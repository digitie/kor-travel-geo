# T-247 백업/복원 벤치마크 스크립트

## 목적

`scripts/benchmark_backup_restore.py`는 백업/복원 조합별 소요시간, dump directory 크기, 최종 `.tar.zst` 아카이브 크기, 압축률을 같은 JSON 형식으로 남기는 운영 벤치마크 실행기다. N150/Odroid 같은 저전력 단일 호스트에서 `jobs`와 zstd 압축 level의 절충점을 비교하기 위한 T-055/T-063 입력이다.

## 기본 조합

기본 계획은 다음 27개 행이다.

- `profile`: `serving-ready`, `lean-serving`, `forensic`
- `jobs`: `1`, `2`, `4`
- `compression_level`: `3`, `9`, `19`

각 행은 `profile_id=<profile>_j<jobs>_z<level>` 형태로 기록되고, 실행 모드에서는 행별 일회용 target DB를 만들어 복원 후 항상 drop한다. 아카이브는 벤치마크 결과 분석을 위해 `--backup-dir` 아래 보존한다.

## 안전 장치

기본 실행은 계획 전용이다. 실제 벤치마크는 다음 두 조건을 모두 요구한다.

```bash
python scripts/benchmark_backup_restore.py \
  --execute \
  --confirmation "RUN-T247-BENCHMARK <current_database>"
```

`--execute`는 `pg_dump`, `pg_restore`, `tar`, `zstd`가 PATH에 없으면 fail-fast한다. `new_database` 복원 target은 행별로 생성하고 성공/실패와 무관하게 drop한다. 복원 실패 정리 정책은 벤치마크 settings에서 `restore_failed_target_cleanup="drop"`으로 고정한다.

## 산출물

`--output-dir` 기본값은 `artifacts/perf/<run-id>`이며 다음 파일을 쓴다.

- `matrix-plan.json`: `profile×jobs×compression` 계획.
- `benchmark-report.json`: schema version, 환경 snapshot, 계획, 실행 결과, profile별 summary.
- `summary.md`: 계획/결과 표와 N150/Odroid 해석 가이드.
- `backups/*.tar.zst`: 실행 모드에서 생성한 백업 아카이브.

`benchmark-report.json`의 주요 결과 필드:

- `backup_seconds`, `restore_seconds`
- `dump_bytes`, `archive_bytes`
- `compression_ratio = dump_bytes / archive_bytes`
- `archive_to_dump_ratio = archive_bytes / dump_bytes`
- profile별 총합/백업/복원 최단 후보, 최소 아카이브, 최고 압축률 후보

## 사용 예시

계획 전용 smoke:

```bash
python scripts/benchmark_backup_restore.py \
  --run-id t247-plan-smoke \
  --output-dir artifacts/perf/t247-plan-smoke
```

저전력 장비 빠른 실행:

```bash
python scripts/benchmark_backup_restore.py \
  --profile serving-ready \
  --jobs 1 --jobs 2 \
  --compression-level 3 --compression-level 9 \
  --output-dir "$RUN_ROOT/$ENV_LABEL/backup-restore" \
  --execute \
  --confirmation "RUN-T247-BENCHMARK kor_travel_geo"
```

전체 조합:

```bash
python scripts/benchmark_backup_restore.py \
  --output-dir "$RUN_ROOT/$ENV_LABEL/backup-restore" \
  --execute \
  --confirmation "RUN-T247-BENCHMARK kor_travel_geo"
```

## 해석

- `jobs=1`은 CPU/RAM/디스크 큐 여유가 가장 크므로 저전력 기준값이다.
- `jobs=2`는 4코어 N150/Odroid급에서 소요시간과 자원 점유의 균형 후보로 먼저 본다.
- `jobs=4`는 빠를 수 있지만 zstd thread와 `pg_dump` 병렬성이 함께 CPU를 포화시킬 수 있다.
- `compression=3`은 예약 로컬 백업 기본 후보, `9`는 외부 복사 크기와 CPU 비용의 중간점, `19`는 아카이브 크기가 가장 중요할 때만 채택 후보로 본다.

## 검증

이번 작업에서는 제품 코드 경로를 바꾸지 않고 실행기와 순수 helper만 추가했다. 단위 테스트는 기본 조합, typed confirmation, 계획 전용 artifact 생성, summary 선택 로직을 고정한다. 현재 작업 환경의 Windows/WSL PATH에는 `pg_dump`/`pg_restore`/`zstd`가 없어 실행 모드의 live 조합은 실행하지 않았고, 계획 전용 smoke만 확인했다.
