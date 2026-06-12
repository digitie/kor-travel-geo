# T-077 `kor-travel-geo` 식별자 전환

## 상태

- 상태: 구현 완료
- 작성일: 2026-06-12
- 갱신일: 2026-06-13
- 요청자: 사용자

## 목표

외부 노출 이름을 검색하기 쉽고 직관적인 `kor-travel-geo` 계열로 통일한다. 이전 이름 계열 표기는 코드, 설정, 변수명, 문서, 경로에서 더 이상 사용하지 않는다.

| 항목 | 목표 |
|------|------|
| GitHub 저장소 이름 | `kor-travel-geo` |
| Python 배포명 | `kor-travel-geo` |
| Python import root | `kortravelgeo` |
| 권장 import alias | `import kortravelgeo as ktg` |
| CLI 명령 | `ktgctl` |
| 환경변수 prefix | `KTG_*` |
| PostgreSQL DB 이름 | `kor_travel_geo` |
| RustFS bucket/prefix 기본값 | `kor-travel-geo` |
| API title / 배포명 | `kor-travel-geo` |
| Web UI 패키지 | `kor-travel-geo-ui` |
| Prometheus metric namespace | `kor_travel_geo_*` |
| callback/header prefix | `x-kor-travel-geo-*` |

`import kortravelgeo as ktg`가 자연스럽게 동작하려면 package root에서 `AsyncAddressClient`, 주요 DTO, 공개 enum/helper를 직접 노출해야 한다. 예시는 다음 형태를 목표로 둔다.

```python
import kortravelgeo as ktg

async with ktg.AsyncAddressClient() as client:
    response = await client.geocode("서울특별시 종로구 인사동")
```

## 범위

- `pyproject.toml`의 project name, package discovery, console script entrypoint를 새 식별자에 맞춘다.
- `src/kortravelgeo/` package root로 구현을 이동하고 내부 import를 일괄 갱신한다.
- FastAPI entrypoint와 Docker 실행 명령을 `kortravelgeo.api.app:app` 기준으로 바꾼다.
- `pyproject.toml`의 `import-linter`, `mypy`, pytest pythonpath, OpenAPI export script, benchmark/운영 스크립트의 import 경로를 갱신한다.
- CLI 명령은 `ktgctl`만 제공한다.
- 환경변수는 `KTG_*`만 사용한다. 이전 환경변수 prefix 호환 alias는 두지 않는다.
- PostgreSQL 기본 DB 이름과 테스트 DB 접두어는 `kor_travel_geo` 계열로 바꾼다.
- RustFS bucket/prefix/object key 기본값은 `kor-travel-geo` 계열로 바꾼다.
- README, `AGENTS.md`, `SKILL.md`, API reference, 개발/운영 문서의 현재 식별자 표와 예시를 새 이름으로 갱신한다.
- API 요청 latency histogram과 opt-in 성능 로그를 추가한다. 로그는 route template, method, status, elapsed_ms만 기록하고 query string/address payload를 남기지 않는다.
- 변경 뒤 설정파일, 변수명, 문서를 두 번 전수조사해 이전 명칭 잔여가 없는지 확인한다.
- wheel/sdist 설치 후 `import kortravelgeo as ktg`와 `ktg.AsyncAddressClient` 접근을 별도 테스트로 고정한다.

## 범위 밖

- GitHub 저장소 설정 화면에서 실제 repository slug를 바꾸는 관리 작업은 PR 코드 변경만으로 완료되지 않는다. 이 Task는 코드·문서·packaging·URL 참조를 `kor-travel-geo`로 맞추고, 실제 GitHub repo rename은 merge 직후 별도 관리 작업으로 처리한다.
- `kortravelgeo` 내부 도메인 모델과 기존 REST path(`/v1/address/*`, `/v2/*`)는 유지한다.

## 호환성 원칙

- 공개 릴리스 전 breaking rename으로 처리한다.
- 장기 호환용 이전 이름 facade, console script alias, 환경변수 alias, 단순 전달 wrapper는 두지 않는다. 필요하다는 사용자 결정이 생기면 별도 ADR로 예외를 기록한다.
- 한 PR 안에서 packaging, import 경로, 실행 entrypoint, 문서 예시를 함께 바꿔 중간 상태를 남기지 않는다.

## 구현 체크리스트

- [x] `src/kortravelgeo/` package root 생성 및 공개 API export 설계
- [x] 기존 코드 package를 `src/kortravelgeo/`로 이동
- [x] 전체 Python import 경로를 `kortravelgeo.*`로 갱신
- [x] `pyproject.toml` project name과 `ktgctl` script entrypoint 갱신
- [x] `import-linter` 계약을 새 계층 경로로 갱신
- [x] FastAPI, Docker, benchmark, OpenAPI export, Alembic env 경로 확인
- [x] `.env.example`, Settings, Docker, UI proxy/runtime config의 `KTG_*` 전환
- [x] PostgreSQL 기본 DB 이름 `kor_travel_geo` 전환
- [x] RustFS bucket/prefix 기본값 `kor-travel-geo` 전환
- [x] 성능 측정 metric/logging 추가 및 민감 입력 비기록 테스트
- [x] README, `AGENTS.md`, `SKILL.md`, `docs/*`의 현재 실행 예시 갱신
- [x] wheel/sdist 설치 smoke 추가: `import kortravelgeo as ktg`
- [x] 이전 명칭 전수조사 1차
- [x] 이전 명칭 전수조사 2차
- [x] `pytest -q`, `ruff check .`, `mypy`, `lint-imports`, Docker API/UI build, healthz/geocode/reverse smoke 통과

## 검증 기준

```bash
python -m pip install -e ".[api,loaders,dev]"
python - <<'PY'
import kortravelgeo as ktg

assert hasattr(ktg, "AsyncAddressClient")
PY

python -m pytest -q
python -m ruff check .
python -m mypy src/kortravelgeo
lint-imports
scripts/docker_app.sh build
scripts/docker_app.sh up
curl -fsS http://127.0.0.1:12201/v1/healthz
```

프론트엔드가 OpenAPI 생성 타입이나 API proxy 경로만 소비한다면 UI import 변경은 없을 수 있다. 그래도 Docker UI build와 `/debug/geocode` smoke는 함께 확인한다.

## 이전 명칭 감사 기준

이전 이름 계열 패턴은 source, tests, scripts, 설정 예시, 문서, UI package 경로에서 0건이어야 한다. 파일/디렉터리명도 같은 기준으로 검사한다. Git index에 남는 rename 전 삭제 경로는 `git add -A` 뒤 다시 확인한다.
