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
- [통합 후속 geo590-review-james-r3-union-20261018.md](geo590-review-james-r3-union-20261018.md) — SHA256 b5cb2e3eff152cb64706d26bbef4d451cd9886500413d891423d97f89468e4f0
- [통합 후속 geo590-591-union-review-popper-r1.md](geo590-591-union-review-popper-r1.md) — SHA256 2e71dc88e6d2fb700f31e6361418d7b51af7f34dd77f58b0a19bf3e5f275b8a5

## #591 통합 최종 확인

#591 머지 후 bb6ef5ce의 두 독립 통합 리뷰도 OPEN0이며, 두 PostGIS integration
모듈과 각각의 최소 실행 수를 함께 유지한다. 작성자 관련43 PASS/Ruff 및 두 리뷰어의
별도 검증을 구분해 보존한다. [최종 통합 CI](union-ci.json) 5개 모두 성공했다.
배포/실제 운영 수용은 여전히 별도다.
