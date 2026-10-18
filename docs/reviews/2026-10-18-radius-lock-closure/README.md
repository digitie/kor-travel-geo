# #590 잠금 획득 재시도 검증

제품 커밋 fa3a779faa980cba621749f1a67c6ea8ddff7178.
독립 두 전체 리뷰와 후속 리뷰에서 열린 P0–P3는 없다.
잠금 충돌 재시도, 연결/SQL 준비 단계의 deadline 초과, 기존 lock_timeout 복원
반례를 수정했다. 작성자 관련37 PASS와 독립 A/B 각각50 PASS를 별도 보존한다.
정확 제품 커밋의 backend·Dagster·PostGIS integration·frontend·OpenAPI CI 5개가 성공했다.
문서 정산 CI는 사용자 지시에 따라 생략하며 제품 검증 결과를 새 문서 실행으로 세지 않는다.

2초 lock 대기·30초 간격·1시간 재시도 예산을 적용한다. 실제 LOCK 요청 직전까지
재시도 예산을 확인하지만 전체 재구축 시간 상한을 새로 보장하지 않는다.
D4=21600 및 daemon 중지는 유지한다. 실제 운영 배포·PG 잠금/응답시간 측정·
공개 UI 검증은 아직 미실행이며 source 통과와 운영 완료를 구분한다.

## 원문 증거

- [geo590-review-james-r1-20261018.md](geo590-review-james-r1-20261018.md) — SHA256 86de1b4bef06800d35fe830e823bcb9e438cca93e06eac7c3abe7ce1abc9fe27
- [geo590-review-james-r2-closure-20261018.md](geo590-review-james-r2-closure-20261018.md) — SHA256 bd8f708da8a2b8c7c06e4f9e5ad2a7a62b0fab401ad88a34fdacf21312ccae3a
- [geo590-review-popper-r1.md](geo590-review-popper-r1.md) — SHA256 088d1944702410a91ee68f6dfcb5033f11108910480b41c43b07e55fe783267e
- [geo590-review-popper-r2.md](geo590-review-popper-r2.md) — SHA256 9802dbb9fb74c7e1e8822e8164a3bc7b58a1decb56dafc1205834b75837927bc
- [제품 CI](source-ci.json)
