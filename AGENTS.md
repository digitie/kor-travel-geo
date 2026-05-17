# AGENTS.md

## 역할

이 저장소는 Juso/주소 파일과 VWorld 유사 geocoding 흐름을 로컬 SQLite/SpatiaLite 기반으로 제공하는 `kraddr.geo` 라이브러리입니다. 작업 전에 `README.md`와 관련 `docs/` 문서를 먼저 확인합니다.

## 지시 우선순위

1. 사용자 요청
2. 이 `AGENTS.md`
3. `README.md`와 `docs/` 문서
4. 기존 코드와 테스트
5. 최소한의, 되돌릴 수 있는 가정

## Provider API 사용 원칙

- 외부 API 관련 작업은 다른 구현보다 먼저 wrapper/adapter/gateway 지양 원칙을 확인하고 문서/코드에 반영한 뒤 진행합니다.
- downstream이 직접 사용할 안정된 public client, typed model, enum, helper를 제공합니다.
- 단순 전달용 wrapper, 장기 호환 alias, 임시 facade를 만들지 않습니다.
- VWorld fallback이 필요하면 `python-vworld-api`의 stable public API를 직접 사용하고, 부족한 geocoder/reverse geocoder 계약은 `python-vworld-api`에서 먼저 안정화합니다.
- TripMate나 `python-krtour-map`에서 필요한 주소/좌표/경계 계약이 부족하면 임시 wrapper를 만들지 않고 이 저장소의 public API를 먼저 안정화합니다.

## 검증

```bash
python -m pytest
python -m ruff check .
```
