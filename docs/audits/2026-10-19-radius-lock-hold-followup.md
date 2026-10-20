# region_radius_parts 잠금 보유 후속 조사

## 현재 보장과 남은 위험

#590은 잠금 **획득 대기**를2초씩, 30초 간격/최대3600초 예산으로 제한했다.
D4=21600을 바꾸지 않는다. 현재 postload.refresh_region_radius_parts는 같은 transaction에서
ACCESS EXCLUSIVE를 획득한 뒤 TRUNCATE, ST_Subdivide 재생성, ANALYZE,
publication_guard를 수행하고 commit한다. 따라서 획득 후 계산하는 동안 reader 차단은
남는다. 대기 상한을 보유 상한으로 설명하면 안 된다.

이번 조사에서는 실제 잠금 보유 시간을 측정하지 않았다. 이미 알려진 standalone
mv_refresh 전체 시간은 해당 테이블의 잠금 보유 시간과 같지 않다.

## 작은 후속에서 먼저 확인할 사항

새 표에 먼저 생성하고 짧은 이름 교체를 하는 후보는 계산 구간의 reader 차단을 줄일 수
있지만 즉시 적용할 한 줄 수정이 아니다. 구현 전 실제 pg_depend/뷰·FK·권한·소유자와
prepared statement 의존성, 기존 인덱스 이름을 조사해야 한다. 이름이 바뀌어도 OID에
결박된 객체는 자동으로 새 표를 보지 않는다.

동시 writer 직렬화, 고유 임시 이름과 이전 표 보존, rename 시 lock_timeout,
실패 rollback/소유권 상실/publication_guard, 첫 생성 경로, cleanup이 남의 표를
삭제하지 않는 조건을 함께 검증해야 한다. 새 표 계산 시 원천 snapshot의 일관성과
기존표/새표 결과 동등성, 오래 열린 reader와 backup 충돌도 포함한다.

먼저 격리 PostGIS에서 보유시간과 reader 지연을 비교하고 중간 실패 반례를 만든 뒤,
효과가 확인된 별도 작은 PR에서 두 독립 리뷰와 배포 검증을 진행한다.
운영 DDL이나 긴 rebuild는 이번 Track 수용을 위해 실행하지 않았다.

## 구현(2026-10-20, G-01 후속 a2)

조사 항목은 이렇게 닫았다. **한 transaction**에서 `region_radius_parts_next`를 채우고(라이브 미접촉),
교체 잠금만 savepoint에서 #590 예산(2 s·30 s·1 h)으로 재시도한 뒤 DROP(무CASCADE)→RENAME→제약·인덱스
이름 복원→commit한다. 그래서 위의 "고유 임시 이름·이전 표 보존·cleanup이 남의 표를 지우지 않는 조건"은
필요 없어졌다 — `_next`는 commit된 적이 없어 다른 세션·`pg_dump`가 볼 수 없고, 실패는 전체 rollback이라
이전 표가 그대로 남는다(고정 이름의 commit된 `_next`가 있으면 손으로 만든 잔재로 보고 DROP한다).
동시 재생성은 advisory xact lock으로 직렬화한다. 원천 snapshot 일관성은 이전과 같은 한 문장 INSERT다.

교체 직전(배타 잠금 아래) 라이브 표가 새 표와 소유자·권한·저장 옵션·인덱스 정의가 다르거나 트리거·정책·
일반 의존 객체(뷰·FK — 자기 CHECK 제약 제외)가 있으면 교체를 거부한다. CHECK 제약이 자기 열에 `n` 의존을
남기는 것은 격리 PostGIS 첫 실행에서 드러났다(그 예외가 없으면 모든 교체가 거부됨).

남은 한계: 재시도 동안 transaction이 열려 있다(xid·원천 ACCESS SHARE·advisory — 막고 있는 reader가 이미
잡는 창과 같다). 교체마다 OID가 바뀌어, snapshot 뒤 교체가 commit되고 나서 표를 잠그는 `pg_dump`는
실패한다(크게 실패, 다음 백업 무관). 실제 운영 보유시간은 측정하지 않았다(운영 DDL·rebuild 미실행).
**배포 전 확인(소유자 창)**: 운영 DB에서 읽기 전용으로
`SELECT relowner::regrole, relacl, reloptions, relhastriggers, relrowsecurity FROM pg_class WHERE oid = 'region_radius_parts'::regclass`
가 앱 role·NULL·NULL·f·f인지(아니면 첫 교체가 거부된다).
