# T-132 C11 guarded 후보 검증 harness 확장

작성일: 2026-06-16

## 결론

T-131에서 1차 후보로 남긴 `centroid_c4_50_c6_c7_move_500` 정책을 반복 검증할 수 있는 별도 harness를 추가했다. active serving object는 변경하지 않았고, T-131 feature table과 T-125 candidate table을 재사용해 같은 결과를 재현한 뒤 cleanup까지 확인했다.

정책 결과는 `repeatable_candidate`다. 다만 100m 초과 이동이 10,099건 남아 있으므로 active serving promotion은 계속 금지한다. 다음 단계는 T-133 shadow serving 성능·rollback 리허설이다.

## 구현

새 스크립트는 `scripts/run_t132_c11_guarded_policy_validation.py`다.

기본 정책:

1. 기존 `current_pt_source`가 `centroid`인 row만 후보로 대체한다.
2. 후보점의 건물 polygon 최근접 거리는 50m 이하여야 한다.
3. 후보점이 우편번호 polygon과 행정구역 polygon 안에 있어야 한다.
4. 기존 대표점 대비 이동거리는 500m 이하로 제한한다.

반복 검증을 위해 다음 flag를 제공한다.

| flag | 의미 |
|------|------|
| `--current-pt-source centroid|any` | 기존 대표점 출처 gate |
| `--building-distance-max-m` | C4 후보 건물 거리 threshold |
| `--movement-max-m` / `--no-movement-limit` | 이동거리 threshold |
| `--allow-c6-c7-errors` | C6/C7 containment gate 해제 |
| `--require-single-candidate` | `bd_mgt_sn`당 후보 1개만 허용 |
| `--require-same-source-month` | 텍스트 정본과 후보 기준월 일치 요구 |
| `--sample-limit`, `--sample-movement-min-m` | sample CSV/GeoJSON export 범위 |

산출물은 결정적 `summary.json` schema, `guarded_policy_samples.csv`, `guarded_policy_samples.geojson`, `reproduce_t132_guarded_policy.sql`을 포함한다. sample row에는 `coord_source_detail="c11_bundle_guarded"`, 텍스트/후보 기준월, 기존 `pt_source`, C4/C6/C7 판정, 기존점·후보점 좌표가 함께 들어간다.

## Live 실행

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| 후보 기준월 | `202604` |
| 텍스트 정본 기준월 | `202605` |
| 산출물 | `F:\dev\geodata\t132-c11-guarded-policy-validation\20260616-r1\` |

실행 명령:

```bash
python scripts/run_t132_c11_guarded_policy_validation.py \
  --pg-database kor_travel_geo_t213_20260615_r3 \
  --reuse-candidate \
  --reuse-features \
  --output-dir /mnt/f/dev/geodata/t132-c11-guarded-policy-validation/20260616-r1 \
  --sample-limit 500 \
  --sample-movement-min-m 100
```

## 결과

| metric | 값 |
|--------|---:|
| 후보 feature row | 6,404,009 |
| baseline C3 unresolved in candidates | 3,498,081 |
| 정책 사용 후보 | 3,482,270 |
| C3 채움 | 3,482,270 |
| candidate C4 over500 | 0 |
| candidate C6 error | 0 |
| candidate C7 error | 0 |
| movement p50 | 6.691m |
| movement p95 | 30.956m |
| movement p99 | 64.981m |
| movement max | 495.345m |
| movement >100m | 10,099 |
| movement >500m | 0 |

`gate_result.status`는 `repeatable_candidate`이고, `serving_promotion_allowed=false`다. hard block은 없지만 `policy still has movement over 100m` warning이 남는다.

## Cleanup

실행 후 다음 작업 테이블을 삭제하고 `to_regclass`로 잔존 relation이 없음을 확인했다.

- `_ktg_t125_c11_bundle_address`
- `_ktg_t125_c11_bundle_entrance`
- `_ktg_t125_c11_candidate_raw`
- `_ktg_t125_c11_candidate_best`
- `_ktg_t131_c11_policy_features`

`summary.json`의 cleanup 결과는 `passed=true`, `remaining_relations=[]`다.

후속 T-133에서 같은 feature table이 필요하면 이번 실행이 작업 테이블을 삭제했으므로 `--reuse-candidate`/`--reuse-features` 없이 다시 생성하거나, T-133 전용 shadow table 생성 단계에서 같은 SQL을 재사용해야 한다.

## 검증

Windows NTFS worktree:

```bash
python -m pytest tests/unit/test_t132_c11_guarded_policy_validation.py tests/unit/test_t131_c11_guarded_policy_simulation.py -q
python -m ruff check scripts/run_t132_c11_guarded_policy_validation.py tests/unit/test_t132_c11_guarded_policy_validation.py
python -m mypy scripts/run_t132_c11_guarded_policy_validation.py
```

WSL ext4 테스트 미러에서도 같은 focused pytest/ruff/mypy를 통과했다.

## 후속

T-133에서 이 정책을 shadow table/MV 또는 read-only candidate path로 구성해 SQL/REST p95, flag off 동일성, rollback 절차를 검증한다. T-134에서는 `pt_source`를 기존 호환 값으로 유지하면서 `coord_source_detail`을 `x_extension` 또는 v2 전용 필드로 노출할지 결정한다. T-119는 여전히 T-133/T-134/T-137, ADR-051 accepted, 사용자 승인 전까지 금지한다.
