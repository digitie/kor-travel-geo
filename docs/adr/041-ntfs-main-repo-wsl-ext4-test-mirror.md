# ADR-041: NTFS main repo와 WSL ext4 테스트 미러를 사용한다

- 상태: superseded by ADR-065
- 날짜: 2026-05-31
- 결정자: 사용자 요청, codex

## 컨텍스트

ADR-034는 WSL ext4 아래 `geo-*` worktree를 source of truth로 두었다. 이후 사용자는 Windows에서 접근 가능한 NTFS checkout을 메인 repo로 삼고, 테스트가 필요할 때만 WSL ext4로 복사하는 방식이 더 명확하다고 결정했다. 또한 worktree 이름의 `geo-*` 접두사는 저장소 이름과 충돌 없이 드러나도록 `kor-travel-geo-*`로 바꿔야 한다.

NTFS에서 장기 테스트와 의존성 설치를 직접 실행하면 inotify, 파일 권한, 대량 I/O 문제가 여전히 반복될 수 있다. 따라서 Git source of truth와 테스트 실행 위치를 분리한다.

## 결정

1. NTFS main repo는 `/mnt/f/dev/kor-travel-geo`로 둔다.
2. 에이전트별 NTFS worktree는 다음으로 고정한다.

| 에이전트 | 고정 worktree | idle branch |
|----------|---------------|-------------|
| ChatGPT Codex | `/mnt/f/dev/kor-travel-geo-codex` | `agent/codex-idle` |
| Claude Code | `/mnt/f/dev/kor-travel-geo-claude` | `agent/claude-idle` |
| Google Antigravity 2.0 | `/mnt/f/dev/kor-travel-geo-antigravity` | `agent/antigravity-idle` |

3. 코드 편집, branch, commit, push, PR은 NTFS worktree에서 수행한다.
4. Python/Node 의존성 설치, 단위/통합 테스트, build, `uvicorn` 장기 실행은 NTFS worktree를 WSL ext4 테스트 미러로 복사한 뒤 수행한다.
5. ext4 테스트 미러는 실행 산출물 전용이며 commit/push하지 않는다.
6. 로컬 secret/env 파일은 각 NTFS worktree에 복사하되 Git에 커밋하지 않는다. `.env*`, `.claude/`, `.codegraph/`는 ignore 대상이다.
7. CodeGraph는 NTFS worktree마다 `codegraph init -i`로 초기화한다. `/mnt` 경로에서는 live watch가 비활성화될 수 있으므로 branch 전환, pull, merge 뒤에는 수동 `codegraph sync`를 실행한다.
8. Playwright e2e는 Windows Node/브라우저에서만 실행한다.

## 근거

- NTFS main repo는 Windows 도구, 에이전트 세션, 사용자의 파일 탐색 경로를 하나로 맞춘다.
- 테스트 실행은 ext4 미러에 격리해 NTFS 대량 I/O와 watcher 문제를 피한다.
- `kor-travel-geo-*` 접두사는 저장소와 worktree의 소속을 이름만으로 구분하게 해 준다.
- secret/env 파일을 worktree마다 복사하면 새 에이전트 세션이 API key와 로컬 포트 설정을 다시 찾지 않아도 된다.

## 실행 기록

2026-05-31에 다음을 실제로 수행했다.

- `/mnt/f/dev/kor-travel-geo-codex`, `/mnt/f/dev/kor-travel-geo-claude`, `/mnt/f/dev/kor-travel-geo-antigravity` worktree 생성.
- `.env`, `kor-travel-geo-ui/.env.local`, `.claude/settings.local.json`, `backend/.env.local`, `web/.env.local`을 각 worktree로 복사.
- `KTG_API_INTERNAL_URL`은 공식 API 포트 `8888`에 맞게 `http://localhost:8888`로 정리.
- 세 worktree에서 `codegraph init -i`와 `codegraph status` 실행.
- `.gitignore`에 `.claude/` 추가.

## 남은 위험

- NTFS main repo에 기존 미커밋 변경이 있으면 main fast-forward 전에 사용자 소유 변경을 먼저 정리해야 한다. 에이전트는 이를 임의로 되돌리지 않는다.
- ext4 테스트 미러에서 수정한 파일을 NTFS worktree로 되돌려 쓰면 source-of-truth가 흐려진다. 필요한 수정은 NTFS worktree에서 다시 적용한다.
- CodeGraph live watch가 `/mnt`에서 꺼질 수 있으므로 `codegraph sync` 누락 시 인덱스가 낡을 수 있다.
