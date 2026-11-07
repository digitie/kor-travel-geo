# 현재 장비의 Geo 조회 성능 개선 검토

작성일: 2026-11-07. 사용자가 지정한 현재 장비 안에서 원인 발굴 → 개선 → 검증을 세 차례 수행한다.
실측 정본은 [회차별 수치](current-hardware-performance-three-cycles.json), 진행·실패 복구 기록은
[실행 계획](../execplan/geo-readonly-performance-three-cycles.md)에 둔다.

## 장비와 병목

ARM 4코어·약 7.5GiB RAM이며 API와 PostgreSQL의 메모리 한도는 각각 1.5GiB·3GiB다.
PostgreSQL 18.6의 shared_buffers는 768MiB다. MV 두 개와 인덱스의 합계는 약 7.5GiB,
그중 인덱스가 약 4.73GiB다. 모든 서빙 산출물을 DB 메모리에 올리는 방식은 이 예산에 맞지 않는다.
MV의 all-visible 비율은 이미 약 99.98%여서 추가 VACUUM을 첫 해결책으로 삼지 않았다.

누적 pg_stat_statements에는 이전 코드와 벤치마크가 섞인다. 이를 현재 운영의 QPS·p95나
요청 비율로 해석하지 않았다. 같은 장비의 결과 비교와 실제 실행계획·DB 명령 수를 사용했다.
초기화·접속 시간과 SQL 실행시간도 구분했다.

## 적용한 방향

1. 지역 조건 reverse의 반경을 후보 단계에 적용한다. 지역 전체를 정렬하던 대표 계획의 실행은
   424.002→11.923ms, buffer hit는 665→120이다. 조건 없는 조회까지 일괄 변경한 후보는 일부
   표본이 악화돼 제외했다. 동률·반경 경계·NULL 좌표·행정구역 조건을 실제 PostGIS로 확인했다.
2. 기본 64MiB의 릴리스별 메모리 결과 캐시를 둔다. 반복 v2 geocode의 라이브러리 경로 p50은
   53.808→1.656ms, geometry reverse는 282.536→2.821ms다. 8종·변형별 24개 표본에서 결과
   불일치·오류 0이며 반복 적중 구간 DB 명령은 0회다. 같은 키 32건의 동시성 8 요청에서 DB 캐시
   UPDATE는 32→1회다. HTTP 인증·전송은 포함하지 않은 값이다.
3. 캐시에 없는 정확 도로명주소는 도로명·본번·부번·지하 여부를 함께 찾는 복합 인덱스로 개선한다.
   기존 도로 코드 인덱스는 도로명 문자열로 조회할 때 바로 활용되지 않았다. 독립 PostGIS의
   부번·지하·페이지·정확한 total·동명 주소·NULL 좌표 검사와 마이그레이션 왕복을 통과했다.
   운영 14종 결과가 같고 대표 서버 실행 12.225→0.452ms, 버퍼 접근 400→5다. 약 278.5MiB의
   인덱스는 187.296초에 생성했다. 도로명에 text_pattern_ops를 사용해 동등 비교를 보존하면서
   로케일 문자열 정렬 비용을 피했다. 실제 추가 용량과 악화 표본도 회차별 수치에 보존한다.

메모리 캐시는 `KTG_CACHE_MEMORY_MAX_BYTES=0`으로 끌 수 있다. TTL은 300초이고 기존 지문 캐시의
10초 TTL을 유지한다. 지문이 없거나 외부 fallback을 요청한 경우, 실패·부분 geometry 실패는
보관하지 않는다. `query_id`와 가변 응답을 호출마다 분리하며 마지막 대기자가 취소하면 DB 작업도
취소한다. 직렬화 버퍼의 과다 할당을 수정한 뒤 5만 고유 결과 최고 RSS는 약 148MiB였다.
보관 바이트 예산과 프로세스 전체 RSS는 다른 값이다. 고유 입력의 지연 개선은 주장하지 않는다.

## 검토한 다른 방안

| 방안 | 판단과 근거 |
| --- | --- |
| DB 영속 캐시를 SELECT만 수행하도록 변경 | 메모리 적중에서 UPDATE 자체를 제거했다. 첫 조회·프로세스 간 공유에는 기존 영속 캐시를 남겨 hit 통계 계약을 유지한다. 메모리 hit·miss·공유·우회는 별도 유한 label counter로 관측한다. |
| 별도 Redis·검색 엔진 | 이번에는 도입하지 않는다. 같은 장비의 RAM·운영 프로세스를 더 소비하며 현재는 프로세스 내부 캐시로 반복 요청 DB 비용을 제거할 수 있다. |
| MV·비정규화 확대 | 이미 건물 대표 좌표·주소와 검색 투영 MV가 있다. 넓은 주소·GeoJSON을 더 복제하기보다 실제 미적중 병목이 입증된 좁은 투영을 다음 후보로 삼는다. 원천 재적재는 필요하지 않다. |
| 짧은 검색어의 용어 사전·매칭 건수 사전 계산 | `강남` 같은 2글자 검색의 첫 조회에는 text-search MV Seq Scan·유사도 계산·정확한 total 비용이 남는다. 같은 검색은 캐시로 줄였으나 첫 조회는 별도 과제다. 용어·지역·정렬의 동등성과 산출물 크기·재생성 비용을 입증한 뒤 도입해야 한다. total을 근삿값으로 바꾸거나 후보를 임의 절단하지 않는다. |
| 상세 주소 join을 페이지 뒤로 지연 | 기존 T-138에서 정확한 total을 유지한 후보의 c64 p95가 289.146→307.716ms로 악화된 기록이 있어 무조건 재적용하지 않는다. 실제 새 workload의 실행계획이 달라질 때 다시 비교한다. |
| 중복·미사용 인덱스 정리 | target MV의 두 trigram·4326 GiST·좌표 출처 인덱스 합계 약 464MiB는 조사 후보다. 누적 idx_scan이 작다는 사실만으로 사용처 부재나 현재 RAM 점유를 단정할 수 없어 이번에는 삭제하지 않는다. 향후 호출자·관리 쿼리·다음 적재·회귀 workload까지 확인한다. |
| covering index·index-only scan | 주소·GeoJSON 전체를 INCLUDE하면 인덱스가 커진다. 현재 all-visible 비율은 양호하므로 좁은 키·필수 정렬 열부터 실제 heap fetch 감소와 크기를 비교한다. GIN을 index-only 용도로 가정하지 않는다. |
| pool·worker·work_mem 확대 | 4코어·DB 3GiB 한도에서 일괄 확대하지 않는다. work_mem은 정렬·hash 연산과 동시 요청마다 소비된다. 과거 pool 64는 exact와 fuzzy/search에 다른 영향을 보였다. 캐시 미적중의 대기·오류까지 포함한 부하 시험으로 따로 결정한다. |
| prepared statement·planner 강제 | 기존 prepare_threshold=5를 유지한다. 실제 reverse 측정은 custom plan을 사용했으며 강제 generic plan timeout을 실제 장애 원인으로 오인하지 않았다. 전역 planner 옵션·similarity threshold를 바꾸지 않는다. |
| 사전 적재·pg_prewarm | 작은 인기 키만 제한적으로 예열하는 방식은 후보다. 7.5GiB 전체 산출물을 예열하면 다른 서비스·OS cache를 밀어낼 수 있어 일괄 예열하지 않는다. |
| 지역 파티션 | 보류한다. 정적 주소의 전국 공통 도로명·공간 조회를 지역 파티션으로 나눌 때의 다중 탐색·경계 후보 비용과 기존 단일 MV보다 줄어드는 I/O를 먼저 증명해야 한다. |
| 서버 복제·장비 증설 | 사용자가 현재 장비 내 개선을 지정했으므로 이번에는 수행하지 않는다. |

## 검증과 운영상 한계

공개 API 인증은 기존 경로로 매번 수행한다. 라이브러리의 캐시 적중 SQL 0회를 외부 HTTP 전체의
SQL 0회로 해석하지 않는다. 메모리 캐시는 프로세스별이며 재시작하면 비어 있다. 영속 캐시·원천·
좌표 격리 판정·정상 릴리스의 값은 유지한다.

공유 장비의 소표본에서 개선 배수나 전체 운영 QPS를 보장하지 않는다. p95 이상치·고유 요청의
추가 직렬화 비용·초기 구현에서 발견해 고친 추적 ID·메모리 문제도 기록했다. 최종 코드는
WSL ext4 필수 검사·실제 PostGIS·정확한 최종 HEAD의 CI·리뷰 창을 통과한 뒤 병합한다.

근거 문서: [T-138 실험](../t138-read-heavy-serving-performance.md),
[ADR-075](../adr/075-bounded-memory-result-cache.md),
[PostgreSQL index-only scan](https://www.postgresql.org/docs/18/indexes-index-only-scans.html),
[pg_trgm](https://www.postgresql.org/docs/18/pgtrgm.html),
[메모리 자원 설정](https://www.postgresql.org/docs/18/runtime-config-resource.html),
[인덱스 연산자 클래스](https://www.postgresql.org/docs/18/indexes-opclass.html),
[PostGIS ST_DWithin](https://postgis.net/docs/ST_DWithin.html).
