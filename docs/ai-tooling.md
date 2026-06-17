# AI 에이전트 툴링 설정 (MCP · agents · skills)

이 저장소는 여러 AI 코딩 에이전트(Claude Code · ChatGPT Codex · Google Antigravity 2.0 · opencode)를
고정 worktree에서 병행 운영한다(ADR-034, `AGENTS.md`). 각 도구의 MCP 서버·서브에이전트·스킬 설정을
저장소에 commit해 worktree 간 일관성을 유지한다.

## MCP 서버

| 서버 | Claude Code (`.mcp.json`) | Codex (`.codex/config.toml`) | Antigravity (`antigravity.json`) | opencode (`opencode.json`) |
|------|:--:|:--:|:--:|:--:|
| `filesystem` | ✅ | ✅ | ✅ | ✅ |
| `codegraph` | (전역/플러그인) | ✅ | ✅ | ✅ |
| `playwright` | (플러그인) | ✅ | ✅ | ✅ |
| `sequential-thinking` | — | ✅ | ✅ | ✅ |

- **filesystem** = `@modelcontextprotocol/server-filesystem`. 노출 경로는 **`.`(상대)** 로 둔다 — 설정 파일이
  worktree마다 다른 절대 경로(`kor-travel-geo-claude`/`-codex`/`-antigravity`)에 commit돼 있으므로,
  도구가 서버를 worktree 루트 cwd로 기동하면 `.`가 곧 해당 worktree 루트를 가리켜 이식성이 보장된다.
- Claude Code `.mcp.json`은 사용자 지시대로 **filesystem만** 추가한다. codegraph/playwright/context7 등은
  이미 전역 설정·플러그인으로 노출되므로 프로젝트 레벨 중복 등록을 피한다.
- 포맷 차이: Claude/Antigravity = `mcpServers`(객체, `command`/`args`/`env`); Codex = TOML
  `[mcp_servers.<name>]`; opencode = `mcp`(객체, `type:"local"`, `command`=배열, `environment`).
- Antigravity의 실 적용 경로는 전역 `~/.gemini/config/mcp_config.json`이다. 저장소의 `antigravity.json`은
  그 정본 소스로, 개발자가 전역 위치로 복사/동기화한다.

## 서브에이전트

- Claude Code: `.claude/agents/*.md`(frontmatter `name`/`description`/`tools`/`model` + 프롬프트).
- Codex: `.codex/agents/*.toml`(`developer_instructions`).
- opencode: `.opencode/agent/*.md`(frontmatter `description`/`mode: subagent`/`tools` + 프롬프트). 위 5개
  공통 에이전트(api-designer/backend-developer/frontend-developer/mobile-developer/ui-designer)에 Codex 전용
  `ui-fixer`까지 6종을 포팅. `model`은 의도적으로 비워(세션 모델 상속) provider 고정을 피한다.

## 스킬 (Anthropic Agent Skills 규격, `SKILL.md`)

- 정본 소스: `.agents/skills/<skill>/`(8종 — postgres 계열). Claude Code는 `.claude/skills/`에서 읽는다.
- opencode: `.opencode/skill/<skill>/`로 동일 `SKILL.md`(name+description frontmatter가 그대로 호환)와
  `references/`를 복사. opencode가 SKILL.md를 동적 도구로 자동 등록한다.
- Antigravity: 스킬은 **전역** `~/.gemini/skills/<skill>/SKILL.md`에서만 인식된다(프로젝트 레벨 디렉터리
  없음). 저장소의 `.agents/skills/`를 정본으로 두고 전역 위치로 동기화한다.
