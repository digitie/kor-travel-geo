# T-108 운영 배포 자동화

## 원문

`pinvi`의 `docs/tasks.md`에서 가져온 원문은 다음과 같다.

```text
- [ ] T-108 — 운영 배포 자동화 (Sprint 6) — **Odroid M1S + N150 16GB 양쪽**
  (ADR-023). multi-platform Docker 빌드 + 두 노드 streaming replication.
```

위 `(ADR-023)`은 `pinvi` 저장소의 ADR 번호다. 이 저장소의 ADR-023은 다른 주제이므로,
`kor-travel-geo`에서는 ADR-041(개발 worktree), ADR-045(DB/RustFS 외부 인프라),
ADR-048(로컬·Docker API/UI 포트), ADR-047(프로젝트 식별자)을 적용 기준으로 삼는다.

2026-06-13 사용자 추가 지시에 따라 **streaming replication은 이 작업에서 하지 않는다**.

## 적용 범위

이 저장소는 PostgreSQL/PostGIS와 RustFS를 직접 구동·정지·재시작하지 않는다. 따라서
T-108의 구현 범위는 다음으로 제한한다.

- API/UI Docker 이미지를 `linux/amd64`와 `linux/arm64` 멀티플랫폼으로 빌드하고
  registry에 push한다.
- N150(`linux/amd64`)과 Odroid(`linux/arm64`) 노드에 같은 이미지 태그를 배포한다.
- 각 노드는 로컬 파일로 관리되는 `--env-file`을 통해 `KTG_PG_DSN`,
  `KTG_RUSTFS_*`, `KTG_VWORLD_API_KEY`를 주입한다.
- 배포 후 API `/v1/healthz`와 UI `/api/runtime-config` smoke check를 실행한다.
- streaming replication 구성·확인·자동화는 이번 범위에서 제외한다.

## 스크립트

`scripts/deploy_app.py`를 추가했다. 기본 동작은 계획 파일을 만들거나 명시한 명령을
실행하는 형태다.

### 계획 생성

```bash
python scripts/deploy_app.py plan \
  --tag "$(git rev-parse --short HEAD)" \
  --node n150=deploy@n150.local,linux/amd64 \
  --node odroid=deploy@odroid.local,linux/arm64 \
  --output-dir artifacts/deploy/t108
```

산출물:

- `artifacts/deploy/t108/deploy-plan.json`
- `artifacts/deploy/t108/deploy-plan.md`

`--node`를 생략한 `plan`은 `deploy@n150.local`, `deploy@odroid.local` placeholder를
사용한다. 실제 `deploy`/`all` 실행에는 `--node`를 명시해야 한다.

### 멀티플랫폼 이미지 빌드

```bash
python scripts/deploy_app.py build \
  --registry ghcr.io/digitie \
  --tag "$(git rev-parse --short HEAD)" \
  --latest
```

생성되는 기본 이미지:

- `ghcr.io/digitie/kor-travel-geo-api:<tag>`
- `ghcr.io/digitie/kor-travel-geo-ui:<tag>`

기본 platform은 `linux/amd64,linux/arm64`이고 기본 output은 `--push`다. `--no-push`는
단일 platform 빌드에서만 허용한다.

### 노드 배포

```bash
python scripts/deploy_app.py deploy \
  --tag "$(git rev-parse --short HEAD)" \
  --remote-env-file /etc/kor-travel-geo/app.env \
  --remote-data-dir /data/kor-travel-geo \
  --node n150=deploy@n150.local,linux/amd64 \
  --node odroid=deploy@odroid.local,linux/arm64
```

노드의 `/etc/kor-travel-geo/app.env`는 Git에 커밋하지 않는다. 최소 예시는 다음과 같다.

```dotenv
KTG_PG_DSN=postgresql+psycopg://addr:addr@<postgres-host>:5432/kor_travel_geo
KTG_RUSTFS_ENABLED=true
KTG_RUSTFS_ENDPOINT_URL=http://<rustfs-host>:12101
KTG_RUSTFS_BUCKET=kor-travel-geo
KTG_RUSTFS_PREFIX=kor-travel-geo
KTG_RUSTFS_ACCESS_KEY=<secret>
KTG_RUSTFS_SECRET_KEY=<secret>
KTG_VWORLD_API_KEY=<secret>
KTG_GEOIP_GATE_MODE=strict
```

배포 스크립트는 원격 노드에서 다음 작업만 수행한다.

- Docker network 생성 또는 재사용
- 기존 API/UI 컨테이너 제거
- 새 API/UI 컨테이너 실행
- API/UI smoke check

DB/RustFS 프로세스나 replication 설정은 건드리지 않는다.

## 운영 순서

1. 같은 commit SHA에서 계획 파일을 생성해 build/deploy 명령을 리뷰한다.
2. registry 로그인과 `docker buildx` builder 상태를 확인한다.
3. `build`로 API/UI 이미지를 `linux/amd64,linux/arm64`에 대해 push한다.
4. N150에 먼저 배포하고 API/UI smoke check를 확인한다.
5. Odroid에 배포하고 API/UI smoke check를 확인한다.
6. T-063 실측 장비가 준비되면 `docs/t055-deployment-n150-odroid.md` runbook으로
   full-load, SQL/REST benchmark, MV refresh/swap, backup/restore를 측정한다.

## 검증

- `python -m pytest tests/unit/test_deploy_app.py -q`
- `python -m ruff check scripts/deploy_app.py tests/unit/test_deploy_app.py`
- `python scripts/deploy_app.py plan --tag test --output-dir <temp>`
- `git diff --check`
