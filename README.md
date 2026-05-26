# 🗺️ python-kraddr-geo

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)
![Database](https://img.shields.io/badge/database-PostgreSQL%20%2B%20PostGIS-336791.svg)

**도로명주소 전자지도(PDF 사양)를 PostgreSQL + PostGIS에 적재해 제공하는 한국 주소 지오코딩 라이브러리·REST API**입니다. vworld OpenAPI와 호환되는 응답 구조를 유지하면서 자체 확장(`x_extension`)을 지원합니다. 사용자 대상 UI가 아닌 디버깅/관리 UI는 별도 Node.js 패키지 [`kraddr-geo-ui`](docs/frontend-package.md)로 운영합니다.

> [!NOTE]
> **현재 상태**: `main` 브랜치는 PostgreSQL + PostGIS 기반 재구현의 백엔드·REST·CLI와 `kraddr-geo-ui` 디버그/관리 UI를 포함합니다. T-005~T-041 구현·실데이터 검증 기록과 T-042~T-049 후속 운영/성능/자료 보강 계획이 문서화되어 있습니다. 이전 SpatiaLite 기반 구현(같은 `kraddr.geo` 패키지)은 `v1` 브랜치에 보존되어 있습니다(ADR-001).

---

## 📝 문서 언어

이 저장소의 Markdown/RST 문서는 **한국어**로 작성합니다. 공식 API 필드명, 코드 식별자, 명령어, URL, 패키지명처럼 그대로 보존해야 하는 값만 영문 원문을 유지합니다.

---

## 💻 개발 환경 (PC, WSL)

> [!WARNING]
> PC 개발은 반드시 **WSL의 ext4 파일시스템** 위에서 진행해야 합니다. NTFS 마운트(`/mnt/<drive>/...`) 위에서 직접 `git`/`pip`/`uvicorn`을 실행하면 파일 권한, inotify, 대량 I/O 성능이 극도로 저하됩니다.

```text
ext4 (개발):  ~/dev/python-kraddr-geo/                  ← 모든 코드/가상환경/테스트 (source of truth)
NTFS (백업): /mnt/<drive>/projects/python-kraddr-geo/  ← 작업 완료 후 카피, Windows에서 접근
```

- 작업이 완료되면 ext4 → NTFS로 카피하여 Windows에서도 접근 가능하게 보관합니다.
- **데이터(`data/`)는 NTFS 측에 보관합니다.** 도로명주소 ZIP/SHP, 대용량 자료는 모두 `data/` 하위에 둡니다.
- ext4 작업 디렉토리에는 대용량 데이터를 복사하지 않고, `ln -s /mnt/d/projects/python-kraddr-geo/data data` 처럼 **심볼릭 링크**를 걸어 사용합니다.

---

## 🚀 빠른 시작

### 1. 백엔드 설정 (Python)

```bash
# WSL ext4 작업 디렉토리에서
cd ~/dev/python-kraddr-geo

# 의존성 설치
uv venv && uv pip install -e ".[api,loaders,dev]"
cp .env.example .env && $EDITOR .env       # KRADDR_GEO_PG_DSN 채우기

# 데이터 심볼릭 링크 연결 (NTFS 경로 예시)
ln -s /mnt/d/projects/python-kraddr-geo/data data

# PostgreSQL + PostGIS 구동 (Docker 권장)
docker compose up -d postgres              # postgis/postgis:16-3.4

# 스키마 적용
kraddr-geo init-db

# 전국 적재 (텍스트 원천 + 선택 SHP, 현재 CLI 옵션 형태)
kraddr-geo load all-sidos \
    --juso "./data/juso/도로명주소 한글_전체분" \
    --jibun "./data/juso/도로명주소 한글_전체분" \
    --locsum "./data/juso/위치정보요약DB" \
    --navi "./data/juso/내비게이션용DB" \
    --shp-root "./data/jusoMap/202605" \
    --yyyymm 202605

# full-load 이후 일변동 ZIP 적용
kraddr-geo load daily-juso ./data/juso/daily/20260401_dailyjusukrdata.zip
kraddr-geo load daily-parcel-links ./data/juso/daily/20260401_dailyjusukrdata.zip

# 선택: 도로명주소 출입구 정보 direct 좌표 적재
# 현재 로컬 원천은 202605 기준월이라 기본 full-load에는 자동 포함하지 않습니다.
kraddr-geo load roadaddr-entrances "./data/juso/도로명주소 출입구 정보" --yyyymm 202605
kraddr-geo refresh mv --swap

# 서비스 기동
uvicorn kraddr.geo.api.app:app --reload --port 8000
```

### 2. 프론트엔드 설정 (Next.js)

```bash
cd kraddr-geo-ui
cp .env.local.example .env.local && $EDITOR .env.local   # NEXT_PUBLIC_VWORLD_API_KEY 설정
npm ci
npm run gen:types        # 백엔드 openapi.json → TypeScript 타입 생성
npm run dev              # http://localhost:3000
```

> [!TIP]
> 운영 콘솔은 `/admin/load` 및 `/debug/geocode`로 바로 진입합니다. 지도 영역은 MapLibre GL JS와 VWorld WMTS를 사용하며, `NEXT_PUBLIC_VWORLD_API_KEY`가 없으면 좌표 프리뷰로 대체됩니다. 백엔드 API 요청은 `KRADDR_GEO_API_INTERNAL_URL`을 통해 Next.js Route Handler가 서버 측에서 프록시합니다.

---

## 🧭 진입점

- **Python 라이브러리**: `from kraddr.geo import AsyncAddressClient` — asyncio 컨텍스트 매니저
- **REST API**: `uvicorn kraddr.geo.api.app:app` — Swagger UI (`http://localhost:8000/v1/docs`)
- **CLI**: `kraddr-geo --help` — `load`, `refresh`, `validate`, `healthz` 등
- **디버그/관리 UI**: `kraddr-geo-ui` — 내부망 전용 디버깅 (ADR-013)

---

## 🛠️ 라이브러리 사용 예제

```python
import asyncio
from kraddr.geo import AsyncAddressClient

async def main() -> None:
    async with AsyncAddressClient() as client:    # .env에서 DSN 자동 로드
        # 지오코딩 (Geocode)
        r = await client.geocode("서울특별시 강남구 테헤란로 152")
        if r.status == "OK":
            print(r.result.point)            # Point(x=127.028..., y=37.500...)
            print(r.refined.text)            # '서울특별시 강남구 테헤란로 152'
            print(r.x_extension.bd_mgt_sn)   # '11680101...'

        # 역지오코딩 (Reverse Geocode)
        rr = await client.reverse_geocode(127.028601, 37.500344, type="both")
        for item in rr.result:
            print(item.type, item.text, item.zipcode)

asyncio.run(main())
```

> [!IMPORTANT]
> 본 라이브러리의 모든 인터페이스는 **async-only**입니다(ADR-002). 동기 컨텍스트에서 호출하려면 호출자가 직접 `asyncio.run` 등으로 감싸야 합니다.

---

## 📁 디렉토리 구조

| 경로 | 역할 |
|------|------|
| `src/kraddr/geo/dto/` | pydantic v2 I/O 모델 (DB·FastAPI 의존성 없음) |
| `src/kraddr/geo/core/` | DB 무관 비즈니스 로직 (Protocol 의존) |
| `src/kraddr/geo/infra/` | DB 어댑터 (SQLAlchemy 2 async + raw SQL) |
| `src/kraddr/geo/client.py` | `AsyncAddressClient` — 라이브러리 진입점 |
| `src/kraddr/geo/api/` | FastAPI 라우터 및 엔드포인트 |
| `src/kraddr/geo/loaders/` | 데이터 적재 파이프라인 (텍스트, SHP 등) |
| `src/kraddr/geo/cli/` | Typer 기반 CLI 명령어 |
| `alembic/`, `sql/` | 스키마 마이그레이션과 DDL |
| `tests/` | 단위 테스트(Fake Repo) 및 통합 테스트(testcontainers) |
| `docs/` | ADR, 사양서, 작업 기록 저장소 |
| `kraddr-geo-ui/` | Next.js 16 기반 디버그 및 관리자 UI |

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
| **ADR-032** | `maplibre-vworld-js`는 최신으로 소비하고 `kraddr-geo` 특화 기능은 이 저장소에서 구현 |
| **ADR-033** | 운영 메타데이터는 `ops` 스키마의 감사·스냅샷·릴리스 테이블로 관리 |

전체 ADR 본문은 [`docs/decisions.md`](docs/decisions.md)에서 확인하실 수 있습니다.

---

## 🔗 외부 연동 REST API

본 패키지는 로컬 DB를 최우선으로 사용하며, 외부 API는 폴백(Fallback) 및 보조 용도로만 사용됩니다. 자세한 발급 절차 및 호출 정책은 [`docs/external-apis.md`](docs/external-apis.md)를 참조하세요.

| 서비스 | 환경변수 | 용도 |
|--------|---------|------|
| **vworld** | `KRADDR_GEO_VWORLD_API_KEY` | 지오코딩 폴백 및 통합 검색 |
| **juso 검색** | `KRADDR_GEO_JUSO_API_KEY` | 도로명/지번 검색 폴백 |
| **juso 좌표** | `KRADDR_GEO_JUSO_COORD_API_KEY` | 좌표 변환 폴백 (미설정 시 검색 키 재사용) |
| **epost** | `KRADDR_GEO_EPOST_API_KEY` | 사서함·다량배달처 우편번호 자동 다운로드 |
| **VWorld WMTS** | `NEXT_PUBLIC_VWORLD_API_KEY` | 디버그 UI(`kraddr-geo-ui`) 지도 렌더링용 |

---

## ⚖️ 법적 고지 및 데이터 사용 한계

> [!CAUTION]
> 이 저장소의 **MIT 라이선스**는 저장소에 포함된 소스 코드와 문서에만 적용됩니다. 도로명주소 전자지도, juso, epost, vworld 등 외부 원천 데이터와 API 응답은 각 제공 기관의 이용약관, 저작권, 재배포 조건을 강력히 따릅니다.

- 본 프로젝트는 한국 주소 지오코딩 도메인을 대상으로 AI 활용 방식과 개발 워크플로를 학습·검증하기 위한 기술 연구 프로젝트입니다.
- 프로젝트에서 사용하는 외부 원천 데이터와 API는 각 제공 기관의 이용약관, 저작권, 재배포 조건, 호출 한도를 준수하는 것을 전제로 하며, 원천 데이터 자체를 저장소에 포함하지 않습니다.
- 원천 ZIP/SHP/TXT, 외부 API 응답 캐시, 내려받은 우편번호 파일은 본 저장소에 커밋하지 마십시오.
- 운영자는 도로명주소 안내시스템, 공공데이터포털, vworld의 최신 약관과 API 호출 한도를 직접 확인하고 관리해야 합니다.
- 본 패키지는 주소 정규화 및 지오코딩을 돕는 '기술적 도구'에 불과하며, 토지·건축물·행정구역 경계의 법적 효력이나 공적 증명을 보장하지 않습니다. 법적 판단이 필요한 업무는 해당 기관의 공식 고시를 기준으로 검증하십시오.

디버그 UI 지도는 MapLibre GL JS + VWorld WMTS를 사용합니다. `kraddr-geo-ui`는 [`digitie/maplibre-vworld-js`](https://github.com/digitie/maplibre-vworld-js)의 최신 확인 SHA 또는 stable release를 package dependency로 소비합니다. VWorld layer/style, marker primitive, tile error redaction, 패키징 문제처럼 범용 기능은 upstream도 적극 수정 대상에 포함하고, 지오코딩/역지오코딩 디버그 입력 연결, 정합성·성능·적재 overlay, 관리 UI fallback처럼 이 저장소 특화 기능은 `kraddr-geo-ui`의 domain wrapper에서 구현합니다.

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
* [`docs/architecture.md`](docs/architecture.md) — 패키지 간 계층 및 데이터 흐름도
* [`docs/decisions.md`](docs/decisions.md) — 아키텍처 의사결정 기록(ADR)
* [`docs/data-model.md`](docs/data-model.md) — PostgreSQL DB 스키마 Reference
* [`docs/backend-package.md`](docs/backend-package.md) — `kraddr.geo` 백엔드 사양서
* [`docs/frontend-package.md`](docs/frontend-package.md) — `kraddr-geo-ui` 프론트엔드 사양서
* [`docs/agent-guide.md`](docs/agent-guide.md) — AI 에이전트 작업 가이드
* [`docs/external-apis.md`](docs/external-apis.md) — 외부 API 연동 가이드
* [`docs/tasks.md`](docs/tasks.md) / [`docs/resume.md`](docs/resume.md) / [`docs/journal.md`](docs/journal.md) — 백로그 및 작업 일지

---
*Powered by Python, PostgreSQL, PostGIS, and Next.js*
