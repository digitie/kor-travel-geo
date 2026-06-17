# ADR-044: 관리 UI 업로드 파일은 선택적으로 RustFS에 저장한다

- 상태: superseded by ADR-045
- 날짜: 2026-06-03
- 결정자: 사용자 요청, codex

## 컨텍스트

T-045 source set 업로드 구현은 upload set manifest와 파일 본문을 모두 로컬 `data/uploads/<upload_set_id>/` 아래에 저장했다. 이 방식은 단일 API 컨테이너에서 빠르게 동작하지만, 프로젝트 간 원천 자료 공유·대용량 원천 파일 반복 업로드에는 약하다. 사용자는 업로드 파일을 RustFS에 저장할 수 있는 옵션, admin UI 설정, 이미 로컬에 있는 파일의 RustFS 업로드, RustFS에 이미 저장된 파일 목록 재사용, 기본 무기한 보존을 요구했다.

RustFS는 S3 호환 object storage다. 이후 ADR-045에서 이 저장소가 RustFS 자체 구동 생명주기를 관리하지 않는 것으로 결정했다.

## 결정

1. upload set manifest는 계속 로컬 metadata로 유지하고, 파일 본문 저장소만 `local` 또는 `rustfs`로 선택한다.
2. RustFS object URI는 `rustfs://<bucket>/<prefix>/uploads/<upload_set_id>/files/<relative_path>` 형식을 사용한다.
3. object key delimiter는 `/`로 고정한다.
4. 기본 prefix는 `kor-travel-geo`다. 같은 RustFS를 쓰는 `python-krtour-map`, `tripmate`는 각자의 prefix를 사용한다.
5. RustFS object는 기본 무기한 보존한다. 기존 `upload_set_ttl_days`는 로컬 manifest/cache cleanup에만 적용한다.
6. RustFS에 저장된 upload set은 적재 전 materialization cache로 내려받아 기존 GDAL/text loader가 filesystem path를 읽는 계약을 유지한다.
7. admin API는 RustFS 설정 조회·저장·연결 테스트, prefix import, local path sync를 제공한다.
8. admin UI는 `/admin/settings`에서 RustFS endpoint/bucket/prefix/auth를 설정하고, `/admin/load`에서 upload storage를 선택하거나 RustFS prefix/local path sync를 실행한다.
9. Playwright e2e 검증은 Windows Node/브라우저에서 Chrome(`chromium` project)과 Firefox(`firefox` project)를 모두 실행한다.

## 근거

- manifest를 로컬에 유지하면 기존 job payload, cleanup, status API와의 결합을 작게 유지할 수 있다.
- `rustfs://` URI와 `/` delimiter를 명시하면 object list를 다시 upload set tree로 가져오는 규칙이 모호하지 않다.
- materialization cache를 두면 loader 전체를 object storage stream 기반으로 바꾸지 않고도 RustFS 저장소를 적용할 수 있다.
- Chrome/Firefox 양쪽 e2e를 표준으로 삼으면 최근 지도·Next 전역 오류처럼 브라우저별로 다르게 드러나는 회귀를 PR 단계에서 잡을 수 있다.

## 결과

- `docs/t076-rustfs-upload-storage.md`를 구현 기준 문서로 둔다.
- API, UI, 테스트는 이 ADR의 저장소 선택 계약을 따른다.
- 운영자는 RustFS data dir과 access key를 `.env`/secret manager에서 관리하고, 저장소에는 실제 secret을 커밋하지 않는다.

## 남은 위험

- 무기한 보존이 기본이므로 반복 live test가 local RustFS disk 사용량을 빠르게 늘릴 수 있다. object 삭제는 자동 cleanup이 아니라 명시 운영 명령으로만 수행한다.
- materialization cache는 원천 파일 크기만큼 API 컨테이너 local disk를 사용한다. cache 위치와 디스크 여유 공간은 운영 문서에 계속 드러내야 한다.
