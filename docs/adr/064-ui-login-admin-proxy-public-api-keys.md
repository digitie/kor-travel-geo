# ADR-064: Admin UI 로그인과 공개 API key 관리를 둔다

- 상태: accepted
- 날짜: 2026-06-23
- 결정자: human

## 컨텍스트

ADR-013은 `kor-travel-geo-ui`를 내부망 전용으로 보고 애플리케이션 인증을 두지 않기로
했다. 이후 요구가 바뀌었다. Admin UI에는 단일 관리자 로그인이 필요하고, `/v1/admin/*`
백엔드 운영 API는 지정된 UI proxy에서 온 요청만 받아야 한다. 또한 vworld 호환 v1과 자체
v2 REST API는 외부/비신뢰 클라이언트에는 query parameter `key`를 요구해야 하며, key는
Web UI에서 랜덤 생성할 수 있어야 한다.

## 결정

Admin UI에는 단일 admin 세션 로그인을 둔다. 기본 계정명은 `admin`이고, password는 평문이
아니라 PBKDF2-SHA256 hash로 `kor-travel-geo-ui/.env.local` 또는 배포 env에만 둔다. 세션은
`httpOnly`/`SameSite=Strict` cookie에 HMAC 서명 payload를 저장하며, session secret도
gitignored env에만 둔다. payload에는 session id, 발급/만료 시각, audience/version,
user-agent fingerprint를 넣고, logout 시 현재 process의 revocation map에 session id를
등록한다. 로그인 실패는 backend audit 로그 기반 durable rate limit을 우선 적용하고, audit 조회가
불가능할 때는 process-local rate limit로 제한한다.

`/v1/admin/*`는 backend `require_role` gate를 전역 적용한다. backend는
`KTG_ADMIN_TRUSTED_PROXY_CIDRS` 안의 peer에서 온 `X-KTG-Actor`/`X-KTG-Roles`만 신뢰하고,
`KTG_ADMIN_PROXY_SECRET`이 설정되어 있으면 `X-KTG-Admin-Proxy-Secret`도 일치해야 한다.
Next.js `/api/proxy/*`는 로그인 세션을 다시 확인한 뒤 client가 보낸 `X-KTG-*`/cookie/auth
header를 전달하지 않고, 서버 env의 shared secret과 admin role header만 주입한다.

Next.js `/api/auth/login`과 `/api/auth/logout`은 backend trusted proxy endpoint
`POST /v1/admin/auth-events`로 로그인 시도·성공·실패·로그아웃 이벤트를 보낸다. backend는 이를
기존 append-only `ops.audit_events`에 `admin_auth.login`/`admin_auth.logout` action으로 저장한다.
시도 username, 결과 사유, next path는 redaction payload로 남기고, client IP와 user-agent는
원문 대신 hash 컬럼에만 저장한다. Admin UI는 `/admin/settings`에서 최근 로그인 기록을 조회한다.

공개 REST API key는 `ops.public_api_keys`에 저장한다. DB에는 SHA-256 hash, hint, 상태와 감사
metadata만 저장하고 plaintext key는 생성 응답에서 한 번만 반환한다. Admin UI 설정 화면은
로드/새로고침 때 DB 목록을 다시 조회하고, 생성 직후 plaintext key를 이 브라우저의 공개 API
요청 key로 저장한다. 공개 API key 검증은 요청마다 DB의 활성 key hash를 조회해 생성·폐기 상태를
즉시 반영한다.

v1/v2 REST API는 외부/비신뢰 클라이언트에 query parameter `key`를 필수로 요구한다. DB에
활성 공개 API key가 하나 이상 있으면 그 DB key만 유효하다. 활성 DB key가 아직 없으면
`KTG_VWORLD_API_KEY`가 기본 key로 동작한다. 단, admin API와 같은 trusted proxy identity
(`X-KTG-Actor`/`X-KTG-Roles`, optional `X-KTG-Admin-Proxy-Secret`)가 확인된 요청은 같은
로컬 운영 UI 흐름으로 보고 공개 API key 검증을 우회한다. v1은 vworld 호환 error envelope로,
v2는 구조화 error envelope로 실패를 반환한다.

## 근거

- 운영 UI는 비전문가도 다루는 관리 표면이므로 내부망 전제만으로는 충분하지 않다.
- backend가 trusted proxy peer와 shared secret을 함께 확인하면 browser가 admin header를
직접 위조해도 권한으로 인정되지 않는다.
- 공개 API key plaintext를 DB에 보관하지 않으면 DB 유출 시 즉시 사용 가능한 key가 노출되지
않는다.
- 공개 API key를 매 요청 DB 조회하면 다중 worker에서도 key 폐기가 즉시 반영된다.
- DB key가 없을 때 `KTG_VWORLD_API_KEY`를 기본값으로 유지하면 기존 vworld key 기반 운영을
중단 없이 시작할 수 있다.

## 결과(긍정)

- Admin UI가 로그인 없이 열리지 않는다.
- admin API는 지정 UI proxy를 통과한 요청만 정상 권한을 얻는다.
- 로그인 시도와 로그아웃 기록이 DB 감사 이벤트로 남고 UI에서 확인된다.
- 외부/비신뢰 v1/v2 클라이언트는 같은 `key` parameter 계약으로 호출할 수 있다.
- trusted proxy를 통과한 Admin UI의 공개 API 호출은 별도 `key` 없이도 동작한다.
- Web UI에서 공개 API key를 생성·폐기하고 목록을 확인할 수 있다.

## 결과(부정)

- 활성 DB key가 생긴 뒤 plaintext를 잃어버리면 다시 조회할 수 없다. 필요한 client에는 생성
  직후 복사해야 한다.
- 공개 API key 검증이 매 요청 DB 조회를 수행하므로 key 검증 hot path의 DB round-trip이 늘어난다.
- login/session secret과 admin proxy shared secret을 API/UI 양쪽 env에 맞춰야 한다.

## 후속

- (open) logout revocation map은 현재 UI process-local이다. 다중 UI worker 또는 무중단 재시작에서
  폐기 세션을 즉시 공유해야 하면 DB/공유 저장소 기반 session store로 분리한다.
