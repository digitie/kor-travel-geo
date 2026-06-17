# ADR-052: RustFS 원천 archive는 자동 삭제하지 않고 수동 관리 표면으로만 정리한다

- 상태: accepted
- 날짜: 2026-06-15
- 결정자: 사용자 요청, claude
- 관련: T-212 (ADR-049 #20·후속 line, ADR-050)

## 컨텍스트

PR #131 리뷰(ADR-049 후속 line "RustFS 용량 관리 정책은 별도 ADR로 정한다")에서 원천 archive의 보존·정리 정책을 별도 ADR로 확정하기로 했다. T-204 reconciliation, T-203c soft-delete/restore + janitor, T-211 용량 metric/카드까지 구현된 상태에서, 저장소가 무한히 커질 때 운영자가 안전하게 정리할 수 있는 정책과 표면이 필요하다. 다만 원천 archive는 같은 serving DB를 다시 만들 수 있는 유일한 근거(ADR-049 #15·rebuild 입력)이므로, 잘못된 자동 삭제는 복구 불가능한 손실이다.

## 결정

1. **기본 원칙 — 등록 완료 원천 archive 자동 삭제 금지.** `available`/`validating`/`missing` 상태의 등록 완료 archive는 어떤 자동 경로(janitor, reconcile, 용량 임계값 등)로도 삭제하지 않는다. archive 삭제는 명시적 사용자(admin) 작업으로만 일어난다.
2. **유일한 자동 cleanup은 T-203c janitor의 미완 multipart abort + session 만료 전이뿐이다(ADR-049 #20 재확인).** janitor는 RustFS에 저장 완료된 object를 절대 자동 삭제하지 않는다.
3. **용량 임계값은 경고(WARNING)일 뿐 자동 삭제 트리거가 아니다.** `source_storage_capacity_limit_bytes` 설정과 T-211 용량 metric/카드를 근거로, 임계값 초과 시 `over_threshold`와 정리 권장(retention recommendation)을 surfacing한다. 권장 대상은 등록 archive가 아니라 정리 가능한 bytes(soft_deleted + quarantined + 미등록 stored object)와 그 object 수다.
4. **`soft_deleted`/`quarantined` object retention.** soft-delete된 group/file과 격리(quarantined) object는 RustFS object를 보존한 채 무기한 유지한다(자동 만료 없음). soft_deleted는 T-203c `restore`(RustFS head/hash 재검증)로 되살릴 수 있다.
5. **미등록 stored object의 import-or-delete SLA.** 등록 deadline이 지난 stored object는 reconcile에서 `registration_expired`로, session·origin이 없는 object는 `object_missing_db`로 분류한다(자동 삭제하지 않음). 운영자는 reconcile resolve(import/extend/delete) 또는 아래 일괄 hard-delete로 수동 결정한다.
6. **`destructive_admin` typed-confirmation 기반 bulk hard-delete/restore 표면.** 일괄 hard-delete는 `destructive_admin` role과 정확한 typed confirmation **`HARD-DELETE-SOURCES`**(T-205b `REBUILD-PROMOTE {id}` / T-208 `ROLLBACK {id}` 패턴 동형)를 요구한다. 대상은 `soft_deleted`/`quarantined` 등록 파일과 미등록 stored object(`object_missing_db`/`registration_expired`)뿐이다. **active match set이 참조하는 정본 object는 절대 삭제하지 않는다**(T-204 `guard_object_deletion` 규칙 재사용). 개별 복구는 기존 T-203c restore/T-204 `restore_soft_deleted` resolve로 충분하므로 별도 bulk restore 표면은 추가하지 않는다.
7. **삭제 전 manifest/export 확인(pre-delete safety).** 일괄 hard-delete 직전, 완료된 `db_backup` manifest/export가 존재하거나 운영자가 `manifest_ack=true`로 명시 승인해야 한다. 둘 다 없으면 작업을 거부한다.
8. **audit + metric + UI 경고.** 각 hard-delete는 `source.hard_delete` audit event로 기록하고, RustFS 오류 시 registry state를 `delete_failed`로 둔다(성공은 `hard_deleted`). hard-delete 결과는 `kor_travel_geo_source_hard_deletes_total` metric으로 노출하고, 용량 카드는 임계값 초과·정리 권장을 경고로 보여준다.

## 근거

- 원천 archive는 serving DB rebuild의 유일한 근거라 자동 삭제 위험이 비대칭적으로 크다. 보존을 기본값으로 두고 삭제는 항상 사람의 명시 결정으로 제한해야 한다.
- 그러나 무한 보존만으로는 운영 저장소가 계속 커지므로, 자동 삭제 대신 "정리 가능 대상 surfacing + 안전장치를 둔 수동 일괄 삭제"가 보존 안전성과 운영성을 동시에 만족한다.
- 정본(active match set 참조) object 삭제 금지는 이미 T-204 reconcile guard로 검증된 규칙이라, 같은 규칙을 일괄 경로에서도 재사용하면 일관성과 안전성이 유지된다.
- 삭제는 비가역적이므로 typed confirmation + 백업 manifest/ack 이중 안전장치를 둔다.

## 결과(긍정)

- 등록 archive 손실 위험 없이 저장소 용량을 운영자가 안전하게 관리할 수 있다.
- reconcile/soft-delete/용량 metric과 정책이 한 ADR로 정합된다(중복 표면 없음 — T-204 guard, T-203c restore, T-211 capacity 재사용).
- 모든 삭제가 audit·metric으로 추적된다.

## 결과(부정)

- 운영자가 수동으로 정리하지 않으면 soft_deleted/quarantined/미등록 object가 누적될 수 있다(자동 만료 없음). 이는 surfacing(용량 카드)으로 완화한다.
- archive tier(저비용 저장소 자동 이전)는 본 ADR 범위에서 제외하고, 필요해지면 별도 ADR로 다룬다.

## 후속

- (open) archive tier 전환(예: cold storage 이전)이 실제로 필요해지면 별도 ADR로 정한다.
- (open) UI "정리 대상" 일괄 삭제 다이얼로그는 백엔드 표면(`POST /v1/admin/source-files/bulk-hard-delete`) 위에 T-212 후속으로 추가한다.
