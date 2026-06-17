# T-238 백업 manifest 원천 3자 reconcile

## 목적

T-237은 백업 생성 시점에 active match set의 RustFS object 존재 여부를 best-effort로 `source_inventory_verification`에 기록한다. T-238은 운영자가 필요할 때 백업 `manifest.json`의 `source_match_set.items[].files[]`를 현재 DB `ops.source_files`와 RustFS `HEAD` 결과에 다시 대조하는 opt-in 검증이다.

검증은 PostgreSQL/RustFS를 직접 구동하지 않는다. 이미 동작 중인 DB와 RustFS bucket에 접속할 수 있을 때만 실행한다.

## 실행

백업 artifact id 기준:

```bash
ktgctl backup reconcile-source --artifact-id <artifact_id> --output artifacts/t238/report.json
```

manifest 파일 기준:

```bash
ktgctl backup reconcile-source --manifest-path /path/to/manifest.json
```

불일치가 있으면 non-zero로 올려야 하는 운영 점검에서는 `--enforce`를 붙인다. `--enforce`는 report의 `ok=false`일 때 exit code `2`로 종료한다.

## 판정

Report는 파일 단위 row와 summary count를 낸다.

| status | 의미 |
|--------|------|
| `present` | manifest object_key가 RustFS에 있고 size/ETag가 기대값과 맞으며 DB row도 manifest와 일치 |
| `missing` | RustFS `HEAD`에서 object를 찾지 못함 |
| `etag_mismatch` | RustFS ETag가 manifest 또는 DB의 `object_etag`와 다름 |
| `size_mismatch` | RustFS size가 manifest `size_bytes`와 다름 |
| `db_missing` | RustFS object는 있지만 manifest의 `source_file_id`/`object_key`에 맞는 DB row가 없음 |
| `db_mismatch` | DB row의 `object_key`/`sha256`/`size_bytes`가 manifest와 다름 |
| `object_key_missing` | legacy/불완전 manifest라 파일 entry에 `object_key`가 없음 |

Manifest에 `object_etag`가 있으면 그 값을 우선 비교한다. 없으면 현재 DB row의 `object_etag`를 사용한다. ETag는 SHA-256으로 간주하지 않으며, T-238은 `HEAD` 기반 빠른 정합성 검증만 수행한다. RustFS `HEAD` 404는 `missing`, 그 밖의 HTTP 오류나 `content-length` 누락처럼 object 존재 여부를 확정할 수 없는 응답은 `head_error`로 분리한다. 따라서 권한/서버 오류나 불완전한 HEAD 응답이 `missing` 또는 size `0`으로 기록되지 않는다.

## Graceful skip

다음 상황에서는 실패 대신 `skipped=true` report를 낸다.

- backup manifest에 `source_match_set` block이 없는 legacy 백업
- `KTG_RUSTFS_ENABLED=false`이거나 RustFS credential이 없어 client를 만들 수 없는 환경

이 경우 백업/복원 자체를 실패시키지 않는다.

## 테스트

기본 CI는 DB/RustFS 없이 단위 테스트만 실행한다.

```bash
python -m pytest tests/unit/test_t238_manifest_source_reconcile.py -q
```

실제 DB/RustFS live 검증은 명시 opt-in이다.

```bash
KTG_TEST_PG_DSN=postgresql+psycopg://... \
KTG_TEST_RUSTFS_SOURCE_RECONCILE=1 \
KTG_TEST_BACKUP_MANIFEST=/path/to/manifest.json \
python -m pytest tests/integration/test_t238_manifest_source_reconcile_live.py -q
```

`KTG_TEST_RUSTFS_SOURCE_RECONCILE=1`을 두지 않으면 integration test는 skip된다.
