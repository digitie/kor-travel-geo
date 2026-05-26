# T-038: `tl_juso_parcel_link` DDL/로더 구현

## 상태

- 상태: 구현 완료
- 대상 브랜치: `codex/t038-parcel-link-loader`
- 관련 ADR: ADR-022
- 대상 원천:
  - `data/juso/202603_도로명주소 한글_전체분/jibun_rnaddrkor_*.txt`
  - `data/juso/daily/*.zip`의 `AlterD.JUSUKR.*.TH_SGCO_RNADR_LNBR.TXT`

## 목적

`rnaddrkor_*.txt`에서 적재한 `tl_juso_text.pnu`는 건물 대표 지번이다. 반면 `jibun_rnaddrkor_*`와 daily `LNBR`는 한 건물에 여러 지번이 붙는 1:N 링크 원천이다. T-038은 이 보조 관계를 `tl_juso_text`에 덮어쓰지 않고, 별도 테이블 `tl_juso_parcel_link`에 보관한다.

이번 작업은 저장과 적재까지가 범위다. `mv_geocode_target`은 계속 `bd_mgt_sn` unique를 유지하며, 지번 검색 후보 확장이나 UI 상세 패널 표시는 후속 PR에서 별도로 연결한다.

## 스키마

새 테이블:

```sql
CREATE TABLE tl_juso_parcel_link (
  bd_mgt_sn       TEXT NOT NULL REFERENCES tl_juso_text(bd_mgt_sn) ON DELETE CASCADE,
  pnu             TEXT NOT NULL,
  bjd_cd          TEXT NOT NULL,
  mntn_yn         CHAR(1) NOT NULL,
  lnbr_mnnm       INTEGER NOT NULL,
  lnbr_slno       INTEGER NOT NULL DEFAULT 0,
  sig_cd          TEXT NOT NULL,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  source_kind     TEXT NOT NULL CHECK (source_kind IN ('jibun_full','daily_lnbr')),
  source_file     TEXT,
  source_yyyymm   TEXT,
  last_mvmn_de    TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (bd_mgt_sn, pnu)
);
```

인덱스:

- `idx_juso_parcel_link_pnu`: PNU 직접 lookup.
- `idx_juso_parcel_link_road`: 도로명 건물번호 키 기반 추적.
- `idx_juso_parcel_link_bjd`: 법정동+지번 키 기반 추적.

제약:

- `bd_mgt_sn`은 `tl_juso_text`를 참조하고 `ON DELETE CASCADE`를 사용한다.
- `pnu`는 19자리 표준 PNU만 허용한다.
- `mntn_yn`은 원천 값 `0`/`1`만 허용한다. PNU의 11번째 토지구분은 로더가 `build_pnu()`를 통해 `0→1`, `1→2`로 변환한다.
- `source_kind`는 `jibun_full` 또는 `daily_lnbr`만 허용한다.

## 로더

파일: `src/kraddr/geo/loaders/text/parcel_link_loader.py`

### Full Snapshot

CLI:

```bash
kraddr-geo load parcel-links data/juso/202603_도로명주소 한글_전체분 --yyyymm 202603
```

동작:

1. `jibun_rnaddrkor_*.txt`를 찾는다.
2. 각 row에서 `bd_mgt_sn`, `bjd_cd`, `mntn_yn`, 지번 본번/부번, `rncode_full`, 건물번호 키를 읽는다.
3. `build_pnu()`로 표준 19자리 PNU를 만든다.
4. 기본값으로 `tl_juso_parcel_link`를 `TRUNCATE`한 뒤 snapshot을 UPSERT한다.
5. `load_manifest(table_name='tl_juso_parcel_link')`에 `last_full_load_at`, `source_checksum`, `source_yyyymm`, `source_set.kind='jibun_full'`을 기록한다.

`--append`를 주면 기존 테이블을 비우지 않고 UPSERT만 한다. 운영 full-load 기본 흐름에서는 교체 적재가 안전하다.

### Daily Delta

CLI:

```bash
kraddr-geo load daily-parcel-links data/juso/daily/20260401_dailyjusukrdata.zip
```

동작:

1. ZIP 또는 디렉터리에서 `TH_SGCO_RNADR_LNBR.TXT` member를 찾는다.
2. `No Data` member는 skip하고 `skipped_no_data_sources`에 기록한다.
3. `MVM_RES_CD`는 `Settings.mvm_res_code_actions`를 따른다.
4. `insert/update` 계열은 `(bd_mgt_sn, pnu)` 기준 UPSERT한다.
5. `delete` 계열은 같은 PK 기준 DELETE한다.
6. 같은 batch 안에 같은 `(bd_mgt_sn, pnu)`가 여러 번 나오면 `mvmn_de DESC`, `source_file DESC`, `staging_seq DESC` 기준 최신 row만 반영한다.
7. `load_manifest`에는 `last_delta_at`, `last_mvmn_de`, `source_set.kind='daily_lnbr'`를 기록한다.

## Batch/API/UI 반영

새 작업 kind:

- `juso_parcel_link_load`: full snapshot.
- `juso_parcel_link_delta`: daily LNBR delta.

`full_load_batch` 기본 child 순서는 다음과 같다.

1. `juso_text_load`
2. `juso_parcel_link_load`
3. `locsum_load`
4. `navi_load`
5. `shp_polygons_load`
6. `pobox_load`

`juso_parcel_link_load`는 `tl_juso_text` FK에 의존하므로 반드시 `juso_text_load` 뒤에 실행한다. `kraddr-geo-ui`의 `/admin/load` 기본 payload도 `juso_parcel_link_load`를 같은 도로명주소 한글 전체분 경로로 보낸다.

`daily_juso_delta`는 여전히 MST만 `tl_juso_text`에 반영한다. daily ZIP의 LNBR까지 적용하려면 같은 ZIP을 `juso_parcel_link_delta`로 한 번 더 실행한다. 두 작업을 분리한 이유는 운영자가 MST와 보조 지번 delta의 실패/재시도 단위를 따로 볼 수 있게 하기 위해서다.

## 실제 파일 검증

추가/보강 테스트:

- `tests/unit/test_parcel_link_loader.py`
  - `jibun_rnaddrkor` row의 PNU 표준 매핑.
  - daily LNBR의 `MVM_RES_CD`/`mvmn_de` 파싱.
  - `No Data` member skip.
  - 잘못된 `mntn_yn`, 누락된 movement code 오류.
- `tests/integration/test_real_jibun_rnaddrkor_files.py`
  - 실제 서울 `jibun_rnaddrkor_seoul.txt`를 새 iterator로 파싱.
  - 실제 `20260401_dailyjusukrdata.zip` LNBR 204행을 새 iterator로 파싱.
- `tests/integration/test_optional_real_postgres_load.py`
  - `KRADDR_GEO_TEST_PG_DSN`이 있으면 실제 Docker PostgreSQL에서 `tl_juso_parcel_link` snapshot/daily delta를 COPY/UPSERT한다.

수동 Docker 검증:

```bash
dropdb -h localhost -p 15432 -U addr --if-exists kraddr_geo_t038
createdb -h localhost -p 15432 -U addr kraddr_geo_t038
KRADDR_GEO_TEST_PG_DSN='postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t038' \
  .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q
```

결과:

- `1 passed in 2.81s`
- 실제 파일:
  - `jibun_rnaddrkor_seoul.txt` snapshot 2행 적재.
  - `20260401_dailyjusukrdata.zip` LNBR 5행 delta 적재.
  - `load_manifest`의 `tl_juso_parcel_link` row가 `kind='daily_lnbr'`, `last_mvmn_de='20260402'`, `upserted_rows=5`로 갱신됨.

전체 검증:

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 133 passed, 3 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run lint` → 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run type-check` → 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test` → 7 files / 22 tests passed.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run build` → 통과.

## 남은 작업

- 지번 검색 후보 확장: 대표 PNU에 맞지 않는 지번 입력을 `tl_juso_parcel_link`로 `bd_mgt_sn`에 연결한다.
- 정합성 케이스 추가: `tl_juso_parcel_link.bd_mgt_sn` FK 누락, PNU 19자리, source 월/일자 불일치 감시.
- 디버그 UI 상세 패널: 한 건물의 보조 지번 목록 표시.
