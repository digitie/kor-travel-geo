# 🗺️ kor-travel-geo

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)
![Database](https://img.shields.io/badge/database-PostgreSQL%20%2B%20PostGIS-336791.svg)

**도로명주소 전자지도(PDF 사양)를 PostgreSQL + PostGIS에 적재해 제공하는 한국 주소 지오코딩 라이브러리·REST API**입니다. vworld OpenAPI와 호환되는 응답 구조를 유지하면서 자체 확장(`x_extension`)을 지원합니다. 사용자 대상 UI가 아닌 디버깅/관리 UI는 별도 Node.js 패키지 [`kor-travel-geo-ui`](docs/architecture/frontend-package.md)로 운영합니다.

> [!NOTE]
> **현재 상태**
>
> `main` 브랜치는 PostgreSQL + PostGIS 기반 재구현의 백엔드·REST·CLI와 `kor-travel-geo-ui` 디버그/관리 UI를 포함합니다.
>
> **주요 구현 항목**:
> - **T-005 ~ T-042**: PostgreSQL + PostGIS 기반의 지오코딩 엔진 및 실데이터 검증
> - **T-044**: `maplibre-vworld-js` 0.1.0 기준 문서-only 재확인
> - **T-277**: 디버그 UI 지도를 GitHub `maplibre-vworld-react` package 기반으로 전환
> - **T-045**: Source set 기준월 선택 및 대용량 업로드/적재 UX 개선
> - **T-046**: DB 백업/복원 UI 구현 및 대구 지역 부분 DB 실제 backup/restore 검증 완료
> - **T-047**: 주요 benchmark 수행 및 튜닝
> - **T-049**: 운영 메타데이터 1차 구현
> - **T-052**: v1/v2 API 분리 및 AI-friendly API reference 제공
> - **T-053**: C1 ~ C10 분석 및 수동 판정 UI
> - **T-054**: 한국 IP 대상 GeoIP gate 적용
> - **T-055**: N150/Odroid 환경 실측 준비
> - **T-056**: `python-legacy-address-base` Address 코드 helper 독립 구현 및 정리
> - **T-057**: Region hint 1차 실측
> - **T-061**: Slim text-search helper 도입
> - **T-064**: 상위 주소 geocode 후보 반환 구현
> - **T-065**: 내비게이션용 DB 기반 `시군구용건물명` 검색 반영
> - **T-076**: Upload set의 로컬 파일시스템/RustFS(S3 호환) 저장소 선택 및 bucket 접속 설정
>
> **최종 재적재 결과 (T-027)**:
> - 빈 PostGIS DB에 전국 `data/juso` 및 `20260401_dailyjusukrdata.zip`을 클린 적재하여 `mv_geocode_target=6,416,642`, `mv_geocode_text_search=6,416,642`, `tl_sppn_makarea=24,204` 생성 확인 및 smoke 테스트 통과.
>
> *이전 SpatiaLite 기반 구현(동일 `kortravelgeo` 패키지)은 `v1` 브랜치에 보존되어 있습니다(ADR-001).*

---

## 📝 문서 언어

이 저장소의 Markdown/RST 문서는 **한국어**로 작성합니다. 공식 API 필드명, 코드 식별자, 명령어, URL, 패키지명처럼 그대로 보존해야 하는 값만 영문 원문을 유지합니다.

---

## 💻 개발 환경 (PC, WSL)

> [!WARNING]
> PC 개발의 Git source of truth는 NTFS의 `F:\dev\kor-travel-geo` 계열 checkout이다. 다만 Python/Node 의존성 설치, 테스트, 장기 실행 검증은 NTFS worktree를 WSL ext4 테스트 미러로 복사한 뒤 실행한다. NTFS worktree에서 직접 `pip`/`npm test`/`uvicorn` 장기 실행을 하지 않는다.

```text
NTFS main repo:   /mnt/f/dev/kor-travel-geo/
NTFS worktree:    /mnt/f/dev/kor-travel-geo-codex/
NTFS worktree:    /mnt/f/dev/kor-travel-geo-claude/
NTFS worktree:    /mnt/f/dev/kor-travel-geo-antigravity/
WSL test mirror:  ~/dev/kor-travel-geo-<agent>-test/   ← rsync 대상, git 작업 금지
Data:             /mnt/f/dev/geodata/juso/
```

- 코드 편집, Git branch/commit/PR, CodeGraph 인덱스는 각 NTFS worktree에서 수행한다.
- 테스트 전에는 현재 NTFS worktree를 WSL ext4 테스트 미러로 복사한다. 예: `rsync -a --delete --exclude .git --exclude .codegraph --exclude .venv --exclude node_modules --exclude kor-travel-geo-ui/.next --exclude data --exclude artifacts /mnt/f/dev/kor-travel-geo-codex/ ~/dev/kor-travel-geo-codex-test/`
- 대용량 Juso 원천은 공용 경로 `F:\dev\geodata\juso`에 둔다. 테스트 미러에서는 `data -> /mnt/f/dev/geodata` symlink를 두어 기존 `data/juso` 상대경로를 유지한다. 현재 쓰지 않는 원천은 `F:\dev\geodata\juso\unused\` 아래에 보존한다.
- ext4 테스트 미러는 실행 산출물 전용이다. 미러에서 commit/push하지 않고, 필요한 코드 변경은 NTFS worktree에 반영한다.
- Git metadata는 Windows Git 기준으로 유지한다. WSL 미러에서 commit/branch를 기록하는 스크립트는 Windows `git.exe`와 `F:/dev/kor-travel-geo-*` 경로를 사용하며, `.git` 포인터를 `/mnt/f/...`용으로 바꾸지 않는다.
- PostgreSQL 검증은 이 프로젝트가 직접 DB를 띄우지 않고, `KTG_PG_DSN`이 가리키는 이미 동작 중인 PostgreSQL/PostGIS에 접속해 수행한다. RustFS도 `KTG_RUSTFS_*` 접속 설정으로 이미 준비된 bucket을 사용한다.
- 로컬 키와 환경 파일(`.env`, `kor-travel-geo-ui/.env.local`, `.claude/settings.local.json` 등)은 NTFS worktree마다 복사하되 Git에 커밋하지 않는다. `.env*`, `.claude/`, `.codegraph/`는 ignore 대상이다.
- Playwright e2e는 Windows Node/브라우저에서만 실행한다. WSL headless Chromium은 반복적으로 시스템 라이브러리 누락이 발생하므로 사용하지 않는다.
- AI 에이전트 worktree 이름은 `geo-*` 접두사를 쓰지 않고 `kor-travel-geo-*` 접두사로 통일한다(ADR-041).

### 에이전트 worktree

| 에이전트 | NTFS worktree | idle branch |
|----------|---------------|-------------|
| ChatGPT Codex | `/mnt/f/dev/kor-travel-geo-codex` | `agent/codex-idle` |
| Claude Code | `/mnt/f/dev/kor-travel-geo-claude` | `agent/claude-idle` |
| Google Antigravity 2.0 | `/mnt/f/dev/kor-travel-geo-antigravity` | `agent/antigravity-idle` |

상세 실행 예시는 [`docs/dev-environment.md`](docs/dev-environment.md)와 [`docs/ports.md`](docs/ports.md)를 참조합니다.

---

## 🚀 빠른 시작

### 1. 백엔드 설정 (Python)

```bash
# NTFS Codex worktree 기준
cd /mnt/f/dev/kor-travel-geo-codex

# 테스트/적재 검증은 ext4 미러에서 실행
mkdir -p ~/dev/kor-travel-geo-codex-test
rsync -a --delete --exclude .git --exclude .codegraph --exclude .venv --exclude node_modules --exclude kor-travel-geo-ui/.next --exclude data --exclude artifacts \
  /mnt/f/dev/kor-travel-geo-codex/ ~/dev/kor-travel-geo-codex-test/
cd ~/dev/kor-travel-geo-codex-test
test -e data || ln -s /mnt/f/dev/geodata data

# 의존성 설치
uv venv && uv pip install -e ".[api,loaders,dev]"
test -f .env || cp .env.example .env       # KTG_PG_DSN, KTG_RUSTFS_* 채우기

# PostgreSQL/PostGIS와 RustFS는 이 프로젝트에서 직접 구동하지 않는다.
# 이미 동작 중인 DB와 bucket 접속 정보를 .env에 저장해 사용한다.

# 스키마 적용
ktgctl init-db

# 전국 적재 (텍스트 원천 + 선택 SHP, 현재 CLI 옵션 형태)
ktgctl load all-sidos \
    --juso "./data/juso/도로명주소 한글_전체분" \
    --jibun "./data/juso/도로명주소 한글_전체분" \
    --locsum "./data/juso/위치정보요약DB" \
    --navi "./data/juso/내비게이션용DB" \
    --shp-root "./data/jusoMap/202605" \
    --yyyymm 202605

# full-load 이후 일변동 ZIP 적용
ktgctl load daily-juso ./data/juso/daily/20260401_dailyjusukrdata.zip
ktgctl load daily-parcel-links ./data/juso/daily/20260401_dailyjusukrdata.zip

# 선택: 도로명주소 출입구 정보 direct 좌표 적재
# 현재 로컬 원천은 202605 기준월이라 기본 full-load에는 자동 포함하지 않습니다.
# 기준월이 텍스트 정본과 다르면 적재는 되지만 serving MV 좌표에는 승격되지 않습니다.
ktgctl load roadaddr-entrances "./data/juso/도로명주소 출입구 정보" --yyyymm 202605
ktgctl refresh mv --swap

# 서비스 기동
uvicorn kortravelgeo.api.app:app --reload --port 12501

# Docker API/UI 빌드 및 실행 (GDAL 버전 매칭 포함)
scripts/docker_app.sh build
scripts/docker_app.sh up

# 운영 노드(N150/Odroid) 배포 계획 생성
python scripts/deploy_app.py plan --tag "$(git rev-parse --short HEAD)" --output-dir artifacts/deploy/t108
```

### 2. 프론트엔드 설정 (Next.js)

```bash
cd kor-travel-geo-ui
cp .env.local.example .env.local && $EDITOR .env.local   # NEXT_PUBLIC_VWORLD_API_KEY 설정
npm ci
npm run gen:types        # 백엔드 openapi.json → TypeScript 타입 생성
npm run dev -- --port 12505   # http://localhost:12505
```

> [!TIP]
> 운영 콘솔은 `/admin/load` 및 `/debug/geocode`로 바로 진입합니다. 지도 영역은 MapLibre GL JS와 VWorld WMTS를 사용하며, `/api/runtime-config`가 Python API `.env`의 `KTG_VWORLD_API_KEY`를 우선 읽어 전달합니다. Docker 실행은 `scripts/docker_app.sh`를 사용하며, 이 스크립트는 API/UI 컨테이너에 `.env`/`.env.local`의 VWorld 키와 DB/RustFS 접속 설정을 주입합니다. PostgreSQL/PostGIS와 RustFS bucket은 이미 동작 중인 외부 인프라로 간주하고 이 프로젝트에서 직접 정지/재시작하지 않습니다. MapLibre 렌더링은 GitHub `maplibre-vworld-react` package에 위임하고 별도 타일/렌더링 fallback은 두지 않습니다. 키가 없으면 지도 대신 좌표 프리뷰 UI를 보여 줍니다. 백엔드 API 요청은 `KTG_API_INTERNAL_URL`을 통해 Next.js Route Handler가 서버 측에서 프록시합니다.

---

## 🧭 진입점

- **Python 라이브러리**: `from kortravelgeo import AsyncAddressClient` — asyncio 컨텍스트 매니저
- **REST API**: `uvicorn kortravelgeo.api.app:app` — Swagger UI (`http://localhost:12501/v1/docs`)
- **Prometheus API metrics**: `http://localhost:12501/metrics` — v1/v2 API 요청 성능, DB pool/query, cache, load job/stage 메트릭
- **Prometheus UI metrics**: `http://localhost:12505/api/metrics` — Next.js route handler, backend proxy upstream, Web Vitals 메트릭
- **CLI**: `ktgctl --help` — `load`, `refresh`, `validate`, `healthz` 등
- **디버그/관리 UI**: `kor-travel-geo-ui` — 내부망 전용 디버깅 (ADR-013)

---

## 🛠️ 라이브러리 사용 예제

```python
import asyncio
from kortravelgeo import AsyncAddressClient

async def main() -> None:
    async with AsyncAddressClient() as client:    # .env에서 DSN 자동 로드
        # 지오코딩 (Geocode)
        r = await client.geocode(query="서울특별시 강남구 테헤란로 152")
        if r.status == "OK" and r.candidates:
            candidate = r.candidates[0]
            print(candidate.point)       # Point(x=127.028..., y=37.500...)
            print(candidate.address.full if candidate.address else None)
            print(candidate.source)      # 'local', 'vworld', 'juso', ...

        # 역지오코딩 (Reverse Geocode)
        rr = await client.reverse(127.028601, 37.500344, include_zipcode=True)
        for item in rr.candidates:
            print(item.match_kind, item.address.full if item.address else None, item.distance_m)

        # 행정구역 hint가 확실하면 후보 검색 범위를 줄일 수 있다.
        hinted = await client.geocode(query="테헤란로 152", sig_cd="11680")
        print(hinted.status)

asyncio.run(main())
```

> [!IMPORTANT]
> 본 라이브러리의 모든 인터페이스는 **async-only**입니다(ADR-002). 동기 컨텍스트에서 호출하려면 호출자가 직접 `asyncio.run` 등으로 감싸야 합니다.

---

## 📁 디렉토리 구조

| 경로 | 역할 |
|------|------|
| `src/kortravelgeo/dto/` | pydantic v2 I/O 모델 (DB·FastAPI 의존성 없음) |
| `src/kortravelgeo/core/` | DB 무관 비즈니스 로직 (Protocol 의존) |
| `src/kortravelgeo/infra/` | DB 어댑터 (SQLAlchemy 2 async + raw SQL) |
| `src/kortravelgeo/client.py` | `AsyncAddressClient` — 라이브러리 진입점 |
| `src/kortravelgeo/api/` | FastAPI 라우터 및 엔드포인트 |
| `src/kortravelgeo/loaders/` | 데이터 적재 파이프라인 (텍스트, SHP 등) |
| `src/kortravelgeo/cli/` | Typer 기반 CLI 명령어 |
| `alembic/`, `sql/` | 스키마 마이그레이션과 DDL |
| `tests/` | 단위 테스트(Fake Repo) 및 통합 테스트(testcontainers) |
| `docs/` | ADR, 사양서, 작업 기록 저장소 |
| `kor-travel-geo-ui/` | Next.js 16 기반 디버그 및 관리자 UI |

---

## 🏛️ 핵심 아키텍처 결정 (ADR)

| ADR | 주요 결정 사항 |
|-----|------|
| **ADR-001** | PostgreSQL + PostGIS 1차 저장소 채택 (SpatiaLite 폐기) |
| **ADR-002** | 라이브러리 외부 API는 오직 비동기(async)만 제공 |
| **ADR-003** | API 응답 구조는 vworld와 1:1 호환, 확장은 `x_extension`으로 분리 |
| **ADR-004** | 비즈니스 로직에 ORM 사용 금지, raw SQL Repository 패턴 강제 |
| **ADR-005** | SHP 적재는 GDAL Python binding만 허용 (`ogr2ogr` subprocess 금지) |
| **ADR-013** | 프론트엔드 UI는 사내 내부망 전용으로 애플리케이션 인증 제거 |
| **ADR-020** | 프론트엔드 지도는 VWorld WMTS + MapLibre GL JS 기반으로 채택 |
| **ADR-029** | 원천 자료 기준월은 source set으로 명시하고 혼합 적재는 확인 절차를 거침 |
| **ADR-030** | 적재 완료 DB 백업/복원은 병렬 directory dump + 압축 아카이브로 수행 |
| **ADR-031** | 전국 적재 후 쿼리 성능은 반복 벤치마크로 gate하고 보조 view/MV 도입을 허용 |
| **ADR-032** | VWorld/MapLibre 책임 경계를 정하고 `kor-travel-geo` 특화 기능은 이 저장소에서 구현 |
| **ADR-063** | 디버그 UI 지도는 GitHub `maplibre-vworld-react` 패키지를 소비 |
| **ADR-033** | 운영 메타데이터는 `ops` 스키마의 감사·스냅샷·릴리스 테이블로 관리 |
| **ADR-034** | AI 에이전트별 고정 Git worktree와 CodeGraph 인덱스를 사용 |
| **ADR-039** | Python 라이브러리는 후보 목록 API만 공개하고 `_v2` 접미사를 제거 |

전체 ADR 본문은 [`docs/decisions.md`](docs/decisions.md)에서 확인하실 수 있습니다.

---

## 🔗 외부 연동 REST API

본 패키지는 로컬 DB를 최우선으로 사용하며, 외부 API는 폴백(Fallback) 및 보조 용도로만 사용됩니다. 자세한 발급 절차 및 호출 정책은 [`docs/architecture/external-apis.md`](docs/architecture/external-apis.md)를 참조하세요.

| 서비스 | 환경변수 | 용도 |
|--------|---------|------|
| **vworld** | `KTG_VWORLD_API_KEY` | 지오코딩 폴백 및 통합 검색 |
| **juso 검색** | `KTG_JUSO_API_KEY` | 도로명/지번 검색 폴백 |
| **juso 좌표** | `KTG_JUSO_COORD_API_KEY` | 좌표 변환 폴백 (미설정 시 검색 키 재사용) |
| **epost** | `KTG_EPOST_API_KEY` | 사서함·다량배달처 우편번호 자동 다운로드 |
| **VWorld WMTS** | `KTG_VWORLD_API_KEY`, `NEXT_PUBLIC_VWORLD_API_KEY` | 디버그 UI(`kor-travel-geo-ui`) 지도 렌더링용. Python API `.env`의 `KTG_VWORLD_API_KEY`를 우선 사용하고, 없으면 UI 전용 키를 사용 |

---

## ⚖️ 법적 고지 및 데이터 사용 한계

> [!CAUTION]
> 이 저장소의 **MIT 라이선스**는 저장소에 포함된 소스 코드와 문서에만 적용됩니다. 도로명주소 전자지도, juso, epost, vworld 등 외부 원천 데이터와 API 응답은 각 제공 기관의 이용약관, 저작권, 재배포 조건을 강력히 따릅니다.

- 본 프로젝트는 한국 주소 지오코딩 도메인을 대상으로 AI 활용 방식과 개발 워크플로를 학습·검증하기 위한 기술 연구 프로젝트입니다.
- 프로젝트에서 사용하는 외부 원천 데이터와 API는 각 제공 기관의 이용약관, 저작권, 재배포 조건, 호출 한도를 준수하는 것을 전제로 하며, 원천 데이터 자체를 저장소에 포함하지 않습니다.
- 원천 ZIP/SHP/TXT, 외부 API 응답 캐시, 내려받은 우편번호 파일은 본 저장소에 커밋하지 마십시오.
- 운영자는 도로명주소 안내시스템, 공공데이터포털, vworld의 최신 약관과 API 호출 한도를 직접 확인하고 관리해야 합니다.
- 본 패키지는 주소 정규화 및 지오코딩을 돕는 '기술적 도구'에 불과하며, 토지·건축물·행정구역 경계의 법적 효력이나 공적 증명을 보장하지 않습니다. 법적 판단이 필요한 업무는 해당 기관의 공식 고시를 기준으로 검증하십시오.

디버그 UI 지도는 MapLibre GL JS + VWorld WMTS를 사용합니다. `kor-travel-geo-ui`는 [`digitie/maplibre-vworld-react`](https://github.com/digitie/maplibre-vworld-react) GitHub tarball을 package dependency로 소비합니다. 2026-06-18 현재 npm registry에는 공개 package가 없어 commit `a7cb0f8f41ec00b44b1d106664506730b87033bd` tarball로 고정합니다. `CoordinateMap`은 upstream `VWorldMapView`/`Marker`/hook을 감싸는 domain wrapper로 두고, VWorld layer/style, marker primitive, tile error redaction, 패키징 문제처럼 범용 기능은 upstream에서 소비합니다. MapLibre를 대체하는 별도 지도 fallback 구현은 두지 않습니다. 지오코딩/역지오코딩 디버그 입력 연결, 정합성·성능·적재 overlay, 관리 UI 전용 UX처럼 이 저장소 특화 기능은 `kor-travel-geo-ui`에 남깁니다.

---

## 🤝 기여하기 (Contributing)

1. **반드시** [`SKILL.md`](SKILL.md)를 먼저 읽고 프로젝트 원칙을 숙지합니다.
2. [`docs/tasks.md`](docs/tasks.md)에서 진행할 항목을 선택하고, [`docs/resume.md`](docs/resume.md)로 현재 상태를 확인합니다.
3. 작업 완료 후 [`docs/journal.md`](docs/journal.md) 엔트리를 추가하고 진척도를 갱신합니다.
4. 주요 아키텍처 결정이 있었다면 [`docs/decisions.md`](docs/decisions.md)에 새 ADR을 추가합니다.
5. 사용자에게 영향을 미치는 변경사항은 [`CHANGELOG.md`](CHANGELOG.md)에 기록합니다.

---

## 🗺️ 문서 지도 (Documentation Map)

* [`SKILL.md`](SKILL.md) — 에이전트 작업 매뉴얼 (DO NOT 규칙, 자주 묻는 작업 등)
* [`docs/architecture/architecture.md`](docs/architecture/architecture.md) — 패키지 간 계층 및 데이터 흐름도
* [`docs/decisions.md`](docs/decisions.md) — 아키텍처 의사결정 기록(ADR)
* [`docs/architecture/data-model.md`](docs/architecture/data-model.md) — PostgreSQL DB 스키마 Reference
* [`docs/architecture/backend-package.md`](docs/architecture/backend-package.md) — `kortravelgeo` 백엔드 사양서
* [`docs/architecture/frontend-package.md`](docs/architecture/frontend-package.md) — `kor-travel-geo-ui` 프론트엔드 사양서
* [`docs/optional-source-usage-decision.md`](docs/optional-source-usage-decision.md) — optional 원천 사용·미사용 최종 판정
* [`docs/agent-guide.md`](docs/agent-guide.md) — AI 에이전트 작업 가이드
* [`docs/architecture/external-apis.md`](docs/architecture/external-apis.md) — 외부 API 연동 가이드
* [`docs/tasks.md`](docs/tasks.md) / [`docs/resume.md`](docs/resume.md) / [`docs/journal.md`](docs/journal.md) — 백로그 및 작업 일지

---
*Powered by Python, PostgreSQL, PostGIS, and Next.js*
