# AGENTS.md

## 문서 언어 정책

이 저장소의 모든 Markdown/RST 문서는 한글로 작성한다. 공식 API 필드명, 코드 식별자, 명령어, URL, 제공자 원문처럼 그대로 보존해야 하는 값만 영어를 유지한다. 새 문서나 기존 문서를 수정할 때도 이 규칙을 우선한다.

## 역할

이 저장소는 도로명주소 전자지도(PDF 사양)를 PostgreSQL + PostGIS로 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API** `addr-kr`이다. 사용자 대상 UI가 아닌 디버깅/관리 UI는 별도 Node.js 패키지 `addr-kr-ui`(Next.js 14 + shadcn/ui + react-kakao-maps-sdk)로 운영한다.

이전(v1) SpatiaLite + SQLite 기반 구현(`kraddr.geo`)은 `v1` 브랜치에 보존되어 있다. master는 PostgreSQL + PostGIS 기반 새 사양으로 처음부터 다시 구현한다(ADR-001).

작업 전에 반드시 다음을 읽는다:

1. `README.md` — 프로젝트 개요와 빠른 시작
2. `SKILL.md` — DO NOT 룰, 자주 묻는 작업, 도메인 어휘
3. `docs/architecture.md` — 두 패키지의 관계, 의존 방향
4. `docs/resume.md` — 현재 진척도와 "다음 한 작업"
5. `docs/decisions.md` — 관련 ADR

## 지시 우선순위

1. 사용자 요청
2. 이 `AGENTS.md`
3. `SKILL.md`
4. `docs/architecture.md`, `docs/decisions.md`, `docs/data-model.md`, `docs/backend-package.md`, `docs/frontend-package.md`, `docs/agent-guide.md`, `docs/external-apis.md`
5. `README.md` 및 나머지 `docs/`
6. 기존 코드와 테스트
7. 최소한의, 되돌릴 수 있는 가정

## 절대 하지 말 것 (DO NOT)

`SKILL.md` §4와 동일하지만 핵심만 다시 적는다:

1. **의존 방향 역행 금지** — `dto → core → infra → client → api/cli` 한 방향. `import-linter`가 강제.
2. **동기 인터페이스 추가 금지** — `AsyncAddressClient`만 둔다 (ADR-002).
3. **`pg_trgm.similarity_threshold` 전역 변경 금지** — 트랜잭션 단위로만 `SET LOCAL`.
4. **ORM에 비즈니스 로직 금지** — `infra/models.py`는 매핑만. 쿼리는 raw SQL (ADR-004).
5. **좌표 순서 혼동 금지** — 외부 인터페이스는 모두 `(lon, lat)`.
6. **`MVM_RES_CD` 매핑 하드코드 금지** — `load_codes` 테이블 또는 settings.
7. **응답에 `x_extension` 외 자체 필드 추가 금지** — vworld 호환성을 깬다 (ADR-003).
8. **외부 API 키 평문 커밋 금지** — 모두 `SecretStr`. `.env`는 권한 600 또는 systemd `EnvironmentFile`/vault.
9. **`ogr2ogr` subprocess 호출 금지** — GDAL Python binding 사용. CP949 디코딩 명시 (ADR-005).
10. **프론트엔드 패키지에 DB 드라이버 추가 금지** — `addr-kr-ui`는 REST API만 호출.

## 제공자 API 사용 원칙

- 외부 API 관련 작업은 단순 전달용 래퍼/어댑터/게이트웨이 지양 원칙을 먼저 확인하고 문서/코드에 반영한 뒤 진행한다.
- 하위 사용자에게는 안정된 공개 클라이언트(`AsyncAddressClient`), 타입 모델(`addr_kr.dto`), 열거형(`ZipSource` 등), 보조 함수를 제공한다.
- 단순 전달용 래퍼, 장기 호환 별칭, 임시 facade를 만들지 않는다.
- vworld·juso·epost·Kakao Maps의 발급/호출 절차는 `docs/external-apis.md`에 모아 둔다. 외부 API 호출은 `httpx.AsyncClient` + `tenacity` 재시도, 회로차단, 쿼터 보호를 갖춘다.
- 응답 구조는 vworld와 1:1로 호환되도록 유지하고 자체 확장은 `x_extension` 키에만 둔다.

## 작업 후 체크리스트

`SKILL.md` §7과 동일:

- [ ] `pytest -q` 통과
- [ ] `ruff check .` / `mypy --strict` / `lint-imports` 통과
- [ ] `docs/journal.md`에 작업 항목 추가 (역시간순)
- [ ] `docs/resume.md`의 진척도 갱신
- [ ] 의사결정이 있었다면 `docs/decisions.md`에 ADR 추가
- [ ] 사용자 가시 변경이면 `CHANGELOG.md` 갱신
- [ ] DTO/스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`

## 검증

```bash
# 백엔드 (구현 시점에 활성화)
python -m pytest -q
python -m ruff check .
python -m mypy src/addr_kr
lint-imports

# 프론트엔드 (addr-kr-ui 부트스트랩 후)
cd addr-kr-ui && npm run lint && npm run type-check && npm run test && npm run build
```
