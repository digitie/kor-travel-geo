# T-213 기준 데이터 보존 정책

T-213 전국 라이브데이터 로딩 결과는 T-214/T-215의 기준 입력이다. 따라서 기본 개발 DB나 WSL 테스트 미러의 임시 artifact에만 두면 안 된다. 이 문서는 T-213 기준 데이터를 어디에 두고, 후속 벤치가 무엇을 확인한 뒤 사용해야 하는지 고정한다.

## 보존 공간

| 대상 | 표준 | 금지 |
|------|------|------|
| 원천 파일 | NTFS 공용 데이터 루트 `F:\dev\geodata\juso` | 에이전트 worktree별 `data/juso`에 원천을 따로 흩어 두는 것 |
| PostgreSQL | 전용 DB `kor_travel_geo_t213` 또는 run별 `kor_travel_geo_t213_<YYYYMMDD>` | 기본 개발 DB `kor_travel_geo`를 T-213 기준 DB로 쓰는 것 |
| RustFS | 같은 bucket을 써도 prefix는 `kor-travel-geo/t213/<run-id>`처럼 분리 | 기본 `kor-travel-geo` prefix에 다른 개발 업로드와 섞는 것 |
| 실행 artifact | NTFS 공용 데이터 영역 `F:\dev\geodata\t213-baseline\<run-id>\` | WSL 미러의 `artifacts/`를 유일한 사본으로 두는 것 |
| 실행 env | 비커밋 파일 `.env.t213` 또는 셸 export로 기존 `KTG_PG_DSN`, `KTG_RUSTFS_*`를 T-213 전용 값으로 지정 | 일반 `.env`의 기본 개발 DB를 암묵적으로 사용하는 것 |

`F:\dev\geodata\juso`는 Git에 커밋하지 않는 공용 원천 저장소다. WSL 테스트 미러에서는 `data -> /mnt/f/dev/geodata` 심볼릭 링크를 두면 기존 `data/juso` 상대경로도 같은 원천을 보게 된다. 문서에는 DB 이름, RustFS bucket/prefix, run id, row count, release id만 남기고 access key나 password는 남기지 않는다.

현재 T-213/T-214가 직접 쓰는 활성 원천은 다음 항목만 `F:\dev\geodata\juso` 루트에 둔다.

- `202605_도로명주소 한글_전체분.zip`
- `202604_위치정보요약DB_전체분.zip`
- `202604_내비게이션용DB_전체분.7z`
- `도로명주소 전자지도\202604\*.zip`
- `도로명주소 출입구 정보\202604\*.zip`
- `구역의도형\202603\*.zip`

위 목록 밖의 원천은 삭제하지 않고 `F:\dev\geodata\juso\unused\` 아래 같은 상대 경로로 보존한다. `unused\move-log.csv`는 이동 기록이다.

## `.env.t213` 예시

아래는 형식 예시다. 실제 secret은 로컬 파일에만 둔다.

```bash
KTG_PG_DSN=postgresql+psycopg://<user>:<password>@localhost:5432/kor_travel_geo_t213_<YYYYMMDD>[_rN]
KTG_RUSTFS_ENABLED=true
KTG_RUSTFS_ENDPOINT_URL=http://127.0.0.1:12101
KTG_RUSTFS_BUCKET=kor-travel-geo
KTG_RUSTFS_PREFIX=kor-travel-geo/t213/<run-id>
KTG_JUSO_DATA_ROOT=/mnt/f/dev/geodata/juso
KTG_RUSTFS_MATERIALIZE_DIR=artifacts/t213/<run-id>/rustfs-materialized
```

`scripts/run_t213_live_pipeline.py`, T-214 SQL/REST/MV benchmark, RustFS reconcile은 새 전용 환경변수명을 만들지 않고 위 파일을 source한 셸에서 기존 설정 키를 사용한다.

## 다른 에이전트용 현재 접속 요약

PostgreSQL 기준 데이터는 파일 경로가 아니라 `KTG_PG_DSN`이 가리키는 논리 DB로 접근한다. Docker volume 또는 `pgdata` 내부 경로는 `kor-travel-docker-manager` 구현 세부사항이므로 다른 에이전트의 작업 계약으로 쓰지 않는다.

| 항목 | 값 |
|------|----|
| PostgreSQL host/port | `localhost:5432` |
| PostgreSQL database | `kor_travel_geo_t213_20260615_r3` |
| `KTG_PG_DSN` template | `postgresql+psycopg://<user>:<password>@localhost:5432/kor_travel_geo_t213_20260615_r3` |
| RustFS endpoint | `http://127.0.0.1:12101` |
| RustFS bucket/prefix | `kor-travel-geo` / `kor-travel-geo/t213/20260615-rerun3` |
| 원천 루트 | `F:\dev\geodata\juso` (`/mnt/f/dev/geodata/juso`) |
| T-213 artifact 루트 | `F:\dev\geodata\t213-baseline\20260615-rerun3\` |
| T-214 artifact 루트 | `F:\dev\geodata\t214-benchmark\20260615-r3\` |
| T-215 artifact 루트 | `F:\dev\geodata\t215-acceptance\20260615-r1\` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |

다른 에이전트는 작업 시작 시 일반 `.env`의 `kor_travel_geo`를 암묵적으로 쓰지 말고, 자기 worktree의 비커밋 `.env.t213` 또는 셸 export로 위 값을 명시한다. DB 계정과 password는 로컬 secret이므로 문서에 쓰지 않는다.

WSL/bash 예시는 다음과 같다.

```bash
export KTG_PG_DSN='postgresql+psycopg://<user>:<password>@localhost:5432/kor_travel_geo_t213_20260615_r3'
export KTG_RUSTFS_ENABLED=true
export KTG_RUSTFS_ENDPOINT_URL='http://127.0.0.1:12101'
export KTG_RUSTFS_BUCKET='kor-travel-geo'
export KTG_RUSTFS_PREFIX='kor-travel-geo/t213/20260615-rerun3'
export KTG_JUSO_DATA_ROOT='/mnt/f/dev/geodata/juso'
export KTG_RUSTFS_MATERIALIZE_DIR='artifacts/t213/20260615-rerun3/rustfs-materialized'
```

PowerShell 예시는 다음과 같다.

```powershell
$env:KTG_PG_DSN = 'postgresql+psycopg://<user>:<password>@localhost:5432/kor_travel_geo_t213_20260615_r3'
$env:KTG_RUSTFS_ENABLED = 'true'
$env:KTG_RUSTFS_ENDPOINT_URL = 'http://127.0.0.1:12101'
$env:KTG_RUSTFS_BUCKET = 'kor-travel-geo'
$env:KTG_RUSTFS_PREFIX = 'kor-travel-geo/t213/20260615-rerun3'
$env:KTG_JUSO_DATA_ROOT = 'F:\dev\geodata\juso'
$env:KTG_RUSTFS_MATERIALIZE_DIR = 'artifacts\t213\20260615-rerun3\rustfs-materialized'
```

## T-213 재실행/복원 규칙

1. T-213 proper 또는 recovery run은 전용 DB와 전용 RustFS prefix를 먼저 지정한 뒤 실행한다.
2. `--typed-confirmation "RUN-T213-LIVE <database>"`의 `<database>`는 전용 DB 이름이어야 한다. `kor_travel_geo`이면 실행하지 않는다.
3. 기준년월이 파일명/manifest에 없는 자료는 `202604`로 갈음한다. 예: `zone_shape_full`은 물리 파일 위치가 `구역의도형/202603`이어도 등록/매칭 기준년월은 `202604`로 둔다.
4. 실행 artifact는 먼저 WSL 미러에 생겨도 종료 직후 `F:\dev\geodata\t213-baseline\<run-id>\`로 복사해 기준 사본을 둔다.
5. `t213-live-recovery-summary.json`에는 최소한 active `serving_release_id`, `dataset_snapshot_id`, `source_match_set_id`, 주요 row count, RustFS bucket/prefix, 기준년월 fallback 정책을 남긴다.
6. 전용 DB를 재생성하거나 새 run으로 교체하면 `docs/t213-phase2-live-loading.md`와 `docs/resume.md`의 기준 release/row count를 함께 갱신한다.

## T-214/T-215 사용 전 preflight

T-214/T-215는 benchmark를 시작하기 전에 다음을 확인한다.

```sql
select current_database();
select count(*) from mv_geocode_target;
select count(*) from mv_geocode_text_search;
select count(*) from tl_sppn_makarea;
```

그리고 `ops.serving_releases` / `ops.dataset_snapshots`가 full-prefix schema(`serving_release_id`, `dataset_snapshot_id`, `source_match_set_id`)를 갖고, active release가 `t213-live-recovery-summary.json`의 값과 일치해야 한다. 이 조건이 하나라도 맞지 않으면 해당 DB는 T-213 기준 DB가 아니므로 T-214 결과로 기록하지 않는다.

RustFS가 필요한 benchmark나 reconcile은 `KTG_RUSTFS_ENABLED=true`이고 `KTG_RUSTFS_PREFIX`가 `kor-travel-geo/t213/<run-id>` 계열인지 확인한 뒤 실행한다.

## 현재 기준 baseline

2026-06-15 KST에 T-214 착수용 T-213 baseline을 전용 공간에 재실행했다.

| 항목 | 값 |
|------|----|
| run id | `20260615-rerun3` |
| PostgreSQL host/port | `localhost:5432` |
| PostgreSQL DB | `kor_travel_geo_t213_20260615_r3` |
| `KTG_PG_DSN` template | `postgresql+psycopg://<user>:<password>@localhost:5432/kor_travel_geo_t213_20260615_r3` |
| RustFS bucket/prefix | `kor-travel-geo` / `kor-travel-geo/t213/20260615-rerun3` |
| artifact 사본 | `F:\dev\geodata\t213-baseline\20260615-rerun3\` |
| T-214 benchmark artifact | `F:\dev\geodata\t214-benchmark\20260615-r3\` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| load batch | `batch_ee0c66494eac490ba927e0a689dfd29a` |

핵심 row count는 `tl_juso_text=6,419,795`, `tl_locsum_entrc=6,405,091`, `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830`, `tl_spbd_buld_polygon=10,687,732`, `tl_roadaddr_entrc=6,404,697`, `tl_sppn_makarea=24,204`, `mv_geocode_target=6,419,795`, `mv_geocode_text_search=6,419,795`다. smoke geocode `경기도 용인시 수지구 성복1로 35`는 `OK` 후보 1건을 반환했다.

## 2026-06-15 재발 방지 기록

T-214 착수 중 기본 `.env`가 `kor_travel_geo`를 가리키고, 해당 DB가 T-213 기준 row count와 schema가 아닌 오래된 상태(`mv_geocode_target=6,416,637`, source registry full-prefix column 없음)임을 확인했다. 또한 WSL 테스트 미러의 `artifacts/`는 `rsync --delete` 대상이라 T-213 summary artifact의 유일한 보관소가 될 수 없다.

따라서 이후 T-213 기준 데이터는 이 문서의 전용 DB/RustFS prefix/NTFS `F:\dev\geodata\t213-baseline` 조합으로만 보존하고, T-214는 그 조합을 확인하지 못하면 벤치를 진행하지 않는다.
