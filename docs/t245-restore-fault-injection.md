# T-245 복원 장애 주입 live 통합 테스트

## 목적

T-244의 backup→restore round-trip fixture를 재사용해, 실제 `pg_dump -Fd` 백업 artifact가 손상됐을 때 `run_restore_job`이 안전하게 거절하고 job-owned target DB를 정리하는지 검증한다. 기본 CI는 live DB와 백업 도구를 요구하지 않으므로 skip되어야 한다.

## 테스트 표면

`tests/integration/test_backup_restore_fault_injection.py`를 추가했다. 모든 테스트는 `KTG_TEST_PG_DSN`과 `pg_dump`, `pg_restore`, `tar`, `zstd`가 없으면 `pytest.skip`한다.

검증 케이스:

- archive-level sha256 flip: 정상 백업 artifact의 DB metadata `sha256`을 잘못된 값으로 바꾸고 `artifact_id` 복원을 시도한다. `verify_archive_checksum`에서 실패해야 한다.
- truncated tar: 정상 `.tar.zst`를 절반으로 잘라 `archive_path` 직접 복원을 시도한다. tar extract 실패로 복원이 중단되어야 한다.
- 내부 checksum 위조: archive를 풀어 `checksums.sha256`의 `manifest.json` digest를 `0...0`으로 바꾼 뒤 다시 묶는다. `verify_internal_checksums`가 mismatch를 잡아야 한다.
- checksum 누락: archive를 풀어 `checksums.sha256`을 제거하고 다시 묶는다. 내부 checksum 파일 누락으로 실패해야 한다.
- 백업 cancel: preflight 직후 cancel된 백업이 `state=failed`, `manifest={"error": "cancelled"}`로 남고 최종 archive, `.part`, temp `backup_*` work dir이 남지 않아야 한다.
- `replace_current` guard: `target_dsn` 사용, 잘못된 typed confirmation, active maintenance window confirmation 불일치가 모두 거절되어야 한다.

손상 복원 4케이스는 각각 throwaway target DB를 먼저 만들고 `restore_failed_target_cleanup="drop"` 설정으로 실행한다. 실패 후 target DB가 존재하지 않는지를 확인해 "target 미적재"를 고정한다.

## 실행

```bash
KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo_rt \
  pytest tests/integration/test_backup_restore_fault_injection.py -q
```

현재 작업 세션의 Windows/WSL PATH에는 `pg_dump`, `pg_restore`, `zstd`가 없어 live 실행은 skip 경로로만 확인했다. 이는 T-245의 "live off skip" 합격조건을 고정한다. 실제 live 검증은 위 도구를 설치한 WSL ext4 테스트 미러에서 같은 명령으로 수행한다.

## 결정

이번 PR은 제품 코드의 복원 정책을 바꾸지 않는다. T-235/T-243/T-244에서 구현된 실패 정리, 부분 복원, round-trip 흐름이 실제 archive 장애에 대해 동작하는지 통합 테스트로 묶는 변경이다.

`replace_current`의 active maintenance window positive path는 실제 serving DB를 덮어쓰는 위험 경로이므로 T-245에서 실행하지 않는다. 대신 `pg_restore` 도달 시 테스트가 실패하도록 안전장치를 걸고, 잘못된 confirmation window가 있어도 `run_restore_job`이 matching confirmation 부재로 거절하는 경로를 검증한다. 실제 hot-swap/rollback round-trip은 T-246의 범위다.
