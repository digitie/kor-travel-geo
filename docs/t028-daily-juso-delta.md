# T-028: 도로명주소 일변동 ZIP 로더

## 상태

- 상태: 구현 완료
- 대상 브랜치: `codex/t028-daily-delta-loader`
- 대상 데이터: `data/juso/daily/*.zip`
- 주요 코드:
  - `src/kraddr/geo/loaders/text/daily_juso_loader.py`
  - `src/kraddr/geo/cli/main.py`
  - `src/kraddr/geo/api/app.py`
  - `tests/unit/test_daily_juso_loader.py`
  - `tests/integration/test_real_juso_text_loaders.py`

## 배경

T-027 전체 적재 계획에서 `data/juso/daily/*.zip`는 full-load 범위 밖 미지원 입력으로 분리했다. 하지만 운영에서는 분기 또는 월 단위 full-load 뒤 매일 배포되는 변동분을 적용해야 `tl_juso_text`와 `mv_geocode_target`의 freshness를 유지할 수 있다.

이번 T-028은 도로명주소 일변동 ZIP 중 **도로명주소 한글 정본의 건물 단위 변동분**을 `tl_juso_text`에 적용하는 1차 구현이다. `MVM_RES_CD` 매핑은 `Settings.mvm_res_code_actions`를 사용하며, 알 수 없는 코드는 조용히 skip하지 않고 `LoaderError`로 중단한다.

## 실제 파일 구조 확인

로컬 실제 데이터는 `F:\dev\python-kraddr-geo\data\juso\daily` (`/mnt/f/dev/python-kraddr-geo/data/juso/daily`) 아래에 있다. 확인한 ZIP 예시는 다음과 같다.

| ZIP | member | 크기 | 비고 |
|-----|--------|------|------|
| `20260401_dailyjusukrdata.zip` | `AlterD.JUSUKR.20260402.TH_SGCO_RNADR_MST.TXT` | 63,154 bytes | 422행 |
| `20260401_dailyjusukrdata.zip` | `AlterD.JUSUKR.20260402.TH_SGCO_RNADR_LNBR.TXT` | 20,363 bytes | 204행 |
| `20260404_dailyjusukrdata.zip` | `AlterD.JUSUKR.20260405.TH_SGCO_RNADR_MST.TXT` | 7 bytes | `No Data` |
| `20260404_dailyjusukrdata.zip` | `AlterD.JUSUKR.20260405.TH_SGCO_RNADR_LNBR.TXT` | 7 bytes | `No Data` |
| `20260506_dailyjusukrdata.zip` | `AlterD.JUSUKR.20260507.TH_SGCO_RNADR_MST.TXT` | 40,638 bytes | 271행 |
| `20260506_dailyjusukrdata.zip` | `AlterD.JUSUKR.20260507.TH_SGCO_RNADR_LNBR.TXT` | 14,029 bytes | 138행 |

member 이름의 `JUSUKR.YYYYMMDD`가 실제 변동 기준일로 쓰인다. 예를 들어 `20260401_dailyjusukrdata.zip`의 member는 `20260402`를 담고 있으므로 `load_manifest.last_mvmn_de`는 `20260402`가 된다. ZIP 파일명의 날짜는 수집·배포 파일명으로만 기록한다.

## MST 컬럼 해석

`TH_SGCO_RNADR_MST.TXT`는 기존 `rnaddrkor_*.txt`와 같은 앞부분 컬럼을 가지며, 21번째 컬럼(index 20)에 `MVM_RES_CD`가 들어온다. 실제 첫 행은 다음 형태다.

```text
51130310445753400007700000|5113031026|강원특별자치도|원주시|소초면|교항리|0|20|3|511304457534|장작터길|0|77|0|5113031000|소초면|26304||20230611|0|63|||
```

주요 index:

| index | 의미 | `tl_juso_text` 매핑 |
|-------|------|---------------------|
| 0 | 건물관리번호 | `bd_mgt_sn` |
| 1 | 법정동코드 | `bjd_cd` |
| 2~5 | 시도/시군구/읍면동/리 명 | `ctp_kor_nm` 등 |
| 6 | 산여부 원본 | `mntn_yn` |
| 7~8 | 지번 본번/부번 | `lnbr_mnnm`, `lnbr_slno` |
| 9 | 시군구코드+도로명코드 | `sig_cd`, `rn_cd` |
| 10~16 | 도로명/건물번호/행정동/우편번호 | 동일 매핑 |
| 20 | 변동사유코드 | `mvm_res_cd` |
| 22 | 건물명 | `buld_nm` |

`parse_juso_row()`를 그대로 재사용하므로 PNU generated column의 `mntn_yn 0→1, 1→2` 표준 매핑도 기존 정본 로더와 같은 규칙을 따른다.

## MVM_RES_CD 처리

기본 매핑은 `Settings.mvm_res_code_actions`다.

| 코드 | action | 처리 |
|------|--------|------|
| `31`, `33` | `insert` | `INSERT ... ON CONFLICT DO UPDATE` |
| `34`, `35`, `36` | `update` | `INSERT ... ON CONFLICT DO UPDATE` |
| `63`, `64` | `delete` | `DELETE FROM tl_juso_text WHERE bd_mgt_sn = ...` |

`insert`와 `update`를 모두 UPSERT로 처리하는 이유는 다음과 같다.

1. 일부 운영 DB는 직전 full-load 기준월과 daily ZIP 기준일이 완전히 맞지 않을 수 있다.
2. daily ZIP 재실행은 멱등이어야 한다.
3. `MVM_RES_CD=34` 수정 행이 로컬 DB에는 아직 없을 때도 실패 대신 최신 행을 반영하는 것이 운영 복구에 안전하다.

매핑에 없는 코드가 나오면 데이터 제공 사양이 바뀐 것으로 보고 `LoaderError`를 발생시킨다. 조용한 skip은 운영 데이터 누락으로 이어지므로 금지한다.

## 한 배치 안의 중복 키 처리

일변동 ZIP 하나 또는 디렉터리 여러 ZIP을 한 번에 넣을 때 같은 `bd_mgt_sn`이 여러 번 나타날 수 있다. 이번 로더는 staging table에 `staging_seq`를 부여하고, master 반영 전 다음 기준으로 마지막 상태 1건만 고른다.

```sql
SELECT DISTINCT ON (bd_mgt_sn) ...
FROM _juso_daily_staging
ORDER BY bd_mgt_sn, mvmn_de DESC NULLS LAST, source_file DESC, staging_seq DESC
```

따라서 같은 건물관리번호가 같은 batch 안에서 `31` 뒤 `63`으로 다시 나오면 최종 최신 이벤트만 master에 반영된다. 이는 SHP generic delta loader의 "한 배치 PK 1회 등장" 가정보다 보수적인 fail-safe다.

## LNBR member 처리

`TH_SGCO_RNADR_LNBR.TXT`는 실제로 함께 배포되지만 이번 PR에서는 master table에 반영하지 않는다. 이유는 다음과 같다.

- 현재 `tl_juso_text`는 건물 1행에 대표 지번 1개만 보관한다.
- `LNBR` member는 건물관리번호와 지번의 보조 관계를 별도로 제공하므로, 향후 `jibun_rnaddrkor_*`와 함께 1:N 관계 테이블을 설계해야 한다.
- 이 결정은 T-029에서 `jibun_rnaddrkor_*` 활용 여부와 함께 ADR-022로 확정했다. 후속 구현은 `tl_juso_parcel_link` 1:N 테이블로 분리한다.

단, 파일을 완전히 무시하지는 않는다. 로더는 `LNBR` member를 발견해 행 수를 세고, `DailyJusoLoadResult.unsupported_lnbr_rows` 및 `load_manifest.source_set.unsupported_lnbr_rows`에 기록한다. 이렇게 하면 운영자가 "ZIP 안에 적용하지 않은 행이 있었다"는 사실을 manifest에서 확인할 수 있다.

## `No Data` 처리

실제 일변동 ZIP에는 member 내용이 정확히 `No Data`인 경우가 있다. `iter_pipe_rows()`에 그대로 넘기면 컬럼 수 부족 오류가 되므로, daily loader는 64 bytes 이하 member를 먼저 읽어 `No Data`인지 판별한다.

- MST `No Data`: 처리 행 0건으로 skip
- LNBR `No Data`: 미지원 행 0건으로 skip
- 결과에는 `skipped_no_data_sources`로 member 수를 기록

## CLI

```bash
kraddr-geo load daily-juso ./data/juso/daily/20260401_dailyjusukrdata.zip

# 여러 ZIP을 디렉터리 단위로 한 번에 적용
kraddr-geo load daily-juso ./data/juso/daily

# 테스트/검증용으로 파일당 앞 N행만 적용
kraddr-geo load daily-juso ./data/juso/daily/20260401_dailyjusukrdata.zip --limit-per-file 3
```

출력 예:

```text
loaded daily tl_juso_text delta: processed=422, upserted=242, deleted=180, lnbr_skipped=204, no_data_sources=0, last_mvmn_de=20260402
```

## API 작업 큐

`POST /v1/admin/loads`에 `kind="daily_juso_delta"`를 등록할 수 있다.

```json
{
  "kind": "daily_juso_delta",
  "payload": {
    "path": "/mnt/f/dev/python-kraddr-geo/data/juso/daily/20260401_dailyjusukrdata.zip"
  }
}
```

성공하면 `load_jobs`에는 처리 행, upsert/delete 건수가 `log_tail` 메시지로 남는다. daily delta는 full-load batch DAG의 기본 source child에는 포함하지 않는다. daily는 full-load가 끝난 운영 DB에 후속으로 적용하는 별도 작업이기 때문이다.

## `load_manifest` 갱신

성공 후 `table_name='tl_juso_text'` 행을 갱신한다.

| 컬럼 | 값 |
|------|----|
| `last_delta_at` | daily loader 성공 시각 |
| `last_mvmn_de` | member 이름에서 추출한 최대 `YYYYMMDD` |
| `row_count` | 이번 실행에서 처리한 MST 행 수 |
| `source_zip` | 입력 ZIP 또는 디렉터리 경로 |
| `source_checksum` | ZIP이면 해당 파일 sha256, 디렉터리면 하위 ZIP sha256 묶음 해시 |
| `source_yyyymm` | `--yyyymm`가 있으면 그 값, 없으면 `last_mvmn_de[:6]` |
| `source_set` | 처리 건수, 미지원 LNBR 행 수, `No Data` member 수 |

## 검증

이번 PR에서 추가한 검증 범위:

- synthetic ZIP 단위 테스트
  - MST/LNBR member discovery
  - `MVM_RES_CD` 파싱
  - PNU 매핑 재사용
  - `No Data` skip
  - daily member가 없는 ZIP 거절
- 실제 파일 파서 검증
  - `20260401_dailyjusukrdata.zip` MST 422행
  - 코드 분포 `31=185`, `34=57`, `63=180`
  - `20260404_dailyjusukrdata.zip` MST/LNBR `No Data` skip
- 선택형 실제 PostgreSQL 검증
  - `KRADDR_GEO_TEST_PG_DSN`이 있으면 DDL 적용 뒤 실제 full sample + daily sample 3행을 같은 DB에 적재한다.
  - 이번 PR에서는 Docker PostGIS `localhost:15432`에 전용 DB `kraddr_geo_t028`을 새로 만들고 `tests/integration/test_optional_real_postgres_load.py`를 실행했다. 결과는 1 passed, 2.66초였다.
- 전체 회귀
  - `pytest -q`: 122 passed / 3 skipped.
  - `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check`: 통과.
  - frontend `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`: 통과.

## 남은 작업

- T-038: `jibun_rnaddrkor_*`와 `TH_SGCO_RNADR_LNBR.TXT`를 함께 적재하는 `tl_juso_parcel_link` 1:N 보조 테이블을 구현한다.
- T-027 최종 클린 로드: T-028 이후에는 full-load 뒤 daily ZIP 일부를 적용하고 MV refresh/정합성 검증을 추가 smoke로 넣는다.
- daily delta를 여러 날짜 순으로 자동 적용하는 scheduler는 아직 두지 않는다. 운영자는 디렉터리 경로를 넘겨 수동 일괄 적용하거나 `load_jobs`에 날짜별 작업을 등록한다.
