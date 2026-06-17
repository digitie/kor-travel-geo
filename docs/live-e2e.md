# 라이브 풀스택 e2e (LIVE_E2E)

`kor-travel-geo-ui/tests/e2e/`의 기본 Playwright 스펙은 `page.route`로 백엔드를 mock해 DB/백엔드
없이 UI 계약만 검증한다. 그것과 별개로 `tests/e2e/live/*`는 **실 백엔드 + 실 DB**를 끝까지 통과하는
풀스택 e2e다. 실제 지오코딩 정확성(주소→좌표), 구조화 에러, admin 화면의 실데이터 렌더를 검증한다.

이 스펙들은 `LIVE_E2E` 환경변수로 **게이트**된다 — 변수가 없으면 `test.skip`되어 기본 mock 런(백엔드
없음)에서 실패하지 않는다.

## 커버리지 (4계층)

| 파일 | 계층 | 내용 |
|------|------|------|
| `live/api-correctness.spec.ts` | 실 API 정확성 | v1(vworld 호환)·v2 geocode/reverse/search/within-radius + health. 알려진 앵커(서울시청)로 좌표·sig_cd·우편번호·bd_mgt_sn 단언 |
| `live/api-negative.spec.ts` | 네거티브/엣지 | 빈/누락 입력 → 구조화 400(`V2ErrorEnvelope` `error.code=E0100`), 존재하지 않는 주소 → 빈 후보 |
| `live/browser-flows.spec.ts` | 라이브 브라우저 | debug geocode/reverse/normalize 페이지를 실 입력→실행→결과로 구동(mock 없음) |
| `live/admin-readonly.spec.ts` | 라이브 admin | ops/consistency/backups/source-files/tables 화면이 실데이터로 렌더(읽기 전용 — 파괴적 작업 금지) |

## 스택 기동 (이 저장소에서 검증된 절차)

Docker 스택은 **WSL 내부**에서 돈다(WSL-native docker). 퍼블리시 포트는 Windows `localhost`가 아니라
**WSL IP**로 접근한다. Playwright 브라우저는 Windows에 있으므로, Windows next 서버가 WSL IP로 API를
프록시하고 Playwright는 Windows에서 12505로 붙는다.

```bash
# 1) DB (PostgreSQL+PostGIS, 적재 완료 데이터): 이미 떠 있으면 생략
#    공식 포트 15434 (ADR-040). 컨테이너 예: ktg-t210-db (postgis/postgis:16-3.5)

# 2) API 컨테이너 (현재 main에서 이미지 재빌드 → 현 DB 스키마와 일치)
wsl bash -lc 'cd /mnt/f/dev/kor-travel-geo-claude \
  && bash scripts/docker_app.sh build-api \
  && export KTG_VWORLD_API_KEY="$(grep -E ^KRADDR_GEO_VWORLD_API_KEY= .env | cut -d= -f2- | tr -d "\"")" \
  && KTG_DB_PORT=15434 KTG_GEOIP_GATE_MODE=off bash scripts/docker_app.sh up-api'
```

```powershell
# 3) 프런트엔드 (Windows): WSL IP로 프록시, VWorld 키 주입
cd kor-travel-geo-ui; npm run build
$wslip = (wsl -e bash -lc "hostname -I").Trim().Split(" ")[0]
$env:KTG_API_INTERNAL_URL = "http://$($wslip):12501"
$env:KTG_VWORLD_API_KEY = ((Get-Content ..\.env | Where-Object { $_ -match '^KRADDR_GEO_VWORLD_API_KEY=' }) -replace '^KRADDR_GEO_VWORLD_API_KEY=','').Trim().Trim('"')
npx next start -p 12505
```

```powershell
# 4) 라이브 e2e 실행 (Windows Playwright)
cd kor-travel-geo-ui
$env:LIVE_E2E = "1"; $env:PLAYWRIGHT_BROWSER = "chromium"
npx playwright test tests/e2e/live
```

기본 mock 런(`npx playwright test`, `LIVE_E2E` 없음)은 `live/*`를 건너뛰므로 영향 없다.

## 주의

- **앵커 주소**: `tests/e2e/live/_live.ts`의 `KNOWN`("서울특별시 중구 세종대로 110" = 서울시청)은 적재
  데이터에서 안정적으로 해석되는 ground-truth다. 데이터 재적재로 좌표가 바뀌면 갱신한다.
- **admin은 읽기 전용**: 백업/복원/rebuild/hard-delete 등 파괴적 작업은 라이브 스펙에서 절대 트리거하지 않는다.
- **VWorld 키**: `browser-flows`/지도 타일은 `.env`의 키(`KRADDR_GEO_VWORLD_API_KEY` 값을
  `KTG_VWORLD_API_KEY`로 주입)와 인터넷 접근이 필요하다.
- 스택 종료: `wsl bash -lc 'cd /mnt/f/dev/kor-travel-geo-claude && bash scripts/docker_app.sh down'` + 12505 next 서버 종료.

## 라이브에서 마주치는 알려진 제약 (실 스택 검증 중 발견)

라이브 e2e를 실 백엔드로 돌리면 mock 런에서는 안 보이던 아래 동작을 만난다. 라이브 admin 스펙이
"렌더+표 존재"까지만 단언하고 실데이터 행 수를 강제하지 않는 이유이기도 하다.

- **source-files/match-set admin → 403 (의도된 RBAC).** `GET /v1/admin/source-match-sets` 등 source-files
  도메인 read는 `require_role(source_file_viewer)`로 게이트된다(`api/security.py`). 신뢰되는
  `X-KTG-Actor`/`X-KTG-Roles` 헤더(admin CIDR 내 peer만 신뢰)가 없으면 403. 로컬 docker 스택의
  프록시는 이 헤더를 주입하지 않으므로 해당 패널은 에러 상태로 렌더된다(페이지는 정상). ops/consistency/
  backups read는 이 게이트가 없어 200. → source-files/match-set 실데이터까지 라이브로 검증하려면 프록시가
  역할 헤더를 주입하고 admin CIDR을 맞춰야 한다.
- **`/v1/admin/ops/pg-stat-statements` → 503.** 이 엔드포인트는 (1) `pg_stat_statements` 확장(백엔드는
  `x_extension.pg_stat_statements` 뷰를 조회)과 (2) `ops.pg_stat_statements_snapshots` 테이블 **둘 다**
  필요하다. 테스트 DB(`ktg-t210-db`)에 확장을 설치해도 snapshots 테이블이 누락돼 있으면 `E0500`로 503.
  스키마를 현재 `sql/ddl/001_schema.sql` 기준으로 정식 마이그레이션해야 해소된다(공유 DB 직접 DDL 금지).
  OpsPanel은 한 엔드포인트 503이 다른 표를 비우지 않도록 `Promise.allSettled`로 부분 로드한다.
- **v1 `type` 파라미터는 소문자만.** `type=ROAD`(대문자)는 `400 INVALID_TYPE`. 상세는
  `docs/api-reference/v1/geocode.md`·`reverse.md` 참조.
