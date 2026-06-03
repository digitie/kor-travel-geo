# T-076 RustFS 업로드 저장소 설계와 구현 계획

## 목적

관리 UI의 원천 파일 업로드 저장소를 로컬 디렉터리뿐 아니라 RustFS(S3 호환 object storage)로 선택할 수 있게 한다. RustFS를 켜면 새 업로드 파일은 최종 저장 위치가 로컬 `data/uploads`가 아니라 RustFS bucket/object가 된다. 이미 로컬에 있는 원천 자료도 RustFS로 올릴 수 있어야 하며, RustFS에 이미 저장된 object 목록을 다시 upload set으로 가져와 `discover`/`plan`/`load` 흐름에 사용할 수 있어야 한다.

이 작업은 코드 작성 전에 다음 보강 범위를 확정한다.

- 백엔드 upload set 저장소 abstraction과 RustFS 연결 설정 API
- admin UI 설정 화면과 업로드 화면의 RustFS 선택·동기화 UX
- Docker 실행 스크립트의 RustFS 컨테이너 기동, bucket 생성 확인, API 환경변수 주입
- `python-kraddr-geo`가 관리하지만 `python-krtour-map`, `tripmate`도 함께 쓰는 로컬 RustFS 운영 원칙
- 기존 `data/`를 사용한 live test와 Chrome/Firefox Playwright e2e 검증 절차

## 외부 전제

RustFS는 S3 호환 object storage로 사용한다. 공식 Docker 문서 기준 이미지는 `rustfs/rustfs`이고 기본 예시는 S3 API `9000`, 콘솔 `9001`을 사용한다. 이 저장소는 FastAPI `9001`, admin UI `9002`를 이미 공식 포트로 쓰므로 RustFS 운영 포트를 S3 API `9003`, console `9004`로 고정한다.

참고:

- <https://docs.rustfs.com/installation/docker/index.html>
- <https://github.com/rustfs/rustfs>

## 저장소 모델

### Upload set manifest

기존 upload set manifest(`upload-set.json`)은 계속 로컬에 둔다. manifest는 작은 metadata이고, upload set 상태 조회·취소·cleanup·job payload 추적에 필요하다. 파일 본문만 저장소 backend에 따라 로컬 파일 또는 RustFS object가 된다.

추가할 manifest 필드:

- `storage_kind`: `local` 또는 `rustfs`
- `storage_uri`: upload set root를 나타내는 URI. RustFS는 `rustfs://<bucket>/<prefix>/uploads/<upload_set_id>/`
- `storage_prefix`: bucket 내부 prefix
- `materialized_path`: RustFS object를 적재 로더가 읽을 수 있도록 내려받은 로컬 cache 경로
- 파일별 `object_key`, `object_etag`, `storage_uri`

기존 `path` 필드는 하위 호환을 위해 유지하되, RustFS 파일에서는 `rustfs://...` URI를 넣는다. 실제 filesystem path가 필요한 로더 진입점은 `materialize_upload_set()`을 거쳐 `materialized_path`를 받는다.

### 구분자와 URI 규칙

RustFS object key는 `/`를 delimiter로 사용한다. 내부 URI는 다음 형식만 허용한다.

```text
rustfs://<bucket>/<project-prefix>/uploads/<upload_set_id>/files/<relative_path>
```

기본 `project-prefix`는 `python-kraddr-geo`다. 공유 RustFS에서 다른 프로젝트가 같은 bucket을 쓰더라도 prefix를 분리한다.

```text
python-kraddr-geo/
python-krtour-map/
tripmate/
```

이 구분자는 UI 표시용 문자열이 아니라 API가 RustFS object 목록을 upload set으로 다시 가져올 때 사용하는 계약이다. object list를 가져올 때는 prefix와 delimiter(`/`)를 기준으로 파일 tree를 복원한다.

### 보존 기간

RustFS object는 기본적으로 무기한 보존한다. `upload_set_ttl_days`는 로컬 upload set cleanup 정책이며, RustFS object 삭제에는 적용하지 않는다. RustFS 삭제는 명시 API 또는 운영자가 RustFS console/S3 client에서 수행하는 수동 작업으로만 한다.

## 백엔드 API

### 설정 조회·저장

신규 admin API:

- `GET /v1/admin/storage/rustfs/config`
- `PATCH /v1/admin/storage/rustfs/config`
- `POST /v1/admin/storage/rustfs/check`

설정 항목:

- 사용 여부: `enabled`
- endpoint URL: 예) Docker 내부 `http://kraddr-geo-rustfs:9003`, host `http://127.0.0.1:9003`
- bucket
- prefix
- region
- path-style 사용 여부
- access key / secret key
- retention days: 기본 `null` 또는 `0`으로 무기한

응답에는 secret 값을 그대로 반환하지 않는다. secret은 `configured: true/false` 상태와 마지막 4자리 같은 redacted hint만 반환한다.

런타임 설정은 환경변수를 기본값으로 삼고, admin UI에서 저장한 값은 `data/rustfs/config.json`에 둔다. 컨테이너 재기동 후에도 Docker volume이 유지되면 admin UI 저장값이 유지된다.

### 새 업로드

`POST /v1/admin/uploads`는 `storage_kind`를 선택적으로 받는다.

```json
{
  "purpose": "full_load_source_set",
  "storage_kind": "rustfs"
}
```

`storage_kind`가 없으면 서버 설정의 RustFS `enabled` 값을 따른다. RustFS가 켜져 있으면 `PUT /v1/admin/uploads/{upload_set_id}/files`는 파일 본문을 임시 spool 파일에 받은 뒤 RustFS object로 업로드하고, 최종 로컬 `files/` 디렉터리에는 저장하지 않는다.

대용량 스트리밍 원칙은 유지한다. checksum 계산, size limit, 상대 경로 escape 방지는 기존 로컬 업로드와 동일하게 적용한다.

### RustFS에 있는 파일 목록 가져오기

신규 admin API:

- `POST /v1/admin/storage/rustfs/import-prefix`

입력:

```json
{
  "prefix": "python-kraddr-geo/uploads/upload_...",
  "purpose": "full_load_source_set"
}
```

서버는 RustFS object list를 읽어 upload set manifest를 만들고, 파일별 `storage_uri`와 `object_key`를 기록한다. 이후 `discover`/`plan` 요청에서 같은 upload set id를 넘기면 materialization cache로 내려받아 기존 로더가 읽을 수 있게 한다.

### 로컬 파일을 RustFS로 올리기

신규 admin API:

- `POST /v1/admin/storage/rustfs/sync-local`

입력:

```json
{
  "root_path": "/data/juso",
  "prefix": "python-kraddr-geo/imports/202604",
  "purpose": "full_load_source_set"
}
```

서버는 허용된 local import root 아래 파일만 업로드한다. Docker 실행에서는 host `data/`를 API 컨테이너의 `/data`에 읽기 전용 mount하고, `KRADDR_GEO_RUSTFS_LOCAL_IMPORT_ROOTS=/data`를 주입한다. 사용자가 임의 시스템 경로를 입력해 container filesystem 전체를 업로드하지 못하게 한다.

## admin UI

### `/admin/settings`

RustFS 설정 섹션을 추가한다.

- 사용 여부 toggle
- endpoint URL
- bucket
- prefix
- region
- access key
- secret key
- 연결 테스트 버튼
- 저장 버튼

secret 입력은 비워 두면 기존 값을 유지한다. 연결 테스트는 bucket 접근 또는 생성 가능 여부를 확인하고, 실패 시 S3 오류 code와 짧은 메시지만 보여 준다.

### `/admin/load`

업로드 패널에 저장소 선택을 추가한다.

- `로컬`
- `RustFS`

RustFS가 서버에서 비활성화되어 있으면 선택지는 disabled로 보이고 설정 화면으로 이동할 수 있게 한다. RustFS 선택 상태에서 업로드하면 `POST /v1/admin/uploads`에 `storage_kind: "rustfs"`를 보낸다. 업로드가 끝난 뒤 source discovery는 기존처럼 upload set id를 사용한다.

추가 동작:

- RustFS prefix 가져오기: prefix 입력 → `import-prefix` → source discovery
- 로컬 경로 RustFS 업로드: root path/prefix 입력 → `sync-local` → source discovery

## Docker와 운영

`scripts/docker_app.sh`는 다음 명령을 제공한다.

- `up-rustfs`: RustFS 컨테이너만 기동한다. bucket 생성은 API의 RustFS 연결 테스트 또는 첫 RustFS 업로드에서 확인한다.
- `up`: API, UI와 함께 RustFS도 기동한다.
- `down-rustfs`: RustFS 컨테이너만 내린다. data volume은 지우지 않는다.
- `logs-rustfs`: RustFS 로그를 본다.

기본값:

```text
container: kraddr-geo-rustfs
image: rustfs/rustfs:latest
network: kraddr-geo-net
S3 API port: 9003
console port: 9004
data dir: ${KRADDR_GEO_RUSTFS_DATA_DIR:-$HOME/kraddr-geo-data/rustfs}
bucket: ${KRADDR_GEO_RUSTFS_BUCKET:-kraddr-geo}
access key: ${KRADDR_GEO_RUSTFS_ACCESS_KEY:-rustfsadmin}
secret key: ${KRADDR_GEO_RUSTFS_SECRET_KEY:-rustfsadmin}
```

RustFS 컨테이너는 RustFS 공식 image의 non-root UID `10001` 정책을 따른다. script는 data dir을 만들고 가능한 환경에서는 owner를 `10001:10001`로 맞춘다. WSL 로컬 개발처럼 `chown`이 막히는 환경에서는 해당 디렉터리를 container-writable 권한으로 열어 둔다. RustFS 로그는 별도 host mount 없이 Docker logs로 확인한다.

이 RustFS 인스턴스의 관리 주체는 `python-kraddr-geo`다. 다만 `python-krtour-map`, `tripmate`도 같은 local RustFS를 사용할 수 있으므로 다음 원칙을 지킨다.

- 컨테이너 이름과 RustFS 포트 `9003`/`9004`는 `python-kraddr-geo` 문서가 기준이다.
- `scripts/docker_app.sh up-rustfs`는 기본적으로 `9003`을 publish 중인 non-managed RustFS 컨테이너를 제거하고 `kraddr-geo-rustfs`를 올린다. 점유자가 Docker Compose 서비스이면 제거 전에 해당 service를 `stop`한다. 이 프로젝트가 RustFS의 로컬 운영 기준이기 때문이다.
- 이미 운영 중인 다른 RustFS를 임시로 재사용해야 하면 `KRADDR_GEO_RUSTFS_REUSE_EXISTING=1`을 명시한다. 이때 script는 해당 컨테이너를 `kraddr-geo-net`에 `kraddr-geo-rustfs` alias로 연결하고, API에는 그 컨테이너의 `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`를 주입한다.
- bucket은 공유하되 project prefix를 분리한다.
- 다른 프로젝트는 이 컨테이너를 삭제하거나 data dir을 cleanup하지 않는다.
- access key/secret key는 로컬 개발 기본값만 문서화하고, 운영 값은 각 프로젝트 `.env` 또는 secret manager에 둔다.
- 운영에서 여러 프로젝트가 같은 RustFS를 쓰면 lifecycle, backup, 접근 권한은 bucket policy 또는 access key 단위로 분리한다.

## 검증 계획

### 백엔드

- RustFS config redaction, merge, secret 유지 단위 테스트
- upload set manifest의 `local`/`rustfs` 직렬화 테스트
- RustFS object key escape 방지 테스트
- `import-prefix`가 object list를 upload set 파일 목록으로 복원하는 테스트
- `sync-local`이 허용 root 밖 경로를 거부하는 테스트
- materialization cache가 sha256이 같은 파일을 재다운로드하지 않는 테스트

### live test

Docker RustFS를 띄운 뒤 기존 `data/` 아래 실제 파일 일부를 사용한다.

1. `scripts/docker_app.sh up-rustfs`
2. API/UI Docker를 최신 image로 기동
3. `/v1/admin/storage/rustfs/check` 성공 확인
4. `/v1/admin/storage/rustfs/sync-local`로 `/data` 아래 실제 원천 파일 일부를 RustFS에 업로드
5. `import-prefix`로 같은 prefix를 upload set으로 다시 가져오기
6. `load-sources/discover`와 `load-sources/plan`이 RustFS upload set id로 성공하는지 확인
7. 신규 브라우저 업로드를 RustFS 저장소로 수행하고 object 존재를 확인

### 프론트엔드와 e2e

프론트엔드 lint, type-check, unit test, build, React Doctor를 WSL ext4 미러에서 실행한다. Playwright e2e와 실제 브라우저는 Windows Node/브라우저에서만 실행하며, 검증 브라우저는 Chrome(`chromium` project)과 Firefox(`firefox` project) 둘 다이다.

필수 e2e:

- `/admin/settings` RustFS 설정 저장·연결 테스트
- `/admin/load` RustFS 업로드 선택, 업로드 완료, source discovery
- RustFS prefix 가져오기
- 좌측 메뉴 이동 중 Next 전역 오류 화면 부재
- VWorld 지도 로딩 회귀

## 남은 위험

- RustFS의 Docker image/env 계약은 RustFS 릴리스에 따라 바뀔 수 있다. `scripts/docker_app.sh`의 image와 port/env는 환경변수로 override 가능하게 둔다.
- RustFS가 S3 호환이어도 일부 고급 API는 구현 차이가 있을 수 있다. 이 저장소는 bucket create/head, object put/head/get/list/delete 같은 기본 API만 사용한다.
- 대용량 파일을 RustFS에 업로드할 때 API 컨테이너의 임시 spool 공간이 필요하다. spool 경로와 최대 업로드 크기를 문서화하고, 로컬 최종 저장소로 오해하지 않게 한다.
- RustFS object는 기본 무기한 보존이므로 실수로 큰 원천 파일을 반복 업로드하면 local disk 사용량이 커진다. cleanup은 명시적 운영 명령으로 분리한다.
