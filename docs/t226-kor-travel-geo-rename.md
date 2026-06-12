# T-226 Python 배포명·임포트명 전환

## 상태

- 상태: 대기
- 작성일: 2026-06-13
- 요청자: 사용자

## 목표

Python 패키지와 GitHub 저장소의 외부 노출 이름을 더 검색하기 쉽고 직관적인 이름으로 전환한다.

| 항목 | 현재 | 목표 |
|------|------|------|
| GitHub 저장소 이름 | `python-kraddr-geo` | `kor-travel-geo` |
| Python 배포명 | `python-kraddr-geo` | `kor-travel-geo` |
| Python import root | `kraddr.geo` | `kortravelgeo` |
| 권장 import alias | 없음 | `import kortravelgeo as ktg` |

`import kortravelgeo as ktg`가 자연스럽게 동작하려면 package root에서 `AsyncAddressClient`, 주요 DTO, 공개 enum/helper를 직접 노출해야 한다. 예시는 다음 형태를 목표로 둔다.

```python
import kortravelgeo as ktg

async with ktg.AsyncAddressClient() as client:
    response = await client.geocode("서울특별시 종로구 인사동")
```

## 범위

- GitHub 저장소 이름을 `kor-travel-geo`로 변경하고, repository URL, badge, issue/PR 링크, GitHub Actions 참조, 원격 URL 갱신 절차를 문서에 반영한다.
- `pyproject.toml`의 project name, package discovery, console script entrypoint를 새 import root에 맞춘다.
- `src/kraddr/geo/` 내부 구현을 `src/kortravelgeo/`로 이동하고 내부 import를 일괄 갱신한다.
- FastAPI entrypoint와 Docker 실행 명령을 `kortravelgeo.api.app:app` 기준으로 바꾼다.
- `pyproject.toml`의 `import-linter`, `mypy`, pytest pythonpath, OpenAPI export script, benchmark/운영 스크립트의 import 경로를 갱신한다.
- README, `AGENTS.md`, `SKILL.md`, API reference, 개발/운영 문서의 현재 식별자 표와 예시를 새 이름으로 갱신한다.
- rename 전후 성능 회귀를 확인할 수 있도록 성능 측정과 구조화 로깅 기능을 추가한다.
- wheel/sdist 설치 후 `import kortravelgeo as ktg`와 `ktg.AsyncAddressClient` 접근을 별도 테스트로 고정한다.

## 범위 밖

- PostgreSQL DB 이름 `kraddr_geo`, 환경변수 prefix `KRADDR_GEO_*`, Web UI 패키지명 `kraddr-geo-ui`, Docker image/container 이름은 이번 사용자 요청에 포함되지 않았다. 구현 전 유지/변경 여부를 명시적으로 확인한다.
- 로컬 NTFS worktree 디렉터리 이름 변경은 GitHub 저장소 이름 변경과 별도 작업이다. 필요하면 에이전트별 worktree 정책과 함께 별도 절차로 다룬다.
- 과거 작업 일지, 성능 산출물, PR 회고 문서의 기존 이름은 당시 재현 정보이므로 현재 실행 문서가 아닌 한 일괄 변경하지 않는다.

## 호환성 원칙

- 공개 릴리스 전 breaking rename으로 처리한다.
- 장기 호환용 `kraddr.geo` facade나 단순 전달 wrapper는 두지 않는다. 필요하다는 사용자 결정이 생기면 별도 ADR로 예외를 기록한다.
- 한 PR 안에서 packaging, import 경로, 실행 entrypoint, 문서 예시를 함께 바꿔 중간 상태를 남기지 않는다.
- GitHub 저장소 rename은 GitHub redirect에만 의존하지 않고, 문서와 remote URL 갱신 절차를 명시한다.
- 성능 측정과 로깅은 주소 원문, API key, DSN, secret을 남기지 않는다. 필요한 경우 query fingerprint, 후보 수, 상태, latency, error code처럼 재현에 필요한 최소 메타데이터만 기록한다.

## 성능 측정·로깅 추가 범위

rename은 외부 도입 지점이 크게 바뀌는 작업이므로, 같은 PR 또는 바로 이어지는 하위 PR에서 최소 관측성을 함께 갖춘다.

- API 요청 단위 구조화 로그를 추가한다. 필수 필드는 `request_id`, route template, HTTP status, elapsed ms, candidate count, source kind, error code다.
- Python client 호출 단위 성능 로그를 opt-in으로 남길 수 있게 한다. 기본값은 비활성화하고, 활성화 시에도 주소 원문은 기록하지 않는다.
- 기존 benchmark script와 REST smoke가 새 `kortravelgeo` import root, 새 repository name, 새 artifact naming을 사용하게 한다.
- benchmark artifact는 JSON/JSONL로 남기고, rename 전 기준값과 rename 후 결과를 비교할 수 있게 summary schema를 고정한다.
- 실패 로그는 redaction helper를 통과한다. VWorld/Juso/Epost key, PostgreSQL DSN, RustFS credential, 업로드 local path는 원문으로 남기지 않는다.
- CI 또는 선택형 로컬 테스트에서 최소 smoke를 실행한다: healthz, geocode, reverse, UI proxy, runtime-config, benchmark script dry-run.

## 구현 체크리스트

- [ ] GitHub 저장소 이름 변경 계획과 remote URL 갱신 절차 문서화
- [ ] `src/kortravelgeo/` package root 생성 및 공개 API export 설계
- [ ] `src/kraddr/geo/` 코드 이동 또는 package 구조 재작성
- [ ] 전체 Python import 경로를 `kortravelgeo.*`로 갱신
- [ ] `pyproject.toml` project name과 script entrypoint 갱신
- [ ] `import-linter` 계약을 새 계층 경로로 갱신
- [ ] FastAPI, Docker, benchmark, OpenAPI export, Alembic env 경로 확인
- [ ] README, `AGENTS.md`, `SKILL.md`, `docs/*`의 현재 실행 예시 갱신
- [ ] historical 문서에서 보존할 이전 이름과 현재 실행 문서에서 바꿀 이름을 분리
- [ ] API request structured logging 추가
- [ ] Python client opt-in performance logging 추가
- [ ] benchmark artifact naming과 summary schema를 `kor-travel-geo` 기준으로 갱신
- [ ] secret/address redaction 회귀 테스트 추가
- [ ] wheel/sdist 설치 smoke 추가: `import kortravelgeo as ktg`
- [ ] `pytest -q`, `ruff check .`, `mypy`, `lint-imports`, Docker API/UI build, healthz/geocode/reverse smoke 통과

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
python scripts/benchmark_api_latency.py --base-url http://127.0.0.1:12201 --limit 1 --dry-run
scripts/docker_app.sh build
scripts/docker_app.sh up
curl -fsS http://127.0.0.1:12201/v1/healthz
```

프론트엔드가 OpenAPI 생성 타입이나 API proxy 경로만 소비한다면 UI import 변경은 없을 수 있다. 그래도 Docker UI build와 `/debug/geocode` smoke는 함께 확인한다.

## 남은 결정

- CLI 명령을 기존 `kraddr-geo`로 유지할지, 배포명과 맞춰 `kor-travel-geo`로 바꿀지 결정해야 한다.
- 환경변수 prefix `KRADDR_GEO_*`를 유지할지 새 prefix를 둘지 결정해야 한다.
- DB 이름 `kraddr_geo`를 유지할지 운영 rename 계획에 포함할지 결정해야 한다.
- Web UI 패키지명까지 맞출지 결정해야 한다.
- 성능 측정/로깅 기능을 T-226 본 PR에 포함할지, T-226 하위 PR로 분리할지 결정해야 한다.
