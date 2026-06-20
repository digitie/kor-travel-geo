# PR #384/#392 post-merge 리뷰와 후속 정리

- 날짜: 2026-06-20
- 범위: 2026-06-19 KST 이후 Claude Code 작성 PR, closed 포함
- 담당: codex

## 확인한 PR

| PR | 상태 | 확인 결과 | 후속 |
|----|------|-----------|------|
| #384 `feat: dev/prod 환경 분리` | merged | conversation comment 1건, review body 0건, review thread 0건, CI green | `docker_app.sh` env-file 상대경로 보강, UI README/live e2e 문서 최신화, root CHANGELOG 추가 |
| #392 `build(ui): migrate kor-travel-geo-ui Tailwind v3 → v4` | merged | conversation comment 0건, review body 0건, review thread 0건, CI green | Tailwind v4 전환을 root CHANGELOG와 후속 검증 기록에 반영 |

## 리뷰 소견

- #384는 dev 기본을 host network로 바꿨지만 `kor-travel-geo-ui/README.md`가 여전히 bridge network
  기본값을 설명했다. live e2e 문서도 과거 `15434`/Claude worktree 절차를 현재 dev 포트
  `12501`/`12505`와 NTFS→WSL 미러 흐름으로 바꿀 필요가 있었다.
- #384의 `KTG_ENV_FILE=.env.dev scripts/docker_app.sh up` 예시는 repo root에서 실행할 때만
  동작했다. 스크립트 경로로 실행하는 사용성을 고려해 상대 env-file은 repo root 기준으로 해석한다.
- #392는 UI 자체 `CHANGELOG.md`에는 기록됐지만 monorepo root `CHANGELOG.md`에도 사용자 가시
  전환으로 남기는 편이 맞다.

## 반영

- `scripts/docker_app.sh`: `KTG_ENV_FILE` 상대 경로를 repo root 기준으로 해석한다.
- `kor-travel-geo-ui/README.md`: Docker 실행 설명을 dev host network 기본과 `KTG_ENV_FILE`
  우선순위에 맞췄다.
- `docs/live-e2e.md`: live e2e 기동 절차를 현재 dev 프로파일, WSL ext4 테스트 미러, Windows
  Playwright 흐름으로 갱신했다.
- `CHANGELOG.md`: dev/prod Docker env-file 정합과 Tailwind v4 전환을 root changelog에 추가했다.

## 검증

- WSL ext4 미러: `bash -n scripts/docker_app.sh` → 통과
- WSL ext4 미러: `python -m pytest -q` → `1094 passed, 67 skipped`
- WSL ext4 미러: `ruff check .` → 통과
- WSL ext4 미러: `mypy src/kortravelgeo scripts/export_openapi.py` → 통과
- WSL ext4 미러: `lint-imports` → `Layered architecture KEPT`
- WSL ext4 미러: `python scripts/export_openapi.py --check --output openapi.json` → 통과
- WSL ext4 미러: `scripts/frontend_check.sh --install` → gen:types/lint/type-check/unit 123건/build 통과.
  설치 없는 첫 실행은 기존 미러의 stale `node_modules`에 `@tailwindcss/postcss`가 없어 실패했다.
- WSL ext4 미러: `npx react-doctor@latest . --offline --verbose --json` → `ok=true`, 기존 warning 31건
- Windows Playwright → WSL UI server `12515`: Chromium/Firefox
  `tests/e2e/navigation.spec.ts tests/e2e/vworld-map.spec.ts` 각 3건 통과. Chromium 전체 e2e 1차 실행은
  UI 서버가 오래된 `.env.local`의 `KTG_API_INTERNAL_URL=http://localhost:8888`을 읽어 proxy 500을
  만든 환경 오류로 2건 실패했고, dev API `12501`을 지정해 targeted 재실행으로 닫았다.
