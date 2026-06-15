# T-207 epost 수동 server-fetch

T-207은 `/admin/source-files` 업로드 탭의 `epost 받기` 버튼에서 시작하는 수동 서버 fetch 경로다. 브라우저 파일 업로드가 아니라 서버가 설정된 epost OpenAPI(`KTG_EPOST_API_KEY`, `KTG_EPOST_DOWNLOAD_URL`)로 ZIP을 내려받고, ZIP 안의 사서함 또는 다량배달처 텍스트 파일을 골라 RustFS source registry에 등록한 뒤 별도 우편번호 적재 job을 enqueue한다.

이 경로는 핵심 `source_match_set`과 `rebuild-db`에 포함하지 않는다. epost 사서함·다량배달처는 보조 우편번호 테이블(`postal_pobox`, `postal_bulk_delivery`)을 갱신하는 enrichment source이며, 전국 도로명주소 serving release의 core source set을 바꾸지 않는다.

## API

```text
POST /v1/admin/source-files/epost-fetch
```

요청:

```json
{
  "category": "epost_pobox_full",
  "user_yyyymm": "202606",
  "enqueue_load": true
}
```

`category`는 `epost_pobox_full` 또는 `epost_bulk_full`만 허용한다. `download_kind`를 생략하면 사서함은 `4`, 다량배달처는 `1`을 사용한다. 성공 응답은 등록된 upload session, source group 등록 결과, 선택된 파일명, T-120 검증 요약, enqueue된 `pobox_load` 또는 `bulk_load` job id를 포함한다.

## 처리 순서

1. `ops.source_upload_sessions`에 `single_file` 세션을 만든다.
2. epost ZIP을 `settings.loader_data_dir/epost/server-fetch/<session_id>/download/` 아래로 내려받는다.
3. ZIP을 `.../extract/` 아래로 푼 뒤 `discover_epost_files()`로 사서함 또는 다량배달처 텍스트 파일을 찾는다.
4. T-120 공통 검증 모듈(`validate_pobox_file`, `validate_bulk_file`)로 행수, 필수 컬럼, 우편번호, 중복 sanity를 확인한다.
5. 선택한 텍스트 파일을 RustFS `source-files/<category>/<yyyymm>/<group_id>/<session_id>/archive/<filename>`에 저장하고 upload session part를 완료 기록한다.
6. `SourceGroupRegistrar`로 `ops.source_file_groups`/`ops.source_files`에 등록한다. `compression_format`은 `txt`로 기록한다.
7. `enqueue_load=true`이면 `pobox_load` 또는 `bulk_load` job을 queue에 넣는다. loader payload의 `path`는 서버에 보존된 추출 텍스트 파일 경로다.

## 실패 상태

실패는 source registry row를 만들지 않고 upload session 상태로 남긴다.

| 상태 | 의미 |
| --- | --- |
| `failed_upload` | epost API 키/다운로드/응답 형식 문제 |
| `failed_extract` | ZIP 해제 실패 |
| `failed_structure` | 사서함·다량배달처 파일 누락 또는 T-120 검증 실패 |
| `failed_rustfs_put` | RustFS 저장 실패 |
| `failed_register` | RustFS 저장 후 registry 등록 실패. 같은 세션으로 register 재시도 가능 |

`user_yyyymm`이 현재 `tl_juso_text.source_yyyymm` 대표 기준월과 다르면 hard error가 아니라 `warnings`에 남긴다. 이 자료는 core rebuild와 독립된 우편번호 보조 자료이기 때문이다.

## 검증

- `tests/unit/test_t207_epost_server_fetch.py`: 네트워크와 RustFS를 fake로 치환해 기본 `download_kind`, 상태 전이, T-120 검증 재사용, ZIP 구조 불일치 실패 상태를 검증한다.
- `kor-travel-geo-ui/tests/unit/source-files-panel.test.tsx`: 업로드 탭 epost 카드가 `POST /admin/source-files/epost-fetch`를 호출하고 최근 결과에 load job id를 표시하는지 검증한다.
