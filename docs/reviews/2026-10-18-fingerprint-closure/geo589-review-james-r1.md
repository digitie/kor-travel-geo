# Geo589 독립 James FULL API·소비자 token 계약 리뷰 r1

판정: **PASS — SOURCE_AND_OWN_PURE_FIXTURE_ONLY**.
OPEN P0=0 / P1=0 / P2=0. 새 제품 차단 결함을 발견하지 못했다.
수용한 geometry 요약 한계와 운영 미실행을 아래에 분리한다. 운영/Track1 전체 완료 판정이 아니다.

## 불변 입력·시각·격리

- 실제 시작 UTC 2026-10-18T04:02:53.029140+00:00.
- 독립 no-checkout clone /home/digitie/dev/kor-travel-geo-codex-track-review-20261018.
- 최종 base d04befabe4c3877a2a93c2159e84de93d9730bc2 → exact head a6a9fcdf09656c29828113ada12cf2990d1d5d31.
- 최종 manifest /home/digitie/dev/geo589-review-manifest-20261018-r2.json 실제 SHA256
  5f58be530c9b58b7e423f9ae2c6fc68ef40855780053e932bf07a031aaf52c92. 요청과 일치.
- superseded r1 manifest 실제 SHA256 f139278c729cfab31cecf003ac94dc355b11f61cc382c2713ffff20e7e09fa3f도 직접 확인했다.
- WSL Ubuntu-26.04 Linux Git/Python만 사용. 공유 clone에는 checkout/branch/index/source/metadata 변경을 하지 않았다.
  Git show/diff/ls-tree/rev-parse와 root가 이미 만든 merge tree 읽기만 사용했다. git merge-tree를 새로 실행해 object를 쓰지도 않았다.
- 제품 source·tests·SQL을 exact Git blob에서 본인 TemporaryDirectory로 가져와 실행했다.
  공개 read-only Common venv Python3.12의 -I -B, sterile HOME/TMPDIR/PATH, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1을 사용했다.
  pytest --noconftest -c /dev/null -p no:cacheprovider로 repo conftest와 자동 plugin을 차단했다.
  Geo root __init__의 client/app/settings import를 피하도록 소유 fixture의 package namespace 경로만 지정했고,
  fingerprint/SQL/core 모듈 본문은 수정하지 않았다. 알고리즘이나 SQL 결과를 mock으로 재구현하지 않았다.
- AGENTS.md, README의 정본 라우터, SKILL.md, 공개 agent-workflow/agent-failure-patterns, architecture 및
  ADR069 D1–D9/개정·ADR043, 관련 resume/tasks 절을 Git object로 읽었다.
  로컬 private runbook/env/키/원천 실데이터/DB/SDK/SSH/provider/Docker/Daemon/새 CI 접근0.
- 다른 새 Geo589 리뷰 결과/모형을 읽거나 요청하지 않았다. 감사·commit의 '리뷰 반영'은 독립 PASS로 계수하지 않았다.

## 초기 범위 오류와 정정의 독립 확인

최초 요청의 current-main03269→head 두 점 diff는 실제 12파일148+/40-였다.
따라서 root에 즉시 manifest8과 불일치를 알리고 최종 판정 고정을 보류했다.
root는 실제 분기점 d04와 currentmain의 D4 문서 추가 커밋을 구별해 r2를 제공했다.

본인이 직접 확인한 결과:

- d04..a6는 정확8파일145+/24-이고 manifest 경로 집합과 같다.
- currentmain03269e2426beb0837b17a40726adc9a16f26b6a0..root merge-tree
  6617fc944e22ca39f062cf73935ab1c6ff6ba857의 diff는 위 diff와 전 bytes 동일하다.
- 올바른 docs/adr/070-odroid-host-and-empty-host-full-load.md 및 journal/resume/tasks의 기존 blob은
  currentmain과 merge-tree에서 모두 같다. check_output 성공 종료를 확인한 실제 존재 경로로 대조했다.
- r2 root_merge_verification의 최초 ADR070 path가 nonexistent host-move.md였던 입력 오류도 root가 정정했다.
  보조증거 SHA256 6b75d1d0714af2d3ddb105a36f6699da42014ab2ca65c686c4d1fda68ad91d27를 읽고 확인했다.
  본인은 그 잘못된 경로의 빈 stdout equality를 근거로 삼지 않았다.
- 이 두 준비 오류를 제품이 D4를 삭제하는 P2로 단정하지 않는다. D4=21600 결정 및 runtime recovery.py는 보존된다.
  main의 문서 추가가 branch head 자체에 없는 것은 merge의 삭제와 다르다.

## 8파일 전수 delta와 실제 API 연결

manifest의 8개 head blob SHA1/SHA256/bytes를 모두 재계산해 일치했다. 전체 diff를 읽었다.
제품 변경은 data_fingerprint.py의 region_radius_parts spec 제거와 사유 있는 allowlist 추가뿐이다.
동 파일의 11개 함수/클래스 AST는 base와 전부 동일하다. fingerprint SQL 구성·savepoint·오류·schema drift
함수나 token 인코딩·API 인증/DTO/캐시·activation/CLI 정책을 함께 바꾸지 않는다.
core/dataset_version.py, admin_repo.py, dataset_ref.py, dataset router, SQL, postload, batch_dag, CLI,
Dagster recovery.py의 base/head bytes도 직접 동일 확인했다.

1. data_fingerprint.py:77–118 대상은 mv_geocode_target, tl_scco 4표, 건물 polygon, makarea, 도로 manage의 8표다.
   :121–133은 text-search MV와 radius parts를 이유 있는 파생 예외로 명시한다.
   unit coverage:124–139는 실제 infra/*_repo.py FROM/JOIN 집합에서 이 예외를 뺀 집합과 양방향 동등성을 검사한다.
   repo module allowlist는 비v2 admin/file/upload/pobox/zipcode이고 실제 AsyncAddressClient의 v2 closure까지 대조한다.
2. sql.py:1282–1335의 실제 radius 재생성 SQL은 tl_scco_ctprvn/sig/emd만 읽고 code/name/parent를 유도한다.
   parent code는 원천 code의 prefix, geometry는 ST_Subdivide(geom,256), part_no는 면적 정렬 row_number다.
   code/name은 원천 spec에서 그대로 hash되므로 원천 명칭/코드 변화가 빠지는 새 경로를 찾지 못했다.
3. geometry_repo.py:320–363의 radius 후보는 실제 parts를 읽는다. 그래서 제외는 '읽지 않는 표'라는 주장이 아니라
   ADR043의 같은 release 재생성 불변식에 기댄 명시적 예외다.
   CLI shp:506–510/shp-all:547–550은 refresh 후 release 기록,
   batch_dag.py:352 및 standalone release:476–479, postload.py:55–115의 두 refresh 전략도 재생성을 연결한다.
   raw psql로 원천만 변경/파생 표만 임의 훼손하는 경로는 ADR043:37에서 금지한 비표준 경로이며 이 PR이 복구를 보장하지 않는다.
4. data_fingerprint.py:136–165는 table 이름과 표별 hash 합을 정렬해 최종 fingerprint를 만든다.
   파생 표 branch 자체를 빼므로 part_no·재분할·metadata만 달라진 rebuild는 새 정의 안에서 token에 영향을 주지 않는다.
   원천 8표의 실제 직렬화 및 summary는 그대로 남는다.
5. admin_repo.py:851–873은 활성 snapshot의 fingerprint에서 token을 투영하고, dataset router는
   POST /v2/dataset/version·history에 기존 public auth와 Cache-Control no-store를 유지한다.
   version_token 기반 changed 필드는 기존 호환 의미이고, data_token을 대신하는 새 판정값을 추가하지 않는다.
6. activation helper는 fingerprint scan→잠금→superseded 검사→원장/cache clear 흐름을 보존한다.
   실패 시 NULL/notes를 기록하고 API는 absent token을 생략하는 기존 '판정 불가' 계약이다.
   fingerprint-active는 기존 활성 snapshot 1개를 재계산하고 성공 시 cache를 지운다. 이번 source 리뷰가 이를 실행하지는 않았다.

## 민감도·소비자 상태 계약 공격

- **원천 geometry 내부 경계 한계**: _row_expression:139–141은 ST_NPoints와 Box2D만 본다.
  정점 수·bbox가 같은 내부 경계 변경은 원천 summary를 유지할 수 있으며, 이번 제외로 예전 조각별 summary가
  우연히 잡던 일부 변화도 잃는다. ADR069:438–443은 이 확대된 blind spot을 직접 수용한다고 적는다.
  점 pt_5179는 여전히 WKB hash다. exact geometry 감지나 모든 within-radius 결과 변경 감지를 보장한다고 해석하지 않는다.
  이 결정의 수용 한계를 숨기는 새 결함으로는 판단하지 않는다. PostGIS 실 geometry 결과를 본인 fixture로 재현하지 않았다.
- **정의 변경 1회**: 9표와 8표는 table 이름까지 fingerprint 입력에 넣으므로 같은 데이터라도 old/new token이 한 번 달라지는 것이 맞다.
  '같은 원천 rebuild 불변'은 같은 새 정의끼리의 비교다. old9표와 new8표까지 같아야 한다는 잘못된 수용조건을 두지 않는다.
  ADR069:449–455/버전 API 문서:115–117에 이를 적고 dd1- 호환 형식은 유지한다.
- **hot-swap/rollback**: 옛 DB/backup의 저장 fingerprint를 재사용하면 old 정의 token이 다시 나올 수 있다.
  문서는 재계산 CLI와 badge의 인접 token 비교 차이를 설명한다. 영구히 단1회만 변한다고 과장하지 않는다.
- **기존 소비자 vs 첫 baseline**: ADR069:240–255의 absence→첫값 저장만, 둘 다 존재하고 다름→재해석을 구분한다.
  이미 token을 저장한 소비자가 정의 변경 후 새 token을 받으면 기존 규약상 다름이지 자동 초기화/첫 baseline이 아니다.
  개정문의 '현재 baseline0건'은 작성 시점의 외부 관측으로만 취급했다. 본인이 DB0건을 새로 검증한 것이 아니다.
- **운영 단계 구분**: source merge, Geo 새 코드/정의 배포, 활성 지문 재계산, Map·Concierge baseline 수용,
  daemon 활성화·운영 CPU/RSS 수용은 서로 별도다. 현재 SOURCE PASS로 이 단계를 완료 처리하지 않으며
  기존 root 위임에 새 승인요건을 추가하지 않는다.

## 본인이 실행한 판별 검사

### A. exact coverage test + old source 교차

소유 ext4 fixture에서 exact head test_data_fingerprint_covers_serving_tables.py를 그대로 실행했다.
앱/client import를 요구하는 test_non_v2_repo_allowlist_is_real_and_unused_by_v2_methods 1개만 제외했다.

- 새 tests + 실제 old d04 data_fingerprint.py: **2 failed /34 passed /1 deselected**,0.40초.
  실패는 :182의 9≠8과 :245/231의 radius 파생 재해시 거절이다. 의도된 RED이며 제품 실패를 숨긴 것이 아니다.
- exact head source + exact tests: **35 passed /1 deselected**,0.29초.
  파라미터 spec 수가 9→8이라 old/new 전체 collected 수가 1개 다르며 두 수량을 합산하지 않는다.
- 제외한 클래스 연결은 exact client.py의 AsyncAddressClient class source를 실제 v2_call_closure에 넣어 22개 도달 메서드를 얻고,
  실제 비v2 class가 closure에 없음을 별도 검사했다. client/app/settings를 import하지 않은 AST/source 검사이며 실제 API 실행이 아니다.

### B. 독립 추가 mutants와 함수 경계

동일 exact helper와 실제 SQL을 사용해 아래 5개 오구현을 각각 넣었을 때 실제 assert가 거절함을 확인했다.
공유/제품 파일이 아닌 소유 module 인자만 바꾸었다.

- tl_scco_ctprvn 누락 → radius built from unhashed ctprvn.
- tl_scco_sig 누락 → radius built from unhashed sig.
- tl_scco_emd 누락 → radius built from unhashed emd.
- mv_geocode_target 누락 → actual raw source들이 unhashed인 target임을 거절.
- region_radius_parts 재추가 → all sources hashed인데 derived target이 다시 hashed임을 거절.

추가로 immutable test_t325_data_token.py의 실제 함수/fixture AST만 추출해
SQL 모든 spec scan/geometry 규칙/schema drift, savepoint 성공 rollback, schema drift scan 전 거절,
caller timeout, timeout·일반 DB오류·일반 예외의 fail-open을 **9회** 직접 실행했다.
저장소 conftest/API 앱/실 DB는 로드하지 않았다. fake connection은 원래 unit의 전달 경계이며
PostgreSQL hash/geometry 엔진을 재구현한 것이 아니다.
실제 core derive_data_token의 None/빈값 부재 및 같은 지문=동일·다른 지문=다른 token도 별도 Python assert 2개로 확인했다.

### C. 정적 범위

- d04..a6 git diff --check exit0.
- 변경 MD 안의 상대 file link 75개를 head tree로 해석해 missing0.
- 원천 spec/allowlist/실제 SQL·refresh call 연결 및 두 diff 경계 일치 확인.
- 8개 blob SHA1/SHA256/bytes 일치, source 함수11 AST 불변.
- CI backend/openapi/integration-postgis/dagster/frontend 5 SUCCESS는 manifest의 외부 제공 증거다.
  본인이 새 CI/전체 suite/PostGIS를 실행한 결과로 합산하지 않는다.

## Findings / disposition

| 분류 | OPEN | 판정 |
| --- | ---: | --- |
| P0 | 0 | 발견 없음 |
| P1 | 0 | 발견 없음 |
| P2 | 0 | 발견 없음 |

초기 r1 기준점/ADR070 경로 표기 오류는 준비 입력 정정으로 종결했고 제품 finding이 아니다.
새 P3 수정 권고도 없다. geometry summary의 문서화된 손실과 수동 SQL 비표준 경로는 위 한계로 남긴다.
기존 max_runtime 21600·maintenance/recovery·590/591 튜닝은 변경/확장하지 않았다.

## 실패/NOT_RUN 한계

- 최초 넓은 ls-tree/합본 읽기 몇 건은 도구 출력이 잘려 필요한 본문을 더 작은 범위로 다시 읽었다.
- ADR043 파일명을 처음 잘못 추측한 Git show 1회가 exit128이었다. tree에서 실제
  043-region-radius-subdivided-accelerator.md를 찾아 정상 읽었으며 이 준비 오류를 제품 지적으로 세지 않는다.
- 의도된 old-source 2 RED 외 실행 fixture 오류0. 최종 own 검사 프로세스는 모두 종료했다.
- PostgreSQL/PostGIS/실 geodata/실 provider/SDK/REST 브라우저/운영 source/token/Map·Concierge 상태/Daemon/CPU·메모리/배포는 NOT_RUN.
- integration test의 실제 원천 변경·같은 데이터 재활성·파생 rebuild 효과는 SQL/테스트 소스로 검토하고 기존 원격 CI 귀속으로 남긴다.
  본인 35개 순수 coverage/9개 전달 경계 검사는 수치 SQL 결과나 PostGIS 잠금·동시성 증명이 아니다.
- 최종 verdict는 exact a6a 및 확인한 merge-tree6617의 source 범위다. 후속 head가 바뀌면 동일하다고 추정하지 않는다.

## 8개 불변 blob SHA256

| 파일 | SHA256 |
| --- | --- |
| CHANGELOG.md | abd734c4738ce656c4175f68dae2112734779a7a7521f83e26346a1cde500b66 |
| docs/adr/069-dataset-data-token.md | 7bebebfcdacd5dd2d99a359880f5c057b0b4f84b72965377180f6dc5e5ba27b0 |
| docs/adr/README.md | 46ace3acf72d5542c405830f4f25841eaf0d6ba9fba5c0566ebbfa33816b58f9 |
| docs/api-reference/v2/dataset-version.md | ccfe83a29ea6050cb801abbbccff0ccbbe30c8d9e32e1585825f96c725afa19e |
| src/kortravelgeo/infra/data_fingerprint.py | de7a65a1fff94138e40e8fc4d8cf251fa83643c71fb5dd29f36cafd3e5d5238d |
| tests/integration/test_t325_data_fingerprint.py | 33a9b7cbc9f7c7df23e6d073b02f6962bddb71be36e6f9026148e963475926d7 |
| tests/unit/test_data_fingerprint_covers_serving_tables.py | d5fb88cb5f6ca921bf9544dbbc9bac9449623a6c54e406a67b561b475900cd08 |
| tests/unit/test_t325_data_token.py | 3ef86907d7274a86c8e174ae3015b15189c341c9b6b9c0ddcfa6f4f32a80537f |

compact ordered path/SHA256 list SHA256: 58edd4e242f46e7d1dec2444a05fc1d033412961a7ff5c4874d0f16e6301dc92.

## 실제 전달 요청 원문

```text
Track1 Geo589의 FULL 독립 A/API·소비자token/변경제거가시성 계약 리뷰를 진행하세요. 결함발견목적/애매하면지적. 정확same manifest /home/digitie/dev/geo589-review-manifest-20261018-r1.json SHA f139278c729cfab31cecf003ac94dc355b11f61cc382c2713ffff20e7e09fa3f. base03269e2426beb0837b17a40726adc9a16f26b6a0 → heada6a9fcdf09656c29828113ada12cf2990d1d5d31, root독립 no-checkout clone /home/digitie/dev/kor-travel-geo-codex-track-review-20261018에두Git객체확인. original Claude WT/Git brokenpointer는수정하지않았습니다. 기존8파일/5CI SUCCESS 검토이며 source는 Claude 소유이니 source/index/branch/sharedclone checkout·편집·되돌림금지. AGENTS/README/SKILL/관련runbook·ADR069/D8/ADR043 최소정본을 immutableGitshow로읽고, fingerprint9→8·region_radius_parts파생제외·원천변경민감도·같은원천재생성불변·모든servingtable coverage/allowlist 이유·mutant 판별력·geometry요약민감도한계·정의변경token1회변화·기존소비자token과첫baseline차이를공격하세요. D4=21600 유지/Geo튜닝범위외. 각파일blob/SHA가manifest와맞는지도확인. sourcefull2review원문을확인한공개경로에서못찾아새독립리뷰를진행하며감사/commit'리뷰반영'을제품PASS로세지않습니다. 순수실행이도움되면자기소유Temp/sterile환경·실제Git source로만검증; conftest/env/운영DB/SDK/SSH/provider/Docker/daemon/새CI/실데이터접근금지. mock값으로알고리즘을다시써서통과시키지마세요. 현재5CI는제공된증거와자기실행을분리. 새상대Geo589보고서둘다확정전읽거나요청금지. 다른agent와병행이니타인변경안건드림. 실제요청전문·manifest/관찰hash/base/head/시간/격리·검증과실패/NOT_RUN·구체file:line시나리오/P0-P2·PASS/CONDITIONAL/BLOCK·OPEN수를 /home/digitie/dev/geo589-review-james-r1.md 에저장하고SHA보고. source머지와배포후fingerprint-active/Map·Conciergebaseline/운영·CPU수용을구분하고새승인요건을만들지마세요.
```

## 기준점 정정 후속 요청 원문

```text
root 기준선 실수를 확인·정정했습니다. 실제 merge-base=d04befabe4c3877a2a93c2159e84de93d9730bc2, current main03269는 D4 문서 커밋209bfc6/merge588을 추가로 포함합니다. git merge-tree --write-tree current03269 heada6a9 EXIT0 tree6617fc944e22ca39f062cf73935ab1c6ff6ba857, effective delta는8파일145+/24-이며 ADR070/journal/resume/tasks는 currentmain과 byte모두동일해 D4유지입니다. 정정 manifest /home/digitie/dev/geo589-review-manifest-20261018-r2.json SHA5f58be530c9b58b7e423f9ae2c6fc68ef40855780053e932bf07a031aaf52c92로 같은head의 검토를 이어가세요. 이전r1 root오류와관찰은 원문에남기되이를제품D4삭제finding으로단정하지마세요(증거로판정). 원래A역할/독립성/noops제약은그대로이며새상대결과전달0. 실제d04..a6 및032..6617 두경계를확인하고최종원문은당초 /home/digitie/dev/geo589-review-james-r1.md 에 superseded초기manifest+최종r2hash/실제후속요청전문을함께기록하세요.
```

## 경로 근거 정정 후속 메시지 원문

```text
경로 표기 실수도 확인했습니다. root 최초비교는 nonexistent070-host-move 경로에서 git-show exit검증을 빠뜨린 잘못된 근거였음을 보존합니다. 올바른 docs/adr/070-odroid-host-and-empty-host-full-load.md와 나머지3파일은 방금 check_output 성공종료+byte/blob equality로 재검증했습니다. 보조증거 /home/digitie/dev/geo589-d4-existing-path-proof-20261018.json SHA6b75d1d0714af2d3ddb105a36f6699da42014ab2ca65c686c4d1fda68ad91d27. r2 manifest/head/base는 그대로이며 이증거는경로정정만입니다. 원문에 root입력오류와본인독립관찰범위를구분해남겨주세요. 새상대보고서노출0.
```

검토 종료 UTC: 2026-10-18T04:08:56.209940+00:00
