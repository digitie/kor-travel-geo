# Geo589 merge-base 정정 addendum — 2026-10-18

정정 대상은 준비 manifest `geo589-review-manifest-20261018.json`(SHA256 `26891aa6764240b1de0817a07a4f4bbace0661d861faa445e7f1718c66883561`) 및 이를 참조한 초기 보고다. 원본은 변경하지 않았다.

초기 준비에서 GitHub PR의 `baseRefOid`를 비교 base로 표시했으나, 이는 당시 current main tip이며 실제 merge-base가 아니었다. 두 개를 구분하지 않은 준비 오류를 정정한다.

| 구분 | 확정 값 |
| --- | --- |
| 실제 merge-base | `d04befabe4c3877a2a93c2159e84de93d9730bc2` |
| 검토 head | `a6a9fcdf09656c29828113ada12cf2990d1d5d31` — 변경 없음 |
| 당시 GitHub baseRefOid/current main | `03269e2426beb0837b17a40726adc9a16f26b6a0` |
| current main과 head의 merge-tree | EXIT0, tree `6617fc944e22ca39f062cf73935ab1c6ff6ba857` |
| 실효 변경 | 8파일,145+/24- |

출처는 root가 별도 clone에서 확인하여 이번 정정 요청으로 전달한 Git 결과다. 이 addendum 작성자가 새로 clone·fetch·merge-tree·테스트를 실행한 결과는 아니다.

root 확인에 따르면 current main에는 D4 문서 commit `209bfc6` 및 #588 merge만 추가돼 있다. merge 결과의 ADR070·journal·resume·tasks는 current main과 bytes가 같다. 따라서 초기 head 대 current-main 비교에서 보일 수 있는 이 차이를 Geo589의 D4 삭제·되돌림으로 판정하면 안 된다. **D4=21600초 유지 결정은 보존된다.**

A/B 독립 리뷰의 공통 기준은 root가 정정한 **review manifest r2**, SHA256 `5f58be530c9b58b7e423f9ae2c6fc68ef40855780053e932bf07a031aaf52c92`다. 실제 merge-base 기준 제품 delta와 current-main에 정상 통합되는 결과를 구분해 검토해야 한다. 초기 manifest의 base 표기·비교 지시는 이 정정과 r2로 대체하며 초기 오류의 원문은 보존한다.

이 문서는 준비 입력의 정정이며 SOURCE_PASS·독립 리뷰 완료·머지·배포 수용 판정이 아니다. 원본 source/branch/index/WIP·PR 메타데이터·운영 상태는 변경하지 않았다.
