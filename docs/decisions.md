# decisions.md — 이전됨 → `docs/adr/`

ADR는 파일당 1개로 [`docs/adr/`](adr/) 아래에 있다 (`NNN-<slug>.md`).
정본 색인·분류(핵심 구조 / → 이관 / → 개발 규칙 / 삭제됨)·작성 규약은
[`docs/adr/README.md`](adr/README.md).

- 순수 개발 규칙(금지·컨벤션)이던 ADR-002/008/014/015는 [`SKILL.md` §4](../SKILL.md)로 이관됐다(옛 ADR 파일은 stub).
- 고유 근거 없이 완전 대체된 ADR-040/042/046(로컬 포트)은 삭제했다(현행 포트는 ADR-048).
- 분리 이전의 단일 파일 본문은 git history에 보존된다.
