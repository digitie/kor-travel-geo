# API Keys

## 환경변수

| Provider | 환경변수 | 사용 위치 |
|----------|----------|-----------|
| vworld | `KTG_VWORLD_API_KEY` | v1/v2 geocode fallback |
| juso 검색 | `KTG_JUSO_API_KEY` | v1/v2 geocode fallback |
| juso 좌표 | `KTG_JUSO_COORD_API_KEY` | juso 검색 결과 좌표 변환 |
| epost | `KTG_EPOST_API_KEY` | 우편번호 ZIP 다운로드 |

## Provider 문서

- vworld OpenAPI: `https://www.vworld.kr/dev/v4api.do`
- juso API: `https://business.juso.go.kr`

## 운영 원칙

- 키는 `.env`, systemd `EnvironmentFile`, vault 등 런타임 설정으로만 주입한다.
- Git에 평문 키를 커밋하지 않는다.
- 외부 API fallback은 로컬 DB가 `NOT_FOUND`일 때만 호출하므로, 운영 트래픽의 기본 경로는 계속 local DB다.

## 공개 REST API key

v1/v2 public endpoint는 Admin 역할과 분리된 공개 API key를 요구한다. 브라우저/VWorld 호환
클라이언트는 `key` query를, 서버 간 클라이언트는 `X-KTG-API-Key` header를 사용한다. 두 위치에
함께 보내면 값이 같아야 하고, 같은 위치에 반복한 key는 값이 같더라도 거부된다. key는 1~128자다.
header는 public endpoint 인증만 수행하며 Admin/ops 권한을 부여하지 않는다.

공개 key는 Admin UI 또는 `/v1/admin/public-api-keys`에서 생성·폐기한다. 평문은 생성 응답에서
한 번만 반환되고 DB에는 hash와 hint만 남는다. 활성 DB key가 없을 때만 `KTG_VWORLD_API_KEY`가
기본 공개 key로 동작한다.

## v2 설계 참고 API

v2 schema는 Kakao Local, Naver Geocoding/Reverse, Google Geocoding/Places, VWorld OpenAPI의 표현 방식을 참고하지만, 이들을 직접 호출하지 않는다. live provider를 추가하려면 별도 task/ADR에서 키, quota, 약관, cache TTL, source 표기 정책을 먼저 정한다.
