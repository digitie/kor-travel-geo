# ADR-004: ORM 위에 raw SQL Repository를 둔다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

## 컨텍스트
지오코딩 쿼리는 CTE와 윈도우 함수를 다용하고 EXPLAIN 결과를 손튜닝해야 한다. ORM의 표현력은 부족하고 디버깅이 어렵다.

## 결정
`infra/*_repo.py`는 `sqlalchemy.text()`로 raw SQL을 직접 실행한다. ORM 모델(`infra/models.py`)은 read-only 매핑 용도로만 둔다.

## 근거
- `text()`는 EXPLAIN 결과를 그대로 재현하기 쉬움
- 인덱스 hint, `SET LOCAL`을 자유롭게 사용 가능
- 안전성: pydantic DTO가 결과를 검증하므로 타입 누수 없음

## 결과(긍정)
- 쿼리 튜닝이 백엔드 PR 안에서 일관됨
- 새 인덱스 추가 시 ORM 매핑 갱신 불필요

## 결과(부정)
- 컬럼 변경 시 SQL을 손으로 갱신해야 함 → CI에서 컬럼 존재성 통합 테스트로 방어

## 후속
- (open) bulk INSERT에 SQLAlchemy Core를 쓸지 검토
