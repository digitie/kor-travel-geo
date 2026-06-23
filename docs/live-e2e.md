# 라이브 풀스택 e2e (LIVE_E2E)

`kor-travel-geo-ui/tests/e2e/`의 기본 Playwright 스펙은 `page.route`로 백엔드를 mock해 DB/백엔드
없이 UI 계약만 검증한다. 그것과 별개로 `tests/e2e/live/*`는 **실 백엔드 + 실 DB**를 끝까지 통과하는
풀스택 e2e다. 실제 지오코딩 정확성(주소→좌표), 구조화 에러, admin 화면의 실데이터 렌더와
읽기 전용 admin/API 계약을 검증한다.

이 스펙들은 `LIVE_E2E` 환경변수로 **게이트**된다 — 변수가 없으면 `test.skip`되어 기본 mock 런(백엔드
없음)에서 실패하지 않는다.

## 커버리지 (10파일 / 230개 case)

| 파일 | case | 계층 | 내용 |
|------|------|------|------|
| `live/api-correctness.spec.ts` | 6 | 실 API 정확성 | v1(vworld 호환)·v2 geocode/reverse/search/within-radius + health. 알려진 앵커(서울시청)로 좌표·sig_cd·우편번호·bd_mgt_sn 단언 |
| `live/api-negative.spec.ts` | 5 | 네거티브/엣지 | 빈/누락 입력 → 구조화 400(`V2ErrorEnvelope` `error.code=E0100`), 존재하지 않는 주소 → 빈 후보 |
| `live/api-readonly-matrix.spec.ts` | 94 | 라이브 공개 API 행렬 | v1/v2 geocode·reverse·search·zipcode·pobox·within-radius와 검증 실패 케이스를 same-origin proxy로 촘촘히 확인 |
| `live/admin-api-query-matrix.spec.ts` | 48 | 라이브 admin API 행렬 | tables/logs/backups/jobs/loads/consistency/audit/snapshots/releases/artifacts/maintenance/pg-stat/cache/source catalog GET 계약을 읽기 전용으로 확인 |
| `live/admin-api-readonly.spec.ts` | 30 | 라이브 admin API 계약 | Next same-origin proxy를 통해 tables/cache/logs/backups/jobs/ops/consistency/source-file catalog를 실 백엔드+DB로 읽기 전용 검증. source-files role-gated read는 `source_file_viewer` opt-in일 때만 실행 |
| `live/admin-browser-readonly.spec.ts` | 29 | 라이브 admin 화면 촘촘 검증 | load/cache/logs/settings/tables/backups/source-files/ops/consistency의 주요 탭·표·필터·입력 surface를 실제 UI로 탐색하되 submit/action 버튼은 누르지 않음 |
| `live/auth-public-api-keys-live.spec.ts` | 7 | 로그인·세션·공개 API key | 미인증 redirect, 로그인 실패/성공/로그아웃, 감사 기록 노출, trusted UI proxy key 우회, 외부 직접 호출 key 요구, opt-in DB key 생성·폐기 |
| `live/browser-flows.spec.ts` | 3 | 라이브 브라우저 | debug geocode/reverse/normalize 페이지를 실 입력→실행→결과로 구동(mock 없음) |
| `live/admin-readonly.spec.ts` | 7 | 라이브 admin smoke | ops/consistency/backups/source-files/tables 화면이 실데이터로 렌더(읽기 전용 — 파괴적 작업 금지) |
| `live/source-files-rebuild-live.spec.ts` | 1 | 라이브 rebuild smoke | role-gated source-files rebuild 진입점의 라이브 경로 smoke |

`case`는 단일 Playwright project 기준이다. 현재 Chromium/Firefox 2 project 목록 기준으로는
`npx playwright test --config playwright.config.ts --list tests/e2e/live`가 460건을 출력한다.

## 최근 검증 (2026-06-23)

- 로컬 production Docker API/UI: `KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS=1` 기준 Chromium/Firefox 각 230건 중
  222 passed/8 skipped. 신규 `auth-public-api-keys-live.spec.ts`는 각 browser 7/7 통과.
- 운영 배포 후 API/UI: prod DB에 테스트 key row를 남기지 않기 위해 `KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS`를
  끄고 Chromium/Firefox 각 230건 중 221 passed/9 skipped. 추가 skip 1건은 UI key 생성·폐기 mutation
  케이스다.

## 스택 기동 (현재 dev 프로파일)

Git source of truth는 NTFS worktree이고, 의존성 설치·API/UI 서버 실행은 WSL ext4 테스트 미러에서 수행한다.
Playwright와 실제 브라우저만 Windows에서 실행한다. PostgreSQL/PostGIS와 RustFS는 이 저장소에서 직접
구동하지 않고, 이미 떠 있는 공용 인프라에 `KTG_PG_DSN`과 `KTG_RUSTFS_*`로 접속한다. 현재 dev 기본 포트는
API `12501`, UI `12505`다.

```bash
# 1) WSL ext4 테스트 미러에서 최신 NTFS worktree를 동기화하고 환경 보정
cd /mnt/f/dev/kor-travel-geo-codex
rsync -a --delete \
  --exclude .git --exclude .codegraph --exclude .venv \
  --exclude node_modules --exclude kor-travel-geo-ui/.next \
  --exclude data --exclude artifacts \
  ./ ~/dev/kor-travel-geo-codex-test/
cd ~/dev/kor-travel-geo-codex-test
test -e data || ln -s /mnt/f/dev/geodata data
source scripts/agent_env.sh

# 2) API 컨테이너. DB/RustFS는 이미 동작 중인 127.0.0.1 기준 인프라에 붙는다.
scripts/docker_app.sh build-api
KTG_ENV_FILE=.env.dev KTG_GEOIP_GATE_MODE=off KTG_FORCE_KILL=1 scripts/docker_app.sh up-api

# 3) UI 서버. Windows Playwright가 붙을 수 있도록 0.0.0.0으로 연다.
cd kor-travel-geo-ui
npm run build
npm run start -- --hostname 0.0.0.0 --port 12505
```

Admin UI live e2e는 실제 로그인을 수행한다. 비밀번호 평문은 Git에 두지 말고 Windows PowerShell
세션의 환경변수나 로컬 secret manager에서만 주입한다. `KTG_UI_ADMIN_PASSWORD_HASH`와
`KTG_UI_SESSION_SECRET`, `KTG_ADMIN_PROXY_SECRET`은 UI 서버가 읽는 `.env.local`에, 같은
`KTG_ADMIN_PROXY_SECRET`은 backend `.env`에 설정되어 있어야 한다.

> ⚠️ `KTG_ADMIN_PROXY_SECRET`처럼 Next 서버가 읽는 값은 step 3의 `npm run start` **전에** 같은
> PowerShell 세션이나 `.env.local`에 설정해야 한다. 서버를 이미 띄웠다면 중지한 뒤 설정하고
> `npm run start`를 다시 실행한다(서버 기동 후 설정하면 반영되지 않는다).

```powershell
# API가 Next proxy peer를 신뢰하도록 backend env에 설정한다. API와 UI가 같은 dev host에서
# 127.0.0.1로 통신하면 loopback만으로 충분하다. secret 값은 backend와 Next에 동일하게 둔다.
$env:KTG_ADMIN_TRUSTED_PROXY_CIDRS = "127.0.0.1/32,::1/128"
$env:KTG_ADMIN_PROXY_SECRET = "<same-random-admin-proxy-secret>"
```

```powershell
# 4) 라이브 e2e 실행 (Windows Playwright)
cd kor-travel-geo-ui
$env:LIVE_E2E = "1"; $env:PLAYWRIGHT_BASE_URL = "http://<WSL_IP>:12505"
$env:KTG_LIVE_E2E_ADMIN_USERNAME = "admin"
$env:KTG_LIVE_E2E_ADMIN_PASSWORD = "<local-admin-password>"
$env:KTG_LIVE_E2E_API_BASE_URL = "http://127.0.0.1:12501"

# DB에 공개 API key를 만들고 즉시 폐기하는 opt-in 케이스까지 실행할 때만 켠다.
$env:KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS = "1"
npx playwright test --config playwright.config.ts --project chromium --workers 1 tests/e2e/live
npx playwright test --config playwright.config.ts --project firefox --workers 1 tests/e2e/live
```

기본 mock 런(`npx playwright test`, `LIVE_E2E` 없음)은 `live/*`를 건너뛰므로 영향 없다.

## 주의

- **앵커 주소**: `tests/e2e/live/_live.ts`의 `KNOWN`("서울특별시 중구 세종대로 110" = 서울시청)은 적재
  데이터에서 안정적으로 해석되는 ground-truth다. 데이터 재적재로 좌표가 바뀌면 갱신한다.
- **admin은 읽기 전용**: 백업/복원/rebuild/hard-delete 등 파괴적 작업은 라이브 스펙에서 절대 트리거하지 않는다.
- **로그인 secret**: `KTG_LIVE_E2E_ADMIN_PASSWORD`는 테스트 실행 프로세스에만 주입한다. Git 추적 파일이나
  문서 예시에 실제 값을 적지 않는다.
- **공개 API key mutation**: `KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS=1`은 `ops.public_api_keys`에 키를 하나
  생성한 뒤 폐기한다. 실제 운영 DB에서 감사 흔적과 폐기 row가 남는 것을 허용할 때만 켠다.
- **VWorld 키**: `browser-flows`/지도 타일은 Python API `.env` 또는 프로세스 환경의
  `KTG_VWORLD_API_KEY`와 인터넷 접근이 필요하다. 키 값은 로그에 남기지 않는다.
- 스택 종료: WSL 미러에서 `scripts/docker_app.sh down`을 실행하고, `ss -ltnp | rg ':12505'`로
  UI 서버 PID를 확인해 종료한다.

## 라이브에서 마주치는 알려진 제약 (실 스택 검증 중 발견)

라이브 e2e를 실 백엔드로 돌리면 mock 런에서는 안 보이던 아래 동작을 만난다. 라이브 admin 스펙이
"렌더+표 존재"까지만 단언하고 실데이터 행 수를 강제하지 않는 이유이기도 하다.

- **source-files/match-set admin은 RBAC가 있다.** `GET /v1/admin/source-match-sets` 등 source-files
  도메인 read는 `require_role(source_file_viewer)`로 게이트된다(`api/security.py`). 현재 live e2e는
  먼저 Admin UI 로그인을 수행하고, Next proxy가 로그인된 요청에 `X-KTG-Actor`/`X-KTG-Roles`와
  `X-KTG-Admin-Proxy-Secret`을 주입한다. backend `KTG_ADMIN_TRUSTED_PROXY_CIDRS`와
  `KTG_ADMIN_PROXY_SECRET`이 맞지 않으면 403이다.
- **`/v1/admin/ops/pg-stat-statements` → 503.** 이 엔드포인트는 (1) `pg_stat_statements` 확장(백엔드는
  `x_extension.pg_stat_statements` 뷰를 조회)과 (2) `ops.pg_stat_statements_snapshots` 테이블 **둘 다**
  필요하다. 테스트 DB(`ktg-t210-db`)에 확장을 설치해도 snapshots 테이블이 누락돼 있으면 `E0500`로 503.
  스키마를 현재 `sql/ddl/001_schema.sql` 기준으로 정식 마이그레이션해야 해소된다(공유 DB 직접 DDL 금지).
  OpsPanel은 한 엔드포인트 503이 다른 표를 비우지 않도록 `Promise.allSettled`로 부분 로드한다.
- **v1 `type` 파라미터 검증은 실제 API 동작을 따른다.** 현재 live 스택에서는 `type=ROAD`가 정규화되어
  성공하고, 존재하지 않는 값(`not-a-type`)은 `400 INVALID_TYPE`으로 거절된다. 상세는
  `docs/api-reference/v1/geocode.md`·`reverse.md` 참조.
