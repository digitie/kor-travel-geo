# Geo 데이터 지문 소스 검토·머지 기록

PR [#589](https://github.com/digitie/kor-travel-geo/pull/589)은 파생 region_radius_parts를 지문에서 제외하고 재생성 원천의 지문은 유지한다. 2026-10-18 04:12:48 UTC 머지 커밋은 047536dc4346c341af78410a0407b4e1ba25af49다.

## 판정과 검증 범위

- 실제 분기점 d04befabe4c3877a2a93c2159e84de93d9730bc2 → 검토 head a6a9fcdf09656c29828113ada12cf2990d1d5d31의 8파일 전체를 두 독립 리뷰어가 검토했다. 둘 모두 SOURCE PASS, 열린 P0/P1/P2=0이다.
- 각자의 실제 Git 소스 순수 coverage 검사 35개와 SQL 계약 검사 9개가 통과했다. 각자 옛 소스에서 새 회귀 2개 실패를 확인했고, James는 mutant 5개, Popper는 mutant 4개를 거절했다. 서로의 fixture·새 판정은 최종 확정 전 공유하지 않았다. 두 사람의 결과를 하나의 실행 수로 합산하지 않는다.
- backend/openapi/integration-postgis/dagster/frontend 원격 CI 5개 SUCCESS는 기존 제품 검증이다. 리뷰어는 PostGIS·운영·provider·UI를 새로 실행하지 않았다.
- 원천 geometry 요약의 기존 한계와 정의 변경에 따른 토큰 1회 변경을 수용한다. 같은 호스트 매 실행에서 비결정성이 실측됐다는 주장으로 확대하지 않는다. Popper의 비차단 P3에 따라 현재 CHANGELOG 표현을 관측/추정으로 정정했다.
- 기존 D4=21600 코드·유지 결정은 보존된다. 새로운 runtime·주기·튜닝 변경은 없다.

## 준비 오류와 정정

root의 최초 manifest는 current main03269를 실제 분기점으로 잘못 지정했다. 두 점 비교가 12파일이 되어 main에만 있던 D4 문서가 빠진 것처럼 보였으므로, 실제 merge-base d04와 예상 merge tree6617을 확인해 r2로 정정했다. d04→a6와 main03269→merge tree6617의 patch bytes가 같다.

r2의 root_merge_verification에는 존재하지 않는 ADR070 경로가 남아 있다. 최초 비교는 Git 조회 실패의 종료값을 확인하지 않아 빈 출력끼리 비교한 잘못된 근거였다. 이를 원문에 보존하고 보조 proof로 정정했다. 실제 docs/adr/070-odroid-host-and-empty-host-full-load.md 및 journal/resume/tasks는 성공한 Git 조회로 비교해 main과 merge tree bytes가 모두 같다. 두 리뷰어도 별도로 이 네 실제 경로를 확인했다. 초기 manifest·raw 보고서는 수정하지 않았다.

## 운영 잔여

이 기록은 소스 머지 완료다. 신규 이미지의 실제 API/CS 적용, 배포 후 활성 지문의 새 정의 재계산, Map/Concierge 첫 기준선 또는 기존 토큰 차이 처리, live API/UI 수용은 이 작업에서 미실행이다. 기존 토큰이 있는 소비자는 첫 기준선 0건 규칙으로 자동 초기화하지 않는다. 복원/rollback의 옛 정의 지문도 재계산 정책을 따른다.

Daemon은 사용자 지시대로 OFF를 유지하고 센서를 활성화하지 않는다. Geo #590/#591 후속, Track1/2 운영 완료, 수집 CPU/RSS 개선을 이 PR의 PASS에 포함하지 않는다. CPU·메모리 개선은 사용자 지시대로 모든 Track1/2 작업 종료 뒤 진행한다.

이 문서 PR은 docs/CHANGELOG만 바꾸며 CI 없이 처리한다. 원 작성자의 broken Git 포인터와 WIP를 고치지 않고 별도 Linux clone을 문서 브랜치 정본으로 사용했다. 원격 검토·머지는 Linux gh로 했으며 제품 테스트 미러에서 commit하지 않았다. 해당 clone의 CodeGraph 준비 결과는 journal에 남긴다.

## 원문 SHA256

각 파일은 외부 원본 bytes 그대로 보관했다. JSON의 과거 pending·준비 제한은 생성 시점의 범위이며 새 운영 금지나 완료 판정이 아니다.

| 파일 | SHA256 |
| --- | --- |
| [geo589-review-manifest-20261018.json](2026-10-18-fingerprint-closure/geo589-review-manifest-20261018.json) | 26891aa6764240b1de0817a07a4f4bbace0661d861faa445e7f1718c66883561 |
| [geo589-review-manifest-20261018-r1.json](2026-10-18-fingerprint-closure/geo589-review-manifest-20261018-r1.json) | f139278c729cfab31cecf003ac94dc355b11f61cc382c2713ffff20e7e09fa3f |
| [geo589-review-manifest-20261018-r2.json](2026-10-18-fingerprint-closure/geo589-review-manifest-20261018-r2.json) | 5f58be530c9b58b7e423f9ae2c6fc68ef40855780053e932bf07a031aaf52c92 |
| [geo589-d4-existing-path-proof-20261018.json](2026-10-18-fingerprint-closure/geo589-d4-existing-path-proof-20261018.json) | 6b75d1d0714af2d3ddb105a36f6699da42014ab2ca65c686c4d1fda68ad91d27 |
| [geo589-mergebase-correction-20261018.md](2026-10-18-fingerprint-closure/geo589-mergebase-correction-20261018.md) | 0290f2ed880f7f41912d974097caa9e3b83ea0927d41d0f33bc726d6fe3ddf34 |
| [geo589-review-james-r1.md](2026-10-18-fingerprint-closure/geo589-review-james-r1.md) | e2018b085b2bb366ecfd69770ab284c5583f4aff187dca7c5b63d90113ebc89c |
| [geo589-review-popper-r1.md](2026-10-18-fingerprint-closure/geo589-review-popper-r1.md) | f659aaf9615e1f57b8bdebe0971d2f663cd148e2622a7ef596dabec4210ca1f2 |
| [geo589-merge-receipt-20261018.json](2026-10-18-fingerprint-closure/geo589-merge-receipt-20261018.json) | 5c27809b4062526983f8dddd89be530e8a0431b8e9a5b631b9ed79b7e0d2da76 |
| [geo589-premerge-conversation-20261018.json](2026-10-18-fingerprint-closure/geo589-premerge-conversation-20261018.json) | 5fe54838e8ea8cf63c78b8e31b31a0b998f97abcf754f2fb89d91a900aedd09e |
