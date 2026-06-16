# T-171 fuzzy ranking 결정성·품질 보강

작성일: 2026-06-16

## 결론

T-171에서는 도로명 fuzzy fallback의 후보 ranking 계약을 exact 도로명 조회와 맞췄다. 기존
`fuzzy_roads`는 도로명 trigram 유사도와 건물 본번(`buld_mnnm`)만으로 후보를 좁힌 뒤
동점이면 `pt_source`, `bd_mgt_sn`으로 정렬했다. 이 경우 같은 본번의 여러 부번이 있는
주소에서 도로명 오타가 나면 입력 부번과 다른 후보가 1순위가 될 수 있었다.

이제 `mv_geocode_text_search` helper MV에 `buld_slno`, `buld_se_cd`를 포함하고,
`GeocodeRepository.fuzzy_roads()`는 fuzzy fallback에서도 `buld_mnnm`, `buld_slno`,
`buld_se_cd`를 모두 필터링한다. 후보 정렬은 다음 순서를 유지한다.

1. `similarity(ts.rn_nrm, :road_nrm) DESC`
2. `pt_source='entrance'` 우선
3. `bd_mgt_sn` 오름차순

`pg_trgm.similarity_threshold`는 기존과 같은 `0.42`이며, 트랜잭션 안에서만 `SET LOCAL`로
적용한다.

## DB 변경

fresh schema와 post-load MV rebuild 경로의 `TEXT_SEARCH_MV_SQL`을 갱신했다.

- `mv_geocode_text_search` 컬럼 추가: `buld_slno`, `buld_se_cd`
- helper index 갱신:
  - `idx_mv_text_search_sig_buld`
  - `idx_mv_text_search_sido_buld`
  - `idx_mv_text_search_bjd_prefix_buld`
- Alembic migration: `0020_t171_fuzzy_ranking`

이 helper MV는 source of truth가 아니며 `mv_geocode_target`에서 재생성 가능하다.

## Golden corpus

`T140-GEO-ROAD-FUZZY-001`을 ranking case로 강화했다.

- 입력: `서울특별시 동대문구 왕산길 189-4`
- 기대: 1순위 후보가 `왕산로 189-4`를 포함한다.
- 기대: `candidates[0].confidence >= 0.42`
- 태그: `fuzzy`, `ranking`, `default-live`

이를 위해 `scripts/run_geocoder_golden_corpus.py`의 expected 검증에 `numeric_gte`를
추가했다.

## 검증

- `python -m pytest tests/unit/test_t140_geocoder_golden_corpus.py tests/unit/test_infra_repo_sql.py tests/unit/test_alembic_migrations.py -q`
- `python scripts/run_geocoder_golden_corpus.py --mode fixture --run-id t171-fixture-smoke --output-dir .tmp/t171-fixture-smoke`

실제 live DB에서 확인할 때는 migration 적용 또는 MV rebuild 후 다음을 실행한다.

```bash
python scripts/run_geocoder_golden_corpus.py \
  --mode live \
  --include-tag ranking \
  --output-dir artifacts/golden-corpus/t171-ranking-live
```
