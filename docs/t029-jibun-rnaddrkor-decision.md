# T-029: `jibun_rnaddrkor_*` 활용 결정

## 상태

- 상태: 결정 완료
- 대상 브랜치: `codex/t029-jibun-rnaddrkor-decision`
- 대상 데이터:
  - `data/juso/202603_도로명주소 한글_전체분/jibun_rnaddrkor_*.txt`
  - `data/juso/daily/*.zip`의 `TH_SGCO_RNADR_LNBR.TXT`
- 관련 ADR: ADR-022

## 결론

`jibun_rnaddrkor_*`와 daily `LNBR` member는 `tl_juso_text`의 대표 PNU를 대체하지 않는다. 둘 다 건물관리번호(`bd_mgt_sn`)와 보조 지번(PNU)의 **1:N 관계**를 표현하는 원천이므로, 후속 구현에서 별도 테이블 `tl_juso_parcel_link`를 추가한다.

이번 T-029 PR에서는 DDL/loader를 바로 추가하지 않고 다음 결정을 확정한다.

1. `tl_juso_text.pnu`는 기존 정본 대표 지번으로 유지한다.
2. `jibun_rnaddrkor_*`는 full-load 시 `tl_juso_parcel_link`의 기준 snapshot으로 적재한다.
3. daily `TH_SGCO_RNADR_LNBR.TXT`는 같은 테이블의 delta source로 사용한다.
4. `tl_juso_parcel_link` 구현은 T-038 후속 작업으로 분리한다.

## 실제 파일 구조

`jibun_rnaddrkor_*.txt`는 14컬럼 pipe-delimited CP949 텍스트다. 서울 파일 첫 행:

```text
11110119200500100014900000|1111012000|서울특별시|종로구|신문로1가||0|150|0|111102005001|0|149|0|
```

컬럼 해석:

| index | 의미 | 비고 |
|-------|------|------|
| 0 | `bd_mgt_sn` | 건물관리번호 |
| 1 | `bjd_cd` | 보조 지번의 법정동코드 |
| 2~5 | 시도/시군구/읍면동/리 명 | 표시·검증용 |
| 6 | `mntn_yn` | PNU 토지구분 변환 재료 |
| 7~8 | 지번 본번/부번 | PNU 본번/부번 |
| 9 | `rncode_full` | 시군구코드+도로명코드 |
| 10~12 | 건물구분/건물본번/건물부번 | 도로명 건물번호 키 |
| 13 | 빈 값 | full snapshot에서는 movement code 없음 |

daily `TH_SGCO_RNADR_LNBR.TXT`는 같은 14컬럼 구조를 쓰되 index 13에 `MVM_RES_CD`가 들어온다.

```text
41480253320608900004500023|4148025326|경기도|파주시|파주읍|파주리|0|31|7|414803206089|0|45|23|31
```

## 실제 cardinality 계측

로컬 실제 데이터 `/mnt/f/dev/python-kraddr-geo/data/juso/202603_도로명주소 한글_전체분` 기준:

| 범위 | 행 수 | distinct `bd_mgt_sn` | 2개 이상 보조 지번을 가진 건물 | 한 건물 최대 보조 지번 수 |
|------|-------|----------------------|--------------------------------|---------------------------|
| 전국 `jibun_rnaddrkor_*` | 1,769,370 | 986,309 | 334,789 | 545 |
| 서울 `jibun_rnaddrkor_seoul.txt` | 89,290 | 52,280 | 13,318 | 545 |

서울 파일에서 `rnaddrkor_seoul.txt` 대표 PNU와 비교한 결과:

| 항목 | 값 |
|------|----|
| `jibun_rnaddrkor_seoul.txt` 행 수 | 89,290 |
| 대표 PNU와 같은 행 | 1 |
| 대표 PNU와 다른 행 | 89,289 |
| `rnaddrkor_seoul.txt`에서 찾지 못한 `bd_mgt_sn` | 0 |

즉 `jibun_rnaddrkor_*`는 "대표 지번 보정"이 아니라 "추가 지번 링크"로 보는 것이 맞다. 이를 `tl_juso_text.pnu`에 덮어쓰면 대표 PNU의 의미가 깨지고, 한 건물에 여러 지번이 있는 정보를 대부분 잃는다.

daily `LNBR` 예시:

| ZIP | 행 수 | distinct `bd_mgt_sn` | 2개 이상 지번 변경이 있는 건물 | 한 건물 최대 행 수 | 코드 분포 |
|-----|-------|----------------------|-------------------------------|--------------------|-----------|
| `20260401_dailyjusukrdata.zip` | 204 | 72 | 31 | 30 | `31=74`, `63=130` |
| `20260506_dailyjusukrdata.zip` | 138 | 56 | 22 | 30 | `31=77`, `63=61` |

daily `LNBR`도 한 건물관리번호에 여러 행이 올 수 있으므로 T-028의 `tl_juso_text` delta와 분리해야 한다.

## 후속 테이블 초안

T-038에서 구현할 테이블 초안:

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
  PRIMARY KEY (bd_mgt_sn, pnu),
  CHECK (char_length(pnu) = 19)
);

CREATE INDEX idx_juso_parcel_link_pnu ON tl_juso_parcel_link (pnu);
CREATE INDEX idx_juso_parcel_link_road
  ON tl_juso_parcel_link (sig_cd, rn_cd, buld_se_cd, buld_mnnm, buld_slno);
```

주의:

- `pnu`는 `build_pnu()`와 DB generated column 규칙을 일치시킨다(`mntn_yn 0→1`, `1→2`).
- full snapshot(`jibun_rnaddrkor_*`)은 `source_kind='jibun_full'`로 적재한다.
- daily `LNBR`은 `MVM_RES_CD=31` 계열을 UPSERT, `63` 계열을 DELETE로 적용한다.
- `tl_juso_text` 삭제 시 관련 parcel link도 같이 지워져야 하므로 `ON DELETE CASCADE`가 적절하다.

## API/MV 반영 원칙

T-038에서 테이블과 로더를 추가하더라도 즉시 `mv_geocode_target`의 대표 결과를 다중 row로 늘리지 않는다. 현재 `mv_geocode_target`은 `bd_mgt_sn` unique를 전제로 `REFRESH CONCURRENTLY`와 geocode/reverse/search 응답 중복 제거를 유지한다.

후속 활용 방향은 다음 중 하나를 별도 PR에서 선택한다.

1. 지번 검색 후보 확장: 입력 PNU 또는 지번 주소가 대표 PNU와 일치하지 않을 때 `tl_juso_parcel_link`로 `bd_mgt_sn`을 찾은 뒤 기존 `mv_geocode_target` 대표 좌표를 반환한다.
2. 디버그/관리 UI 표시: 한 건물의 보조 지번 목록을 상세 패널에 표시한다.
3. 정합성 케이스 추가: `tl_juso_parcel_link.bd_mgt_sn`이 모두 `tl_juso_text`에 존재하는지, PNU가 19자리 표준인지 검증한다.

## 검증

이번 PR에서 추가한 테스트:

- `tests/integration/test_real_jibun_rnaddrkor_files.py`
  - 실제 `jibun_rnaddrkor_seoul.txt` 첫 행들이 14컬럼 구조인지 확인한다.
  - 같은 `bd_mgt_sn`에 서로 다른 보조 지번 PNU가 나오는 것을 확인한다.
  - 실제 daily `20260401_dailyjusukrdata.zip`의 `LNBR` member가 같은 구조 + `MVM_RES_CD`를 갖는지 확인한다.
- 전체 회귀:
  - `pytest -q`: 124 passed / 3 skipped.
  - `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check`: 통과.

## 다음 작업

- T-038: `tl_juso_parcel_link` DDL/Alembic, full snapshot loader, daily LNBR delta loader, manifest/정합성 테스트 구현.
- T-027 최종 클린 적재: T-038 이후에는 full-load 뒤 parcel link snapshot과 daily LNBR delta까지 적용하는 smoke를 추가한다.
