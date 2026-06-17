# ADR-021: 도로명주소 일변동 ZIP은 MST만 즉시 반영하고 LNBR은 manifest에 기록한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-028 구현

## 컨텍스트

행안부 도로명주소 일변동 ZIP(`daily/*.zip`)에는 `TH_SGCO_RNADR_MST.TXT`와 `TH_SGCO_RNADR_LNBR.TXT`가 함께 들어 있다. `MST` member는 기존 `rnaddrkor_*.txt`와 같은 건물 단위 도로명주소 정본 구조에 `MVM_RES_CD`가 추가된 형태라 현재 `tl_juso_text`에 바로 반영할 수 있다. 반면 `LNBR` member는 건물관리번호와 지번의 보조 관계를 제공하므로 현재 `tl_juso_text`의 대표 지번 1개 모델과 직접 맞지 않는다.

## 결정

T-028 daily loader는 `TH_SGCO_RNADR_MST.TXT`만 `tl_juso_text`에 적용한다.

- `31`, `33`은 UPSERT한다.
- `34`, `35`, `36`도 UPSERT한다.
- `63`, `64`는 `bd_mgt_sn` 기준 DELETE한다.
- 알 수 없는 `MVM_RES_CD`는 skip하지 않고 `LoaderError`로 중단한다.
- 같은 batch 안에 동일 `bd_mgt_sn`이 여러 번 나오면 `mvmn_de DESC`, `source_file DESC`, `staging_seq DESC` 기준 최신 1건만 master에 반영한다.
- `TH_SGCO_RNADR_LNBR.TXT`는 T-028 daily MST loader에서 master에 쓰지 않고 행 수만 `DailyJusoLoadResult.unsupported_lnbr_rows`와 `load_manifest.source_set.unsupported_lnbr_rows`에 기록한다. T-038 이후 실제 LNBR 반영은 `juso_parcel_link_delta`가 담당한다.
- `LNBR` 및 `jibun_rnaddrkor_*`의 1:N 지번 관계 테이블 여부는 ADR-022에서 결정한다.

## 근거

- `MST`는 기존 `parse_juso_row()`와 PNU generated column을 재사용할 수 있어 full-load 정본과 같은 컬럼 의미를 유지한다.
- daily ZIP을 재실행해도 결과가 같아야 하므로 신규/수정은 모두 UPSERT가 안전하다.
- 운영 DB의 full-load 기준월과 daily ZIP 기준일이 어긋날 수 있으므로 `update` 코드가 기존 행을 찾지 못해도 실패시키지 않는다.
- `LNBR`을 현재 `tl_juso_text`에 덮어쓰면 대표 지번이 어떤 기준으로 선택되었는지 불명확해진다. 조용한 손실보다 명시적 미지원 기록이 낫다.

## 결과

- CLI는 `ktgctl load daily-juso <zip-or-dir>`를 제공한다.
- API 작업 큐는 `kind="daily_juso_delta"`를 제공한다.
- `load_manifest.last_delta_at`, `last_mvmn_de`, `source_checksum`, `source_set`이 daily 적용 watermark 역할을 한다.
- T-027 최종 클린 적재에서는 full-load 뒤 daily ZIP 일부 적용을 별도 smoke로 추가할 수 있다.

## 남은 위험

- 여러 날짜 ZIP을 디렉터리로 한 번에 적용할 때 파일명 정렬에 의존한다. 현재 로더는 최종 반영 시 `mvmn_de`와 `staging_seq`로 최신 상태를 고르지만, 제공자가 같은 날짜 안에서 더 세밀한 순서를 제공하면 그 필드를 추가로 반영해야 한다.
- `LNBR` 반영은 T-038 `juso_parcel_link_delta`로 분리됐다. 다만 이 테이블을 지번 검색 후보에 연결하는 작업은 아직 후속이다.
