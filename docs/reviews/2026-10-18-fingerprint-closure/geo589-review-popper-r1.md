# Geo589 독립 Popper/Backend·SQL·지문정합·회귀·운영계약 FULL 리뷰 r1

**PASS — SOURCE_AND_PURE_FIXTURE_ONLY. OPEN P0=0 / P1=0 / P2=0.**

source 범위에서 새 차단 결함을 발견하지 못했다. 실제 PostGIS/운영 fingerprint-active/소비자 baseline/Daemon ON/CPU 수용을 실행하거나 완료했다고 판단하지 않는다. r1 기준선 오류는 아래 이력으로 보존하며, 정정된 실제 delta와 merge 결과에 D4 삭제 finding을 부여하지 않는다. 새 상대 Geo589 원문/모형은 읽거나 요청하지 않았다.

## 불변 대상·시각·격리

- 첫 관찰 UTC 2026-10-18T04:03:07.783654+00:00, 마지막 연결 source 관찰 UTC 04:07:32.287060. 종료 시각은 끝에 기록.
- root 독립 no-checkout clone: /home/digitie/dev/kor-travel-geo-codex-track-review-20261018.
- head a6a9fcdf09656c29828113ada12cf2990d1d5d31, tree666ba1ce8767bca750add3ee753fa2da5bbcf6ea.
- 최종 실제 merge-base d04befabe4c3877a2a93c2159e84de93d9730bc2, tree d02c7c119ffc606ef750e31ff2196a3e767712eb.
- 최종 manifest /home/digitie/dev/geo589-review-manifest-20261018-r2.json 실제 SHA256 **5f58be530c9b58b7e423f9ae2c6fc68ef40855780053e932bf07a031aaf52c92**.
- 최초 r1 manifest 실제 SHA256 **f139278c729cfab31cecf003ac94dc355b11f61cc382c2713ffff20e7e09fa3f**. r1의 base03269는 최종 제품 delta 판정에서 superseded다.
- AGENTS/README/SKILL, workflow/failure-patterns runbook, architecture 라우터, ADR069 D2/D3/D8·개정, ADR043, resume/tasks G01 정본을 읽었다. gitignored local/private runbook/env는 요청 제한에 따라 읽지 않았다.
- WSL Linux의 immutable Git object와 소유 TemporaryDirectory만 사용. original Claude WT/Windows pointer/shared checkout/index/branch/WIP를 수정하지 않았다. 기존 read-only Weather venv interpreter에 -I -B, sterile HOME/TMPDIR/PATH, PYTHONDONTWRITEBYTECODE와 pytest plugin 자동 로드 차단/--noconftest/-c /dev/null/-p no:cacheprovider를 적용했다.
- actual Geo package __init__/API/Settings/client import를 피하기 위해 소유 namespace 경로를 만들고 actual fingerprint/sql source를 로드했다. client closure는 실제 class AST source로 검사했다.
- 운영 DB/실데이터/env/secret/SDK/provider/SSH/Docker/Daemon/새 CI/브라우저 실행0. audit hook은 socket/subprocess를 거부했다. 알고리즘을 재구현한 mock hash를 검증 근거로 쓰지 않았다. 이 보고서 외 영구 산출물은 없다.

## 초기 scope 불일치와 직접 정정 검증

처음 요청의 currentmain03269→head a6a 단순 two-dot diff는 **12파일148+/40-**였다. 그 비교에서는 ADR070 D4 21600유지 결정·journal 항목이 빠지고 resume/tasks가 draft 재확인으로 보였다. 즉시 root에 scope 불일치를 알렸고 제품 finding 확정은 보류했다.

root는 currentmain을 merge-base로 잘못 지정했다고 정정했다. 본인은 이후 직접 다음을 확인했다.

1. git merge-base 03269… a6a… 결과 d04bef….
2. d04→a6 실제 PR delta **8파일145+/24-**, manifest 8경로 일치.
3. root가 이미 만든 예상 merge tree6617fc944e22ca39f062cf73935ab1c6ff6ba857를 읽어 **d04→a6 patch bytes == 03269→6617 patch bytes** 전체 동일.
4. 실제 존재 경로 docs/adr/070-odroid-host-and-empty-host-full-load.md, docs/journal.md, docs/resume.md, docs/tasks.md 각각 check_output git-show 성공 후 current03269/merge-tree6617 bytes를 비교해 **4/4 동일**.
5. kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py도 d04/head byte 동일. D4=21600 유지. 590/591 tuning/timeout은 이 PR 변경으로 계수하지 않는다.
6. 두 실제 diff 경계 모두 git diff --check exit0.

root의 첫 D4 증명은 nonexistent070-host-move 경로에서 exit를 확인하지 않은 오류였다는 후속 메시지도 받았다. 보조 proof SHA6b75d1d0714af2d3ddb105a36f6699da42014ab2ca65c686c4d1fda68ad91d27를 확인했으나 본인 판정은 위 **실제 존재 경로/성공종료/byte 비교**에 근거한다. 초기 입력 오류를 제품 D4 삭제로 판정하지 않는다.

## 전체 delta와 연결 source 검토

### 실제 파생 관계·coverage

src/kortravelgeo/infra/data_fingerprint.py:77–133은 region_radius_parts spec만 제거하고 이유 있는 allowlist로 이동한다. 나머지8표 spec/column/geometry 규칙은 그대로다. dependency/schema/DTO/OpenAPI/복구 정책 변경은 없다.

infra/sql.py:1282–1335의 실제 refresh SQL은 TRUNCATE 후 tl_scco_ctprvn/sig/emd에서 code/name/parent code/geom을 읽고 ST_Subdivide(geom,256), row_number ORDER BY ST_Area DESC로 parts를 다시 만든다. 셋은 지문에 남으며 tl_scco_li도 계속 지문 대상이다.

- loaders/postload.py:55–115: concurrent/swap 모두 parts refresh await 후 반환. parts는 SQL 순회와 publication_guard를 commit 전에 수행.
- cli/main.py:499–507,537–548,756–766: shp/shp-all/all-sidos의 source 적재 뒤 parts 재생성, 이후 release 기록.
- loaders/batch_dag.py:344–353,433–475: SHP leaf가 재생성 완료 후 반환하고 standalone direct-serving release는 loader 완료 후 기록. batch child는 최종 consolidated release를 기다림.
- ADR043:15–20,35–38: 표준 경로 재생성 불변식과 연결 source가 정합. 직접 SQL로 원천만 변경하는 비표준 경로는 기존 문서 제한이다.

이를 전부 하나의 장기 transaction이라는 뜻으로 확대하지 않는다. MV/parts/release는 별도 commit을 가질 수 있고 취소/부분 실패의 기존 publication/worker fence와 운영 수용은 별도다. 이 PR은 그 호출 순서/commit/lock을 바꾸지 않는다.

### SQL 결정성·geometry 민감도

data_fingerprint.py:136–170의 actual builder는 spec 이름 정렬, public schema, 행 hashtextextended의 numeric sum, 최종 table_name COLLATE C string_agg→md5를 사용한다. 표 이름도 입력이므로 9→8 정의가 달라지는 전환을 설명할 수 있다. _row_expression은 code/name, 점 WKB, polygon ST_NPoints|Box2D를 유지한다.

새 SQL은 parts part_no/분할 순서/조각 자체를 읽지 않는다. 원천 code/name 또는 NPoints/Box2D가 달라지면 hash 입력이 바뀐다. 실제 PostgreSQL hash/sum/PostGIS 결과를 본인이 실행한 것은 아니다. 함수 출력 SQL·선택표·회귀 판별력을 검사했고 실제 DB effect는 외부 PostGIS CI 귀속이다.

ADR069:440–443은 감도 손실을 명시한다. polygon 점 수/bbox는 같고 내부 경계만 움직이면, 예전 parts 요약에서 드러났을 변화를 이제 놓칠 수 있다. 이는 승인된 D3 절충이며 모든 geometry 변경 검출을 PASS하지 않는다. 모든 플랫폼/PostGIS 버전의 완전 결정성이나 hash 무충돌도 증명하지 않는다.

### 실패·activation·복원·소비자

- data_fingerprint.py:241–288의 savepoint/SET LOCAL/성공·실패 rollback/schema drift fail-open은 그대로다. 30min은 base에도 있으며589에서 새로 늘린 것이 아니다.
- admin_repo.py:806–815는 fingerprint를 publication guard 전에 계산한다. active release 재검사/cache clear/hot-swap 상속은 이번 delta에서 바뀌지 않는다. 장시간 scan을 새로 lock 아래 넣지 않는다.
- ADR069:449–455 및 API reference:115–119는 정의 전환으로 같은 데이터 token1회 변화를 명시하고, 이전 정의 backup/hot-swap/rollback이 저장 지문을 상속해 옛 token을 다시 가져올 수 있으므로 **복원 뒤 fingerprint-active 재계산**을 설명한다. dd1 prefix/DTO/schema 변화0.
- ADR069 D8:245–253의 없음=판정불가, 저장값 없음→첫 유효 token baseline만 저장, 두 값 모두 있고 다름→재해석 규칙은 유지된다. 이미 baseline 있는 소비자를 자동 초기화하지 않는다.
- “현재 baseline0건”은 작성시점 관측이며 본인 DB 증명이 아니다. source merge 이후 활성 지문 재계산/Map·Concierge baseline 수용/Daemon OFF/CPU 수용은 별도다. 운영 작업을 새 사용자 승인요건/merge 장벽으로 추가하지 않는다.

## 본인 검사와 실패 이력

### 실제 coverage: 최종35 PASS/0.29초, 1 deselected

exact head의 test_data_fingerprint_covers_serving_tables.py와 실제 fingerprint/sql/infra repo 파일을 소유 temp에 넣어 실행했다. package client import가 필요한1개는 선택 제외하고, actual AsyncAddressClient class source AST와 actual v2_call_closure로 22메서드 closure 및 non-v2 repo 미사용 조건을 따로 확인했다. 알고리즘을 대역으로 다시 쓰지 않았다.

새 unique8/derived-exclusion positive 두 테스트를 actual merge-base fingerprint.py로 바꾼 소유 fixture에서 **2 FAIL**(9!=8, region derived-but-hashed) 확인. 현재 코드에서는 같은 검사가35PASS에 포함된다. repo source를 되돌린 것이 아니다.

actual assert_no_derived_table_is_hashed에 tl_scco_ctprvn/sig/emd 각각 누락 및 mv_geocode_target 누락4mutant를 넣어 모두 AssertionError. exact 테스트의 region 재삽입도 rejection을 확인한다. FROM/JOIN coverage·phantom allowlist·new repo·missing table·column drift 검사가 함께 통과했다.

### actual SQL/schema/token 및 exact callback9 PASS

- actual _build_fingerprint_sql에 spec순서32개를 섞어 입력: SQL bytes 전부 동일.
- SQL이 public.region_radius_parts를 읽지 않고 tl_scco_sig/sig_kor_nm을 읽음 확인.
- actual schema_drift에 남은 source3표 각각 누락: 해당 표명으로 거절.
- actual derive_data_token의 같은입력/다른입력/None 경계 검사.
- actual data_token tests의 SQL shape/schema/savepoint/timeout/exception/drift/caller-timeout AST를 그대로 실행해 **9 PASS**. fake connection은 exact 기존 테스트의 transport일 뿐 hash 계산 대역이 아니다. coroutine은 직접 완료시켜 asyncio socket/DB engine을 만들지 않았다.

첫 coverage 실행은35PASS 뒤 own client-closure assert가 실패했다. client.py 전체의 첫 class가 AsyncAddressClient라고 가정했기 때문이다. 정확한 class AST segment를 넘긴 최종35PASS/closure22만 계수했다. 첫35와 합산하지 않았다.

첫 callback runner는 asyncio.run의 자체 wakeup socketpair가 audit hook에 거절돼 종료1. 외부 네트워크/DB 호출은 없었다. event loop 없이 non-yielding coroutine을 직접 완료한 최종9PASS만 계수했다. intentional old-code2FAIL은 판별력 증거이며 성공으로 지우지 않는다.

## 통합·문서·외부 CI 한계

tests/integration/test_t325_data_fingerprint.py:261–289는 parts만변경→token유지, source이름변경+실제refresh→token변경을 저장 release 경로로 검사한다. :292–304는 같은bbox vertex추가, :319–326은 MV변경 민감도다. disposablePG guard/actual source/activation 사용은 읽었으나 본인은 실행하지 않았다. 같은호스트 ST_Subdivide 반복 결정성을 증명하는 새 테스트도 아니다. ADR069가 그 미확인을 명시한다.

**비차단 P3 표현 관찰**: CHANGELOG.md:42–44 “호스트·실행마다 해시가 달라”는 ADR069:438–439 “추정, 같은호스트 재실행 결정성·GEOS 확인하지 않음”보다 단정적이다. 확실한 근거는 환경 사이 parts지문 차이이며 every-run 비결정성 실증은 아니다. source/table 정책을 바꾸는 P0–P2 결함으로 계수하지 않는다.

manifest의 backend/openapi/integration-postgis/dagster/frontend5 SUCCESS는 외부 CI 증거다. 본인의 PG/전체suite/SDK/provider/운영 증명이 아니다. “리뷰 반영” commit이나 기존 감사도 이번 source PASS로 계수하지 않았다. 새 CI 실행0. API/worker/lifecycle/복원·활성지문재계산·소비자baseline·CPU/RSS는 이번 독립 실행에서 NOT_RUN이다.

## 8 blob/SHA 검증

각 SHA256·Git blob·bytes를 manifest에 대조해8/8 일치했다.

| 파일 | Git blob | SHA256 |
| --- | --- | --- |
| CHANGELOG.md | 07d01192ab9324c278e5f1b4c4086f0b34134eb8 | abd734c4738ce656c4175f68dae2112734779a7a7521f83e26346a1cde500b66 |
| docs/adr/069-dataset-data-token.md | eba8c314f95b6874bb2c09f0707c4b8d8d71a9a5 | 7bebebfcdacd5dd2d99a359880f5c057b0b4f84b72965377180f6dc5e5ba27b0 |
| docs/adr/README.md | f57ac6921bafb235699f6a963c70c5808df2c9d5 | 46ace3acf72d5542c405830f4f25841eaf0d6ba9fba5c0566ebbfa33816b58f9 |
| docs/api-reference/v2/dataset-version.md | 507644bd37f8c8e4874bcd65bea6e21e9da559f0 | ccfe83a29ea6050cb801abbbccff0ccbbe30c8d9e32e1585825f96c725afa19e |
| src/kortravelgeo/infra/data_fingerprint.py | ef479537b7320663fa2eaa4c8a7b3c43099228a2 | de7a65a1fff94138e40e8fc4d8cf251fa83643c71fb5dd29f36cafd3e5d5238d |
| tests/integration/test_t325_data_fingerprint.py | b250dd93109fb79ca6cd206166f6b6a99884c50e | 33a9b7cbc9f7c7df23e6d073b02f6962bddb71be36e6f9026148e963475926d7 |
| tests/unit/test_data_fingerprint_covers_serving_tables.py | 39c6ef81ad398279443e4adc394499ffdaad0f9d | d5fb88cb5f6ca921bf9544dbbc9bac9449623a6c54e406a67b561b475900cd08 |
| tests/unit/test_t325_data_token.py | e6ba89501acc35a072304f45ef497458491fb0f3 | 3ef86907d7274a86c8e174ae3015b15189c341c9b6b9c0ddcfa6f4f32a80537f |

## 실제 전달 요청 원문 — 초기 요청

~~~text
Track1 Geo589 FULL 독립 B/Backend·SQL·지문정합·회귀/운영계약 리뷰입니다. 결함발견목적, 애매하면지적. same manifest /home/digitie/dev/geo589-review-manifest-20261018-r1.json SHA f139278c729cfab31cecf003ac94dc355b11f61cc382c2713ffff20e7e09fa3f. base03269e2426beb0837b17a40726adc9a16f26b6a0 → heada6a9fcdf09656c29828113ada12cf2990d1d5d31, root독립no-checkout clone /home/digitie/dev/kor-travel-geo-codex-track-review-20261018에두Git객체존재. 원ClaudeWT/brokenWindowsGitpointer수정0. 8파일/현재5CI SUCCESS의동일delta전체를검토하되코드작성자는Claude이므로 source/index/branch/sharedclonecheckout·편집·되돌림금지. AGENTS/README/SKILL/runbook·ADR069/D2/D3/D8/ADR043 최소정본읽고 실제refresh재생성원천관계/allowlist coverage·sourcegeometry민감도/SQLfingerprint결정성·같은원천재생성token불변·원천행변경token변화·제외표재삽입/원천표누락mutant테스트판별력·정의전환token1회변화/복원후재계산/기존소비자baseline관계를공격하세요. D4=21600유지·590/591튜닝/timeout이589에추가됐다고확대금지. 모든blob/SHA확인. 공개경로exact2리뷰raw미발견이새리뷰이유이며감사나commit'리뷰반영'을소스PASS로계수하지않습니다. 자기소유Temp/sterile환경실제Git source의순수시험만허용, 실제conftest/env/secret/운영DB/SDK/provider/SSH/Docker/daemon/실데이터/새CI금지. 알고리즘을다시쓴mockPASS금지. 현재PostGISCI성공은외부증거로귀속하고직접PG실행처럼표시하지마세요. 새상대Geo589보고서둘다확정전읽거나요청금지. 다른agent와병행이니타인변경안건드림. 실제요청전문·manifest/관찰hash/시간/격리·검사/실패/NOT_RUN·file:line/P0-P2구체시나리오·PASS/CONDITIONAL/BLOCK·OPEN수를 /home/digitie/dev/geo589-review-popper-r1.md 에저장후SHA보고. source머지와배포후fingerprint-active/소비자baseline/daemonOFF/CPU수용은구분하며새사용자승인요건을만들지마세요.
~~~

## 실제 기준선 정정 요청 원문 — 최종 r2

~~~text
root 기준선 실수를 확인·정정했습니다. 실제 merge-base=d04befabe4c3877a2a93c2159e84de93d9730bc2, currentmain03269는D4문서커밋209bfc6/merge588추가입니다. git merge-tree --write-tree current03269 heada6a9 EXIT0 tree6617fc944e22ca39f062cf73935ab1c6ff6ba857, effective delta8파일145+/24-이며 ADR070/journal/resume/tasks는currentmain과byte동일해D4유지. 정정manifest /home/digitie/dev/geo589-review-manifest-20261018-r2.json SHA5f58be530c9b58b7e423f9ae2c6fc68ef40855780053e932bf07a031aaf52c92로동일head검토를이어가세요. 초기r1root오류·관찰은원문에남기되제품D4삭제라고단정하지마세요(증거로판정). 원래B역할/독립성/noops제약유지·새상대결과전달0. 실제d04..a6와032..6617두경계확인, 최종원문은원래 /home/digitie/dev/geo589-review-popper-r1.md 에초기supersededmanifest+최종r2hash/이후실제요청전문을함께보존하세요.
~~~

## 실제 root 증명 경로 정정 원문

~~~text
r2root D4검증 첫경로가 잘못됐습니다. 최초 nonexistent070-host-move 비교는 git-show exit검증누락의잘못된근거였음을보존합니다. 실제 docs/adr/070-odroid-host-and-empty-host-full-load.md와나머지3파일을방금check_output성공종료+byte/blob equality로재검증. 보조 /home/digitie/dev/geo589-d4-existing-path-proof-20261018.json SHA6b75d1d0714af2d3ddb105a36f6699da42014ab2ca65c686c4d1fda68ad91d27. r2manifest/head/base는그대로, 경로정정만이며sourceD4삭제가아님은각자실제객체로판단하세요. root입력오류/본인검증범위를원문에분리기록. 새상대보고서전달0.
~~~

검토 종료 UTC: 2026-10-18T04:10:49.872794+00:00
