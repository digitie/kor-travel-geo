# PR #210~#217 사후 리뷰 및 fixup

날짜: 2026-06-16

## 배경

PR #216 병합 후 Claude Code의 백업/복원 계열 PR을 사후 리뷰했다. 열린 PR은 없었고, 최근 병합된 #205, #206, #208, #210, #211, #213, #214, #215, #217에 GitHub 리뷰 코멘트를 남겼다.

## 주요 발견

- #210/#211: `target_dsn`이 현재 앱 DB와 다른 클러스터를 가리켜도 dry-run과 실제 restore version guard가 현재 엔진의 PostgreSQL/PostGIS 버전을 조회했다.
- #210: dry-run에서 target DB 접속/존재 확인 실패가 warning으로만 남아 `can_restore=true` false-positive가 가능했다.
- #214: restore 실패 cleanup의 `DROP DATABASE`/`ALTER DATABASE` SQL이 DB 이름을 직접 보간했고, quarantine 이름이 PostgreSQL 63자 제한을 넘을 수 있었다.
- #213/#215/#217: 블로킹은 아니지만 restore-drill gate, copy durability, manifest snapshot 일관성, RustFS HEAD timeout/cap은 후속 권장으로 남겼다.

## 반영 내용

- restore/dry-run version query는 실제 `target_dsn`으로 별도 engine을 열어 target cluster를 조회한다.
- dry-run의 target emptiness check와 target version query 실패는 warning이 아니라 blocker로 처리한다.
- restore target DB 이름은 런타임에서 `[A-Za-z_][A-Za-z0-9_]{0,62}` 형태로 검증한다.
- cleanup SQL은 검증된 identifier만 quote하고, quarantine 이름은 suffix 공간을 확보하도록 잘라 PostgreSQL 63자 제한 안에 둔다.
- Windows 전체 단위 테스트에서 함께 드러난 `TL_SPPN_MAKAREA` ZIP member prefix의 OS별 separator 회귀를 `PurePosixPath`로 고쳤다.

## 검증

- Windows: `python -m pytest tests/unit/test_backup_restore.py tests/unit/test_restore_target_cleanup.py tests/unit/test_restore_version_compat.py -q`
- Windows: `python -m ruff check src/kortravelgeo/infra/backup.py tests/unit/test_backup_restore.py tests/unit/test_restore_target_cleanup.py`
- Windows: `python -m pytest -q` (`758 passed, 53 skipped`)
- WSL ext4 mirror: `python -m pytest -q` (`761 passed, 50 skipped`)
- WSL ext4 mirror: `python -m ruff check .`
- WSL ext4 mirror: `python -m mypy src/kortravelgeo`
- WSL ext4 mirror: `lint-imports`

Windows 전체 `mypy src/kortravelgeo`는 로컬 Windows Python 환경에 GDAL `osgeo` stub/module이 없어 기존 loader import에서 실패했다. WSL ext4 검증 환경에서는 통과했다.
