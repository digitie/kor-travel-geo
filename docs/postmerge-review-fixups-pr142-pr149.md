# PR #142/#145/#149 리뷰 후속 반영

## 배경

2026-06-16 전체 PR review thread 스캔에서 이미 머지된 source registry 계열 PR에 남아 있던 current unresolved thread 7건을 확인했다.

| PR | 파일 | 지적 요약 | 반영 |
|----|------|-----------|------|
| #142 | `api/routers/admin.py` | register 시점 coverage 검증이 빈 `PartManifest`를 full structure validator에 넘겨 member 누락으로 실패할 수 있음 | register 전용 `validate_group_coverage()`를 추가해 slot coverage만 판정 |
| #142 | `infra/source_group_service.py` | `revalidate_group()`가 자식 상태 변경 전 aggregate를 계산해 이전 child state가 group state에 남을 수 있음 | 자식 상태를 먼저 `available`/`quarantined`로 정리한 뒤 `recompute_group_aggregates()` 호출 |
| #145 | `infra/source_janitor.py` | janitor abort key가 실제 multipart upload key와 다름 | upload endpoint와 같은 `source-files/<category>/<yyyymm>/<group>/<session>/<slot>/archive` key를 session row에서 재구성 |
| #145 | `infra/source_group_service.py` | soft-delete 직후 recompute가 `soft_deleted`를 되돌릴 수 있음 | 기존 pure recompute가 모든 child 삭제 상태를 `soft_deleted`로 접는 경로를 유지하고 통합 테스트로 회귀 방지 |
| #149 | `infra/source_reconcile.py` | `object_limit` 설정이 RustFS list 결과에 적용되지 않음 | `RustfsClient.list_objects(prefix, limit=...)`를 추가하고 limit 초과 시 fail-fast |
| #149 | `infra/source_reconcile.py` | `import_object` resolve가 실제 등록 없이 item을 resolved로 닫음 | register flow 필요 상태로 차단하고 item을 open 유지 |
| #149 | `infra/source_reconcile.py` | RustFS client 없이 `delete_object`가 DB row를 `hard_deleted`로 바꿀 수 있음 | object가 존재한다고 재확인된 경우 RustFS client가 없으면 `blocked:rustfs_unavailable`로 차단 |

## 반영 상세

### register coverage 검증 분리

등록 endpoint는 storage-first 흐름이라 archive 내부 member를 아직 materialize하지 않는다. 따라서 `validate_group_manifest()`를 직접 호출하지 않고, 새 순수 helper `validate_group_coverage()`로 기대 slot의 present/missing만 판정한다. full SHP/TXT member 검증은 기존 `POST /source-file-groups/{id}/validate` 경로에 남긴다.

### source group 상태 재계산 순서

`revalidate_group()`은 validation row 기록 뒤 자식 file 상태를 먼저 바꾼다. `passed`/`warning`이면 `available`, 실패이면 기존 `available` 또는 `validating` 자식을 `quarantined`로 내린 뒤 aggregate를 다시 계산한다. 이 순서가 group state와 child state를 같은 transaction 안에서 일치시킨다.

`soft_delete_group()`은 기존 `recompute_group_derived()`의 “모든 child가 deleted 상태이면 group도 `soft_deleted`” 규칙에 의존한다. 이 규칙이 깨지면 통합 테스트에서 `resp.state == "soft_deleted"`가 실패한다.

### janitor abort key 정합성

janitor는 더 이상 `session_id/part_key` placeholder key를 쓰지 않는다. upload session row의 `prefix`, `category`, `user_yyyymm`, `source_file_group_id`, `source_upload_session_id`, `part_key`로 실제 upload endpoint와 같은 RustFS object key를 구성한다. 이 키와 `multipart_upload_id`를 함께 전달해야 S3 `AbortMultipartUpload`가 실제 unfinished upload를 찾는다.

### reconcile resolve 안전장치

`import_object`는 registry insert를 수행하지 않으므로 resolve item을 닫지 않는다. 응답은 `blocked:registration_flow_required`이고 DB item state는 `open`으로 남아, operator가 register flow로 처리하거나 재스캔할 수 있다.

`delete_object`는 object가 존재한다고 판단되는데 RustFS client가 없으면 DB hard-delete를 하지 않는다. storage 삭제가 성공했거나 object가 이미 absent인 경우에만 DB row hard-delete가 뒤따른다.

## 검증

- `python -m ruff check ...` 통과
- `python -m mypy src\kortravelgeo\infra\source_reconcile.py src\kortravelgeo\infra\source_janitor.py src\kortravelgeo\core\source_validation.py src\kortravelgeo\api\routers\admin.py src\kortravelgeo\infra\source_group_service.py src\kortravelgeo\infra\rustfs.py` 통과
- `python -m pytest tests\unit\test_t203a_upload_sessions.py tests\unit\test_t203b_register_recompute.py tests\unit\test_t203b_register_api.py tests\unit\test_t203c_janitor_restore.py -q` 통과
- `python -m pytest tests\integration\test_t210_source_integration.py -q`는 현재 Windows 환경에서 DB-gated 케이스 대부분이 skip됐고, 실행 가능한 3개 케이스는 통과했다. live PostGIS 케이스는 WSL ext4 미러와 `KTG_TEST_PG_DSN` 설정에서 추가 확인한다.
