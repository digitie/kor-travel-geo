# T-322 Dagster instance storage 드라이버 검증 (`postgresql+psycopg2://` · `postgres_db` · SQLAlchemy 2.1)

## 배경

T-316에서 본체 SQLAlchemy 허용 범위를 2.1까지 넓혔지만 `kor-travel-geo-dagster`는 `sqlalchemy<2.1`을
유지했다. SQLAlchemy 2.1은 `postgresql://` URL의 기본 DBAPI를 psycopg2 → psycopg 3으로 바꾸고
(`sqlalchemy/dialects/postgresql/__init__.py` — 2.0.54:97 `base.dialect = dialect = psycopg2.dialect`,
2.1.1:99 `… = psycopg.dialect`), manager는 Dagster 메타 DB URL을 scheme 없는 `postgresql://…`로 준다
(`KOR_TRAVEL_GEO_DAGSTER_PG_URL` → 세 geo Dagster 서비스의 `KTG_DAGSTER_PG_URL` →
`kor-travel-geo-dagster/docker/dagster.yaml`의 `storage.postgres.postgres_url`). T-316 리뷰에서
2.1 + bare URL이면 RUN_START의 `NOTIFY run_events, %(notify_id)s`가 `psycopg.errors.SyntaxError`로
실패함을 실측했다.

대안으로 URL을 `postgresql+psycopg2://`로 명시하는 안이 나왔지만, dagster_postgres의 일부 경로(event
watcher의 LISTEN/NOTIFY, alembic 설정, 연결 helper)가 URL을 `psycopg2.connect()`/libpq에 그대로 넘기면
libpq가 `+psycopg2` scheme을 거부한다는 우려가 있었다. 이 문서는 그 우려를 소스와 실측으로 확인한다.
운영(n150)·`.env`·컨테이너는 건드리지 않았다.

## 결론 요약

1. **dagster_postgres의 모든 런타임 경로는 SQLAlchemy `create_engine`을 거친다.** URL을
   `psycopg2.connect()`/libpq에 그대로 넘기는 런타임 경로는 pin 범위(`dagster-postgres>=0.25,<1`) 전체에
   없다. event watcher는 LISTEN이 아니라 SQLAlchemy polling(`SqlPollingEventWatcher`)이고, alembic은
   URL이 아니라 이미 연결된 SQLAlchemy `Connection`을 받는다. 우려는 **근거 없음**으로 판정한다.
2. **`postgresql+psycopg2://`는 SQLAlchemy 2.0·2.1 둘 다에서 end-to-end 통과**(migrate · run storage ·
   event log NOTIFY · event watcher · schedule storage · daemon tick→queued run · webserver GraphQL).
   기존 DB(현재 운영과 같은 2.0 + bare URL로 만든 DB)에 URL만 바꿔 붙여도, 그 상태에서 2.1로 올려도 통과.
3. **structured `postgres_db:` 형식은 scheme 문제를 피하지 못한다.** dagster가 내부에서
   `scheme`(기본값 `postgresql`)으로 URL을 다시 만든다. 그래서 2.1에서는 bare URL과 똑같이 실패하고,
   `scheme: postgresql+psycopg2`를 줄 때만 통과한다. "가장 깔끔한 해법"이 아니다.
4. **2.1 + psycopg 3의 실패는 NOTIFY 하나가 아니다.** webserver 모드의 connect hook이 DBAPI 연결에
   `with conn:`을 써서, psycopg 3에서는 그 자리에서 연결이 **닫힌다** → 모든 GraphQL 질의가 HTTP 500
   `(psycopg.OperationalError) the connection is closed`. 그런데 daemon `liveness-check`와 manager
   webserver healthcheck(`repositoriesOrError`)는 **통과**한다 — 겉으로 healthy인 채 run이 하나도 못 돈다.
5. 권고: manager 값을 `postgresql+psycopg2://…`로 바꾼다(현재 2.0 이미지에서는 동작 변화 0, 세 서비스
   재생성만 필요, DB migration 불필요). **pin은 유지**하고, 해제는 아래 조건을 모두 채운 뒤 별도 PR로.

## 검증 환경

| 항목 | 값 |
|------|----|
| 해석 기준 | `dagster.Dockerfile`의 `".[loaders]" ./kor-travel-geo-dagster` 한 번 resolve를 `uv pip compile --python-version 3.12`로 재현(2026-09-29) |
| 해석 결과 | dagster/dagster-webserver/dagster-graphql 1.13.24, dagster-postgres 0.29.24, SQLAlchemy 2.0.54, psycopg2-binary 2.9.13(dagster-postgres의 `Requires-Dist`), psycopg 3.3.6, alembic 1.20.0 |
| venv | Python 3.12.13, 본체 `.` + `./kor-travel-geo-dagster` (GDAL `[loaders]` 제외 — storage 경로와 무관). 2.1 venv는 `--override "sqlalchemy[asyncio]>=2.1.1,<2.2"` → 2.1.1 |
| DB | throwaway `postgres:16`(16.14) 컨테이너, `127.0.0.1:15932`, 셀마다 빈 DB |
| 설정 | 운영과 같은 `storage.postgres` 한 블록 + `telemetry.enabled=false`, run_coordinator/launcher 기본값(QueuedRunCoordinator + DefaultRunLauncher) |
| 코드 위치 | op 1개짜리 job + `* * * * *` schedule(`DefaultScheduleStatus.RUNNING`), `python_file` workspace |

dagster 자체는 `sqlalchemy<3,>=1.0`만 요구한다 — 2.0에 묶는 것은 우리 pin뿐이다.

## 셀마다 수행한 조작

1. `dagster instance migrate`
2. `dagster job execute -f job_def.py -j t322_job` (CLI run — run storage + event log, RUN_START NOTIFY 포함)
3. in-process probe (`DagsterInstance.get()`):
   - run storage: `execute_in_process(instance=…)` → run `SUCCESS`
   - NOTIFY 전달: **검증 대상 URL과 무관한** psycopg2 연결(libpq kwargs)로 `LISTEN run_events` → 수신 건수
   - event watcher: `event_log_storage.watch(run_id, None, cb)` → `RUN_SUCCESS`까지 수신
   - schedule storage: `add/get/delete_instigator_state` 왕복
   - webserver engine: `instance.optimize_for_webserver(...)` 뒤 run·log·instigator 조회 3회
4. `dagster-daemon run` 60~105초(다음 분 경계의 schedule tick → queued run → DefaultRunLauncher 실행) +
   종료 직전 `dagster-daemon liveness-check`, daemon 로그 traceback 수
5. `dagster-webserver` 기동 → GraphQL `runsOrError` 2회(+ `instance.daemonHealth`)
6. SQL 요약: `runs`·`job_ticks` 상태, `instigators`, `daemon_heartbeats`, `event_logs`, `alembic_version`

## 실측 결과

URL 형식: **bare** = `postgresql://…`, **+psycopg2** = `postgresql+psycopg2://…`,
**db** = `postgres_db:`(username/password/hostname/db_name/port, scheme 기본값),
**db+scheme** = `postgres_db:` + `scheme: postgresql+psycopg2`.

| SA | URL 형식 | 드라이버 | migrate | run storage (CLI·in-process) | event log NOTIFY | event watcher | schedule storage | daemon | webserver |
|----|----------|----------|---------|------------------------------|------------------|---------------|------------------|--------|-----------|
| 2.0.54 | bare (현 운영) | psycopg2 | PASS | PASS (`SUCCESS`) | PASS (12건 수신) | PASS (12 events) | PASS | PASS — tick `SUCCESS` 1, run `SUCCESS`, heartbeat 6종, liveness PASS, traceback 0 | PASS — GraphQL 200, runs `SUCCESS` 3 |
| 2.0.54 | +psycopg2 | psycopg2 | PASS | PASS | PASS (12) | PASS (12) | PASS | PASS (동일) | PASS (동일) |
| 2.0.54 | db | psycopg2 | PASS | PASS | PASS (12) | PASS (12) | PASS | PASS (동일) | PASS (동일) |
| 2.0.54 | db+scheme | psycopg2 | PASS | PASS | PASS (12) | PASS (12) | PASS | PASS (동일) | PASS (동일) |
| 2.1.1 | bare | **psycopg** | PASS | **FAIL** — `sqlalchemy.exc.ProgrammingError: (psycopg.errors.SyntaxError) syntax error at or near "$1"` / `LINE 1: NOTIFY run_events, $1;` — run 3건 모두 `NOT_STARTED` | **FAIL** (0건) | 해당 없음(성공한 run 없음) | PASS (tick `SUCCESS` 1) | **부분 FAIL** — liveness PASS·heartbeat 6종인데 tick이 만든 run의 `RUN_ENQUEUED`(`report_dagster_event`)에서 같은 SyntaxError, traceback 8 | **FAIL** — engine `psycopg.OperationalError: the connection is closed`, GraphQL HTTP 500 같은 오류. healthcheck용 `repositoriesOrError`는 200 `RepositoryConnection` |
| 2.1.1 | +psycopg2 | psycopg2 | PASS | PASS | PASS (12) | PASS (12) | PASS | PASS (tick 1, run `SUCCESS`, traceback 0) | PASS (runs `SUCCESS` 3) |
| 2.1.1 | db | **psycopg** | PASS | **FAIL** (bare와 동일 SyntaxError) | **FAIL** (0건) | 해당 없음 | PASS | **부분 FAIL** (bare와 동일) | **FAIL** (bare와 동일) |
| 2.1.1 | db+scheme | psycopg2 | PASS | PASS | PASS (12) | PASS (12) | PASS | PASS | PASS |

운영 전환 시나리오(기존 DB 재사용 — `2.0 + bare`로 만든 DB에 이어 붙임, 빈 DB 아님):

| 단계 | 결과 |
|------|------|
| 같은 2.0.54 이미지, URL만 `+psycopg2`로 (= 권고 운영 변경) | 전 항목 PASS. 기존 schedule state(RUNNING) 유지, 멈춘 사이 놓친 tick을 catch-up(tick `SUCCESS` 누적 3), runs `SUCCESS` 7, alembic `29b539ebc72a` 불변 |
| 이어서 2.1.1 + `+psycopg2` (= pin 해제) | 전 항목 PASS. runs `SUCCESS` 11, tick `SUCCESS` 5, traceback 0, alembic 불변 |

부수 확인:

- libpq는 `+psycopg2` scheme을 실제로 거부한다: `psycopg2.connect("postgresql+psycopg2://…")` →
  `psycopg2.ProgrammingError: invalid dsn: missing "=" after "postgresql+psycopg2://…" in connection info
  string`. 즉 우려 자체는 타당했지만, 아래 소스 근거대로 dagster 런타임에 그런 호출이 없다. **manager 쪽에서
  이 URL을 `psql`/`pg_dump`에 넘기는 소비자가 있으면 깨진다** — 확인 결과 소비자는 geo Dagster 세 서비스뿐이고
  (`docker-compose.yml` 2209·2275·2385행), standalone 백업(`standalone_backup.py` 80행)은 URL이 아니라
  컨테이너·DB 이름을 쓴다.
- SQLAlchemy 2.1 + psycopg2 조합에서 deprecation 경고 없음(각 셀 로그 grep).
- 2.1.1 venv에서 `import kortravelgeo_dagster.definitions` OK, Dagster 패키지 테스트 전부 통과
  (2.0.54와 동일, 이 PR의 새 테스트 포함 78 passed). 다만 dagster ephemeral(SQLite) instance teardown
  (`build_resources`) 중 SQLAlchemy pool reset 로그 `sqlite3.ProgrammingError: Cannot operate on a closed
  database`가 2.1에서는 매번 2건, 2.0에서는 가끔(공유 venv SQLAlchemy 2.0.51에서 4회 중 1회) 찍힌다 — GC
  시점 의존 teardown 잡음이고 테스트는 통과, Postgres storage와 무관(pin 해제 PR에서 한 번 더 볼 것).
- 2.1 venv를 `--override "sqlalchemy>=2.1.1,<2.2"`(extra 없이)로 만들면 greenlet이 빠져 본체 async import가
  실패한다. 2.1은 greenlet을 `[asyncio]` extra로만 끌어온다. 실제 pin 해제에서는 본체가
  `sqlalchemy[asyncio]`를 선언하므로 문제없다(override 산출물일 뿐).

## 소스 근거 (dagster-postgres 0.29.24 / dagster 1.13.24, 설치본 기준)

URL이 흘러가는 경로:

| 위치 | 내용 |
|------|------|
| `dagster_postgres/storage.py:47-58, 77` | `DagsterPostgresStorage`가 `pg_url_from_config(config_value)` 결과 하나를 run/event/schedule storage에 그대로 넘긴다 |
| `dagster_postgres/utils.py:29-42` | `pg_url_from_config` — `postgres_url`이면 **문자열 그대로**, `postgres_db`면 `get_conn_string(**postgres_db)` |
| `dagster_postgres/utils.py:45-64` | `get_conn_string(..., scheme="postgresql")` → `f"{scheme}://{userinfo}@{hostname}:{port}/{db_name}"`(58행) |
| `dagster/_core/storage/config.py:62` | `postgres_db.scheme` 필드 기본값 `"postgresql"` — structured 형식도 결국 URL이고 기본 scheme은 bare |
| `dagster_postgres/utils.py:169-182` | `create_pg_engine` → `dagster._core.storage.sql.create_engine`(= `sqlalchemy.create_engine`, `sql.py:16`) |
| `run_storage/run_storage.py:90`, `event_log/event_log.py:98`, `schedule_storage/schedule_storage.py:90` | 세 storage 모두 `create_pg_engine(self.postgres_url, …)`(AUTOCOMMIT + NullPool). webserver 모드 재생성도 같은 함수(`run_storage.py:132`, `event_log.py:138`, `schedule_storage.py:130`) |
| `run_storage.py:176`, `event_log.py:145-148`, `schedule_storage.py:172-175`, `dagster/_core/storage/sql.py:44-49, 131-154` | alembic upgrade/stamp는 `alembic_config.attributes["connection"] = conn`(SQLAlchemy `Connection`) — `run_migrations_online`이 `context.configure(connection=…)`. URL을 다시 쓰지 않는다 |
| `event_log/event_log.py:376-387` | `watch()` → `SqlPollingEventWatcher`(SQLAlchemy 조회 polling). LISTEN 경로 없음 |
| `dagster_postgres/utils.py:129-136` | `wait_for_connection` — 0.29.x는 `sqlalchemy.create_engine(conn_string)`. 런타임 호출자 없음(테스트 fixture 전용) |

`psycopg2.connect(url)` 직접 호출 이력(pin 하한까지 확인, wheel 직접 비교):

| dagster-postgres | `utils.get_conn` = `psycopg2.connect(conn_string)` | `wait_for_connection` → `psycopg2.connect` | 런타임 호출자 |
|------------------|----------------------------------------------------|---------------------------------------------|---------------|
| 0.25.0 · 0.25.11 · 0.26.0 · 0.27.3 · 0.28.0 | 있음 | 있음 | **없음**(0.28.0은 `test_fixtures`만), watcher는 이미 `SqlPollingEventWatcher` |
| 0.29.0 · 0.29.12 · 0.29.24 | 삭제 | SQLAlchemy로 변경 | 없음 |

psycopg2 전제로 쓰인 코드(= psycopg 3 비호환, 0.25.0~0.29.24 전부 존재):

| 위치 | 내용 | psycopg 3에서 |
|------|------|---------------|
| `event_log/event_log.py:200-204` | "LISTEN/NOTIFY no longer used for pg event watch - preserved here to support version skew" — `db.text("NOTIFY run_events, :notify_id; ")` | psycopg2는 client-side 치환(`NOTIFY run_events, '<run>_<id>'`)이라 동작. psycopg 3은 server-side bind(`$1`) → NOTIFY는 파라미터를 못 받아 SyntaxError. `store_event`마다 실행되므로 첫 이벤트(RUN_ENQUEUED/RUN_START)에서 run이 멈춘다 |
| `utils.py:162-166` `set_pg_statement_timeout` + `optimize_for_webserver`(`event_log.py:125`, `run_storage.py:119`, `schedule_storage.py:117`) | webserver engine의 `"connect"` 이벤트에서 DBAPI 연결에 `with conn: with conn.cursor() as curs: …` | psycopg2의 `with conn:`은 트랜잭션 범위(연결 유지). psycopg 3의 `Connection.__exit__`는 **연결을 닫는다** → pool이 닫힌 연결을 내줘 모든 webserver 질의 실패 |
| `utils.py:78-88` `retry_pg_creation_fn` | `exc.orig.pgcode != "42P07"` | psycopg 3 예외에는 `pgcode`가 없다(`sqlstate`만, 실측 `hasattr(psycopg.Error, "pgcode") == False`) → 빈 DB에 세 서비스가 동시에 테이블을 만들다 경합하면 원래 오류 대신 `AttributeError` |

따라서 psycopg 3은 dagster-postgres가 지원하지 않는 조합이고, 2.1로 가는 길은 "psycopg 3에서 검증"이
아니라 **드라이버를 psycopg2로 명시**하는 것뿐이다.

## 권고

### 1. manager `KOR_TRAVEL_GEO_DAGSTER_PG_URL` → `postgresql+psycopg2://…`

scheme만 바꾸고 user/password/host/port/db는 그대로 둔다. 예:
`postgresql+psycopg2://kor_travel_geo_app:<secret>@127.0.0.1:11000/kor_travel_geo_dagster`.
manager 저장소의 `.env.example`(153·465행)과 문서의 예시도 같은 표기로 맞춘다.

geo `dagster.yaml`은 바꾸지 않는다(`postgres_url: env: KTG_DAGSTER_PG_URL` 유지). structured
`postgres_db` + `scheme` 형식도 2.0/2.1 모두 통과하지만 manager가 URL 하나 대신 env 5개를 주도록 계약을
바꾸고 이미지와 env를 동시에 배포해야 한다(순서가 어긋나면 세 서비스가 config 오류로 못 뜬다). 얻는 것은
"드라이버 선택이 geo 저장소에 고정된다"뿐이라, 지금은 값 변경 한 줄보다 비용이 크다.

### 2. 운영 적용 안전성과 절차

- **현재 2.0.54 이미지에서는 동작 변화가 없다.** 2.0에서 `postgresql://`와 `postgresql+psycopg2://`는 같은
  dialect·같은 드라이버다(표의 `드라이버` 열, 전환 시나리오 1단계).
- DB 쪽 작업 없음: 스키마·alembic revision 불변, `dagster instance migrate` 불필요, 재build 불필요.
- env는 컨테이너 재생성 때만 반영되므로 **세 서비스 재생성**이 필요하다: `kor-travel-geo-dagster-code-server`,
  `kor-travel-geo-dagster`(webserver), `kor-travel-geo-dagster-daemon`. DefaultRunLauncher의 run은
  code-server 안의 자식 프로세스라 **진행 중 run이 없을 때** 한다.
- 절차는 `tasks.md` T-322 항목에 둔다(적용 → 검증 → 롤백).
- 롤백은 값을 되돌리고 같은 세 서비스를 재생성하면 된다(2.0에서는 두 값이 같은 드라이버라 롤백도 무위험).

### 3. `sqlalchemy<2.1` pin — 유지. 해제 조건

지금은 **유지**한다. 아래를 모두 만족한 뒤 별도 PR로만 푼다.

1. 운영과 이 이미지를 쓰는 모든 환경의 `KTG_DAGSTER_PG_URL`이 `postgresql+psycopg2://`(또는
   `postgres_db` + `scheme: postgresql+psycopg2`)로 배포·검증돼 있다(위 1·2).
2. **fail-fast guard**를 같은 PR에 넣는다. 2.1에서 bare/`+psycopg` URL은 healthcheck를 통과한 채
   run만 못 돌기 때문이다(위 결론 4). 예: code location import 시 `make_url(KTG_DAGSTER_PG_URL)`의
   드라이버가 `psycopg2`가 아니면 즉시 실패 → code-server 컨테이너가 healthcheck(`grpc-health-check`)에
   실패하고 재시작을 반복해 바로 드러나며, webserver·daemon은 `depends_on: service_healthy`로 뜨지 않는다.
   세 서비스는 같은 compose 변수에서 같은 값을 받으므로 code-server 한 곳의 검사로 충분하다(webserver·daemon은
   definitions를 import하지 않는다).
3. CI `dagster` job의 `assert v.startswith('2.0.')`를 2.1 기준으로 바꾸고 본체 pytest + Dagster 패키지
   테스트가 2.1 resolve에서 통과한다(이번 실측: Dagster 패키지 전부 통과, SQLite teardown 로그만 확인 필요).
4. psycopg2-binary가 계속 설치된다(dagster-postgres `Requires-Dist: psycopg2-binary` — 현재 충족).
5. 가능하면 이 문서의 end-to-end 조작(실 Postgres storage에서 run·NOTIFY·daemon tick·webserver GraphQL)을
   opt-in 통합 테스트로 옮긴다. 이번 검증은 dagster 1.13.24 / dagster-postgres 0.29.24 한 조합만 실행했다.

## 검증하지 못한 것

- 운영 이미지의 정확한 dagster/dagster-postgres 버전(n150 미접속). 이미지는 lock 없이 build 시점에 해석되므로
  2026-09-29에 재build하면 위 1.13.24/0.29.24가 된다. `psycopg2.connect(url)` 부재는 pin 범위 0.25.0~0.29.24 전체에서
  소스로 확인했지만, end-to-end 실행은 0.29.24만 했다.
- 실제 geo code location(backup/load/restore job)의 run은 돌리지 않았다 — storage 경로는 job 내용과 무관하고,
  code location은 import·단위 테스트까지만 확인했다.
- GDAL `[loaders]` extra 없이 설치했다(storage 경로와 무관).
- manager 쪽 변경과 운영 적용은 하지 않았다(범위 밖, manager 담당과 조율).

## 재현

throwaway 하네스(`job_def.py`, `dagster.yaml` 3종 — URL형은 bare/+psycopg2 공용, `check_storage.py`,
`run_case.sh`, `webserver_probe.sh`)로 셀당
`run_case.sh <venv> <bare|psycopg2|db|db_psycopg2> <db>`를 순차 실행했다(한 번에 무거운 프로세스 하나).
하네스·venv·컨테이너는 검증 뒤 삭제했다.
