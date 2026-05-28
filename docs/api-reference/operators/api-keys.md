# API Keys

## 환경변수

| Provider | 환경변수 | 사용 위치 |
|----------|----------|-----------|
| vworld | `KRADDR_GEO_VWORLD_API_KEY` | v1/v2 geocode fallback |
| juso 검색 | `KRADDR_GEO_JUSO_API_KEY` | v1/v2 geocode fallback |
| juso 좌표 | `KRADDR_GEO_JUSO_COORD_API_KEY` | juso 검색 결과 좌표 변환 |
| epost | `KRADDR_GEO_EPOST_API_KEY` | 우편번호 ZIP 다운로드 |

## Provider 문서

- vworld OpenAPI: `https://www.vworld.kr/dev/v4api.do`
- juso API: `https://business.juso.go.kr`

## 운영 원칙

- 키는 `.env`, systemd `EnvironmentFile`, vault 등 런타임 설정으로만 주입한다.
- Git에 평문 키를 커밋하지 않는다.
- 외부 API fallback은 로컬 DB가 `NOT_FOUND`일 때만 호출하므로, 운영 트래픽의 기본 경로는 계속 local DB다.

## v2 설계 참고 API

v2 schema는 Kakao Local, Naver Geocoding/Reverse, Google Geocoding/Places, VWorld OpenAPI의 표현 방식을 참고하지만, 이들을 직접 호출하지 않는다. live provider를 추가하려면 별도 task/ADR에서 키, quota, 약관, cache TTL, source 표기 정책을 먼저 정한다.
