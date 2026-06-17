# ADR-049: T-109 원천 파일 업로드·매칭·검증은 확장성 우선 설계로 구현한다

- 상태: accepted
- 날짜: 2026-06-14
- 결정자: 사용자 요청, codex

## 컨텍스트

T-109는 백업/리스토어 고도화를 위해 원천 파일 업로드, RustFS 저장, DB registry, source match set, optional 검증 자료, C11+ 검증 케이스를 새로 설계한다. PR #131 리뷰에서 M1~M12와 L1~L11이 확인됐고, 사용자는 아직 서비스 단계가 아니므로 호환성·최소 수정 비용보다 확장성, 완성도, 일관성, 성능을 우선하라고 결정했다. 단, admin/API/CLI/DTO처럼 외부에서 호출할 수 있는 인터페이스 변경은 문서와 OpenAPI에 명확히 남겨야 한다.

## 결정

T-109 구현은 다음 확정안을 따른다.

1. C11+ case metadata는 DB registry 기반 동적 catalog를 정본으로 둔다.
2. match set과 운영 dataset 연결은 `ops.dataset_snapshots.source_match_set_id` FK로 한다.
3. source file 검증 상태는 `state`와 `validation_state`를 분리한다.
4. upload/register 흐름은 storage-first다. 업로드 세션 생성 시 `user_yyyymm`은 필수이며 사용자가 직접 입력·확정한다. UI는 추정값 또는 현재 날짜 기준 `YYYYMM`을 입력 필드의 사전 입력값으로만 제안한다. `user_yyyymm`이 없으면 백엔드는 파일명이나 현재 날짜로 보완하지 않고 upload session 생성을 거부한다. RustFS 저장과 검증 뒤 사용자가 registry 등록을 승인한다.
5. admin 권한은 role gate를 필수로 두고, typed confirmation은 추가 안전장치로만 사용한다. 최소 신원 source는 trusted reverse proxy 또는 Next.js admin proxy가 주입하는 `X-KTG-Actor`/`X-KTG-Roles` 헤더다.
6. `ops` 내부 ID는 full-prefix로 통일한다. 기존 `snapshot_id`, `release_id`, `event_id` 등은 구현 단계에서 `dataset_snapshot_id`, `serving_release_id`, `audit_event_id`처럼 rename한다.
7. 시도별 다중 파일 category는 `ops.source_file_groups`를 만들고, match set은 group을 참조한다. child file 분할은 `sido_code` 하드코딩이 아니라 `part_kind`/`part_key`로 일반화한다.
8. 업로드 전략은 multipart/resumable을 정식 경로로 둔다. upload session과 part 진행 상태는 DB에 영속화한다.
9. RustFS 정합성 검증은 `quick`/`deep` 모드로 나눈다. 정기 scan은 size/etag가 직전 검증과 같으면 재해시를 생략하고, 변경 감지 object나 사용자가 실행한 `deep` scan은 object 전체를 streaming 재해시해 SHA-256 mismatch를 즉시 확정한다.
10. `rebuild-db`와 `run-validation`은 RustFS object를 materialize한 뒤 loader 또는 validator가 사용하기 직전에 registry의 `sha256`/`size_bytes`/`group_sha256`와 다시 대조한다. 불일치나 누락이 있으면 rebuild는 child job을 만들지 않고 중단하며, validation은 해당 입력을 `skipped`가 아니라 `failed`로 기록한다.
11. 진행 중 upload session은 목록 API와 UI에서 다시 찾을 수 있어야 하며, 등록 대기 object는 deadline 전까지 reconciliation에서 `pending_registration`으로 분류해 삭제 후보에서 제외한다. deadline이 지난 저장 완료 object는 자동 삭제하지 않고 `registration_expired` issue로 전환한다. DB에 multipart part 기록은 있지만 RustFS multipart upload id가 이미 abort/expire된 경우는 `failed_storage_state`로 전환하고 해당 slot 재업로드를 요구한다.
12. match set activation은 기존 active를 retire하고 새 active를 세우는 atomic swap이다. active match set은 object 결손이 생겨도 `state='active'`를 유지하고 `integrity_alert=true`로 재구성 불가를 표시한다. `state='invalid'` 전환은 비-active 중 `validated` match set에만 적용하고(`draft`/`restored_from_backup` 같은 pre-hash 상태는 hash를 요구하는 `invalid`로 가지 않는다), `revalidatable` 복구 전이는 `invalid` 또는 `restored_from_backup`(후자는 canonical hash 선산출 후, M-A 옵션2)에 적용한다. active `integrity_alert` 해제는 `POST /validate`의 active validate-in-place로만 확정하며, 성공해도 `state='active'`를 유지한다.
13. rebuild는 전역 PostgreSQL advisory lock, stale running job 마감, staging 재초기화, consistency ERROR 승격 차단을 포함한다. 알려진 원천 품질 ERROR를 받아들이는 경우만 `destructive_admin` typed confirmation으로 `forced_promotion=true`를 기록한다. `forced_promotion=true`는 consistency ERROR 승격 차단만 우회하고, source archive integrity gate(hash/size/object presence), `source_file_group.state!='available'`, selected match set의 `integrity_alert=true`는 우회하지 못한다.
14. 백업 복원 후 manifest 기반 `restored_from_backup` match set은 read-only stub group/file을 `missing` 상태로 만들고, source archive availability와 hash 확인 전에는 rebuild 입력으로 활성화하지 않는다. stub은 `validation_state='unknown'`인 채 `available`이 될 수 없다. object 재연결 후에는 **두 상태머신을 구분해** 전이한다: group/file은 `missing -> validating -> (storage SHA-256/size 재계산 + validation_state passed/warning) -> available`, 그 group을 모두 갖춘 match set은 **먼저 canonical source_set_hash를 산출한 뒤** `restored_from_backup -> revalidatable -> (validate) -> validated`로 전이한다(M-A 옵션 2: revalidatable 진입 전 hash 산출로 source_set_hash CHECK 위반 방지). manifest의 `group_sha256`은 재계산 전까지 신뢰값이 아니라 비교 대상이다.
15. `soft_deleted` source group/file은 RustFS head/hash 검증과 재검증을 거친 `restore` action으로 되살릴 수 있다. 재업로드로 우회해 새 group id를 만드는 것을 기본 복구 경로로 삼지 않는다.
16. restore hot-swap 또는 rename 기반 운영 DB 교체 직후에도 source quick reconcile을 실행해 active snapshot의 `source_match_set_id`와 RustFS object availability를 확인한다.
17. 같은 `category + user_yyyymm`의 non-terminal upload session은 기본적으로 1개만 허용한다. 중복 생성 요청은 `409`와 기존 session resume payload를 반환한다. register 전 완료 slot은 명시 `replace`로 교체할 수 있으며 기존 검증 결과를 무효화한다.
18. serving release rollback도 match set one-active invariant를 따른다. rollback 대상 snapshot이 `source_match_set_id`를 갖고 있으면 같은 transaction에서 현재 active match set을 `retired`로 내리고 대상 match set을 `active`로 복원한다. 대상의 `integrity_alert`는 rollback 직전 source quick reconcile 결과로 보존 또는 재계산한다. legacy snapshot은 정본 match set으로 자동 승격하지 않는다.
19. epost pobox/bulk는 수동 server-fetch 예외이며, fetch 실패·ZIP 구조 불일치·기준월 mismatch를 upload/session/report 상태로 노출한다. 핵심 source match set rebuild에는 포함하지 않는다.
20. janitor는 PostgreSQL advisory lock 기반 admin service/CLI periodic job로 두며, 미완 multipart abort와 session 만료 전이만 자동 처리한다. RustFS 저장 완료 object는 자동 삭제하지 않고 reconciliation issue로 사용자 조치를 기다린다.

## 근거

- 아직 운영 서비스 안정화 전이므로, 사후 호환 alias를 쌓는 것보다 schema/API/DTO를 일관되게 정리하는 비용이 낮다.
- SHP 3종은 제공 단위가 시도별 ZIP 17개라서 개별 file이 아니라 group을 match set 단위로 삼아야 한다.
- 기준년월은 파일명 추정이나 현재 날짜 fallback으로 자동 결정하면 안 된다. 사용자가 직접 입력·제출한 `user_yyyymm`만 저장과 match set의 정본이 된다.
- RustFS object 저장은 DB transaction과 원자적으로 묶을 수 없다. 먼저 저장하고, 검증과 사용자 승인 뒤 registry insert를 재시도 가능하게 만드는 흐름이 운영 UX와 잘 맞는다.
- 손상 의심 object는 hash mismatch를 지연 확정하지 말고 전체 재해시로 즉시 판단해야 한다. 다만 정기 scan이 매번 전국 object를 다시 읽으면 운영 I/O 비용이 선형으로 커지므로, 변경 감지와 `deep` scan을 분리한다.
- 업로드/register와 rebuild/run-validation은 며칠 또는 몇 주 간격으로 분리될 수 있다. 그 사이 사용자가 RustFS에 직접 접근해 object를 교체·삭제할 수 있으므로, 정기 reconciliation에만 의존하지 않고 실제 사용 직전 흐름이 독립적으로 무결성을 보장해야 한다.
- 운영자는 대용량 17개 part 업로드를 한 번에 끝내지 못할 수 있다. session 재개 진입점, 중복 session 409, `pending_registration`/`registration_expired` 구분이 없으면 resumable upload와 storage-first 모델이 실제 UX에서 깨진다.
- active serving DB는 이미 만들어진 결과이고, source archive registry는 같은 DB를 다시 만들 수 있는 근거다. 따라서 active match set의 원천 결손은 `state`를 `invalid`로 바꿔 one-active 슬롯을 비우지 않고, `integrity_alert`로 재구성 가능성 결손을 표시해야 한다.
- 백업 복원과 rename hot-swap은 serving DB 교체 절차일 뿐 원천 archive가 현재 RustFS에 존재한다는 보장은 아니다. 복원 entrypoint마다 source quick reconcile이 필요하다.

## 결과(긍정)

- T-109 구현자가 선택지를 다시 해석하지 않고 같은 방향으로 schema/API/UI를 만들 수 있다.
- admin UI는 C11+ 추가 시 하드코딩 없이 case registry를 렌더링할 수 있다.
- source match set과 active serving release의 연결이 FK로 추적된다.
- 대용량·불안정 네트워크에서도 multipart upload 진행률과 재개가 가능하다.
- 기존 `ops`와 신규 source registry의 ID 네이밍이 맞춰진다.
- 정기 RustFS scan은 `quick`, 손상 의심 또는 수동 검증은 `deep`으로 분리되어 운영 I/O 비용을 통제할 수 있다.
- RustFS object가 register 이후 변조돼도 rebuild와 사후 validation이 자체적으로 중단되어 손상 archive가 적재·검증 입력으로 조용히 사용되지 않는다.
- 브라우저 종료, 서버 재시작, 복원 직후 metadata 결손, soft-delete 복구, hot-swap 후 source 결손 같은 운영 시나리오가 명시 상태 전이로 닫힌다.

## 결과(부정)

- 기존 admin API/DTO/OpenAPI의 `snapshot_id`, `release_id`, `event_id` 계열 이름이 바뀌므로 migration과 문서 갱신 범위가 커진다.
- role gate, multipart upload, DB case registry, quick/deep reconciliation은 최소 구현보다 작업량이 많다.
- deep 재해시는 object 수와 크기가 늘면 정합성 scan 시간이 길어질 수 있다.
- rebuild와 validation도 materialize 시점에 streaming hash를 계산해야 하므로, 해당 job의 I/O와 구현 복잡도가 약간 증가한다.
- match set atomic swap, stale rebuild 정리, restored stub 생성, `integrity_alert`, restore/janitor/slot replace까지 포함하므로 구현 PR의 schema/API/test 범위가 더 넓어진다.

## 후속

- (open) T-109 구현 PR은 full-prefix rename migration, `infra/sql.py`/`sql/ddl/001_schema.sql` fresh init-db DDL 갱신, OpenAPI export, TypeScript type 재생성, admin UI route/parameter 변경 문서를 함께 포함한다.
- (resolved, ADR-052) RustFS 용량 관리 정책은 ADR-052(T-212)로 확정했다. 기본은 등록 archive 무기한 보존 + 자동 삭제 금지, 정리는 `destructive_admin` typed-confirmation 일괄 hard-delete로만. archive tier는 향후 별도 ADR.
- (open) 보강 자료가 실제 serving 좌표 ranking에 편입되는 조건은 C11+ 검증 결과와 feature flag 기준을 보고 별도 ADR로 정한다.
