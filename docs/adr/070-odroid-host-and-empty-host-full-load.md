# ADR-070: geo 스택을 odroid(192.168.1.13)에서 운영하고, 빈 호스트는 소스에서 serving DB에 직접 풀로드한다

- 상태: **accepted (2026-10-15, 소유자)** — accepted 게이트 3건을 소유자가 닫았다(아래 "실행 기록" 끝 "소유자 결정"):
  §14-8 = **dump 복원(D3-6 지름길 (a), 수동 `pg_restore`)으로 갈음**, D3의 serving DB 직접 풀로드는 **다음 재적재 때**로 미룸;
  §14-12 = **odroid 이전 확정**, D6의 0.95 GiB anon 플립 게이트 대신 **사후 메모리 관찰**; §14-21 = **(나) 소비자별 공개 키**
  (active: `kor-travel-map`·`pinvi-api`·`kor-travel-concierge`). D3·D6은 이 결정만큼 amendment(실행 기록)로 읽는다 — 본문은
  2026-10-13 설계 기록으로 남긴다. 나머지 §14-19·4·7·6은 실행된 그대로(§14-4 = `dagster-sub.`, §14-7 = 백업 off, §14-6 = odroid 현지 빌드).
  (옛 상태 줄: proposed — 게이트 3건 대기, n150 잔류면 `rejected`였다.)
- 날짜: 2026-10-13 (실행 기록·accepted 2026-10-15)
- 결정자: 사용자 요청(2026-10-13 설계 프로그램 Track 2 "geo·weather·transport를 odroid로 옮긴다"),
  claude 설계 + 적대 리뷰 3회(6명) + odroid 비root 실측(2026-10-13) 반영. 정본 설계는 저장소 밖
  (`track2-design-final.md`, 절 번호 `§n`은 그 문서)이며, 이 ADR은 geo 저장소가 지켜야 할 결정만 둔다.
- 관련: ADR-045(PostgreSQL·RustFS는 외부 인프라 — 이 저장소는 DB를 구동하지 않는다)·ADR-048(API/UI 포트
  12501/12505)·ADR-064(공개 API 키)·ADR-066(Dagster 오케스트레이션)·ADR-067(데이터셋 버전 API)·
  **ADR-069(Track 1, `data_token` — 먼저 머지됨; 본 ADR과의 상호작용은 D8)**. 교차 저장소(모두 proposed,
  2026-10-13): Manager **ADR-58**(호스트 프로필 Manager·`hosts:`·odroid PG 인스턴스·이미지 변수·odroid
  초기화 절차 — 호스트 쪽 정본), Map **ADR-110**(Map→geo REST·connect timeout·`GEO_HEAVY_POOL` 근거),
  concierge **ADR-50**(concierge→geo URL·키 DB 우선), transport **ADR-014**. weather는 자체 ADR 없음.
- 옛 문서와의 관계: `docs/t055-deployment-n150-odroid.md`(x86 가정 → 본 ADR로 정정), `docs/t108-deploy-automation.md`
  (멀티아치 레지스트리 → 보류), 백로그 T-063(실측 보류 → T-326a로 승계).

## 컨텍스트

**호스트.** 운영 geo 스택(api 12501·ui 12505·Dagster code-server 12503)은 n150(192.168.1.14)의
`kor-travel-docker-manager` compose 안에서 돌고, PostgreSQL은 같은 호스트의 공용 제어 평면 instance
`kor-travel-shared-postgres` 11000(`docs/ports.md:27`, `.env.prod.example:53-57`)이다. Map·concierge·PinVi도 같은
호스트라 소비자 호출은 loopback이고, HAProxy(OPNsense, 저장소 밖)만 LAN peer로 들어온다(설계 §4.4). 소유자 지시로
geo·weather·transport 세 서비스와 **그들의 PostgreSQL**을 odroid(192.168.1.13)로 옮기고, n150에 남는
Map/PinVi/concierge는 REST로만 호출한다.
포트·URL·컨테이너명·compose 프로젝트명·디렉터리 규칙은 n150과 **동일**, 호스트만 `.14 → .13`.
데이터 보존·롤백은 비범위 — DB는 소스에서 재적재한다(소유자 지시 "다시 로드").

**옛 가정의 정정(실측).** 2026-10-13 odroid 비root 읽기 전용 실측(설계 fact base §A2 — 저장소 밖 수치)으로:

| 항목 | 이 저장소의 옛 서술 | 실측 |
|---|---|---|
| CPU/arch | Odroid = "H4 Plus 가정, Intel N97/N305 x86"(`docs/t055-deployment-n150-odroid.md:52-57`, CPU 행 `:54`) | **ODROID M1S, aarch64 Cortex-A55 ×4, max 1.8 GHz** |
| RAM / swap | "8~32 GB"(`t055:55`), "8GB라면 shared_buffers 축소"(`t055:328`) | **7,676 MiB(7.5 GiB), swap 0** |
| 디스크 | "NVMe 또는 SATA"(`t055:56`) | eMMC 58 GB = `/` + `/var/lib/docker`(33 G free); NVMe 938 GB ext4 통째 `/mnt/media`(Plex 라이브러리 336 G, 555 G free), 링크 PCIe 2.0 ×1 |
| OS/Docker | "Ubuntu 26.04 또는 Debian 12"(`t055:57`) | noble userland + PID1 systemd 245(focal) + kernel 5.10.198; Docker 29.1.3; **`docker compose` v2·buildx 없음**; cgroup v1(memory on, swap accounting on) |
| 배포 | `linux/arm64` 멀티아치 이미지를 레지스트리로(`docs/t108-deploy-automation.md:33-35,91-101`) | 레지스트리 없음, n150에 binfmt 없음 → odroid 현지 빌드(D7) |

같은 날 03:4xZ 소유자 승인 처리(fact base §A3)로 **완료된 것**: WSL에서 직접 `ssh digitie@192.168.1.13`
(WSL Docker 잔재 네트워크 제거), `/etc/sudoers.d/digitie` NOPASSWD(`sudo -n` 동작), `usermod -aG docker digitie`,
`timedatectl set-ntp true` + timesyncd 재시작으로 시계 2026-10-13 03:38Z 동기(RTC 갱신). **미완인 것**:
timesyncd 부팅 순서 사이클(`webvnc-router-timesyncd-config.service`)의 drop-in 영속화(재부팅 뒤 재발 가능),
`docker compose` v2/buildx 설치, 호스트 방화벽, fstab bind 마운트(NVMe 디렉터리 트리), swapfile. 이들은
Manager ADR-58·`prod-deployment.md`의 odroid 초기화 절(그 문서 §9.1 — 설계 §11.1에 해당) 몫이며 이 저장소는 그 결과를
전제로만 둔다.

**n150 실측(geo, 저장소 안 기록).** `mv_refresh` 1.22~1.59 h, `db_backup` 0.64~0.72 h, `db_restore` 2.18 h
(`load_jobs` 2026-07-09~ 이력 — 공용 이전(2026-09-28) **전** 전용 12500 인스턴스(superuser) 시절 값; 공용 인스턴스의
NOCREATEDB 롤에서는 `db_restore`가 거절된다, 컨텍스트 5·D3-6), **serving DB에 full load를 적재한 적은 없고** 개발 WS
전국 full load 4 h 08 m(SHP 3 h 37 m) — `docs/journal.md` 2026-09-30 항목, `kor-travel-geo-dagster/src/kortravelgeo_dagster/run_tags.py`
docstring. 단 n150 하드웨어에서 전국 `full_load_batch`가 돈 적은 있다: 2026-07-12 T-290l 격리 scratch DB e2e(7 로더 직렬 →
`tl_juso_text` 6,416,637 → MV 둘 다 6,416,637, journal 2026-07-12 항목 `docs/journal.md:1608-1630`) — wall clock은 journal에
없고 `load_jobs`/run store에서 회수 가능하면 T-326a가 n150 분모로 쓴다. 백업 artifact는 4,706,711,752 B
(≈4.4 GiB, journal 2026-08-18). 공용 PG의 `kor_travel_geo`는 34 GB, 버퍼 적중 48.3 %, temp 13 GB(설계 fact base
§B2 — 저장소 밖 수치); MV shadow swap temp +11.67 GiB(`t055:112`). **전국 원천 ZIP은 n150에도 없다**(설계
fact base §E1; 런북 전제 `docs/deploy/staging-full-load.md:31-33`는 운영자가 배치한다고만 적는다).

**이 저장소에서 확인한 제약(2026-10-13 head `6dd4951` 기준).**

1. **공개 API 키의 "신뢰 peer 면제"는 peer IP만으로 성립하지 않는다.** `require_public_api_key`는
   `_trusted_public_client`가 참이면 키 검사 없이 통과하는데(`src/kortravelgeo/api/public_api_key.py:55-56`),
   그 판정은 `resolve_request_context`(`:70-71`)이고 이것은 peer가 `KTG_ADMIN_TRUSTED_PROXY_CIDRS`(또는
   `KTG_GEOIP_TRUSTED_PROXIES`) 안에 있고(`src/kortravelgeo/api/security.py:127-133`), `KTG_ADMIN_PROXY_SECRET`이
   설정돼 있으면 그 헤더가 맞고(`:144-151`, 호출 `:161-164`), `x-ktg-actor`와 인식되는 role이 있어야(`:165-170`) 참이다.
   즉 면제는 admin 프록시 경로의 것이고, 전환 뒤 peer가 `192.168.1.14`가 되면 CIDR 조건에서부터 거짓이다. 그러면 키가
   대조된다: 유효 집합 = DB `public_api_keys` 활성 해시, 비어 있으면 `KTG_VWORLD_API_KEY` 해시 하나
   (`public_api_key.py:62-67,144-150`). DB에 키가 **하나라도** 있으면 VWorld 폴백은 꺼진다(all-or-nothing); 반대로
   `KTG_VWORLD_API_KEY`가 비어 있고 DB도 비면 유효 집합이 공집합이라 **모든** 키가 거부된다(`:144-150` strip → `:66-67`).
   **오늘 상태는 저장소 안 기록으로 닫힌다 — 면제가 아니라 키 경로이고, 발급 키다.** (ⅰ) Map 클라이언트는 `x-ktg-actor`/`x-ktg-roles`를
   보내지 않는다(Map `src/kortravelmap/` grep 0건; 키 거부 400 `field == "key"`/401 `E0401`은 `GeoAuthNotConfiguredError`로
   처리, Map `src/kortravelmap/geocoding.py:92-96,103-107`) → CIDR과 무관하게 **오늘도 키 경로**. (ⅱ) 2026-08-08
   `kor-travel-map`용 공개 API 키를 DB에 발급했고(그전 8건 전부 revoked라 env 폴백 하나로 24h 26만 건이 인증되던 상태 →
   "첫 DB 키 발급 = env 폴백 컷오버"), 08-17 24h 401 0건·public 2xx 238건으로 소비자 전환 완료(`docs/journal.md:1540-1543`).
   즉 **n150 `public_api_keys`에는 활성 발급 키 ≥1(Map 몫)이 있고 VWorld 폴백은 꺼져 있으며, Map의
   `KOR_TRAVEL_MAP_KOR_TRAVEL_GEO_API_KEY`는 발급 키로 loopback에서 이미 대조·검증돼 왔다**(Map ADR-110 컨텍스트 4도 같은 결론 —
   2026-08-13 prod 사고: VWorld 키가 결선돼 geo가 401). concierge의 actor 헤더 유무·키 값은 미확인(concierge ADR-50 몫).
   설계 §9.1 키 행의 "유효성 검증된 적 없음"·§5.6 ⑥의 "loopback 면제로 통과" 전제는 틀렸다(설계 쪽 정정 전달, 후속).
2. **풀로드 라우팅에 env 게이트가 없다.** T-290k PR3 이후 모든 실행 종류가 무조건 Dagster로 간다 —
   "`dagster_executed_job_kinds` opt-in gate … are gone"(`src/kortravelgeo/api/_full_load_launch.py:9-11`).
   런북의 `KOR_TRAVEL_GEO_DAGSTER_EXECUTED_JOB_KINDS=…,full_load_batch`(`staging-full-load.md:43`, `:78`의 "제거 여부"
   주석)는 stale이다(이번 PR에서 정정).
3. **소스 볼륨은 추가 overlay이고, 컨테이너 경로 계약은 `/app/data/source`다.** `docs/deploy/docker-compose.geo-source-vol.yml`을
   Manager 배포에 추가 `-f`로 얹어야 api·dagster 컨테이너가 `/app/data/source`를 본다(`staging-full-load.md:34-36`; bind 문자열은
   `${KOR_TRAVEL_GEO_SOURCE_DIR:-/home/digitie/kor-travel-geo-data/source}:/app/data/source:ro`,
   `docker-compose.geo-source-vol.yml:30`). `full_load_batch` payload의 파일 경로도 전부 `/app/data/source/...` 절대경로다
   (`staging-full-load.md:51-58`). Manager의 "compose 하나" 규칙과 충돌한다.
4. **run 상한.** 공용 plane의 `run_monitoring.max_runtime_seconds`는 6 h이고 geo는 `LONG_JOBS = {full_load_batch,
   load_source, db_restore, backup_restore_drill}`만 `dagster/max_runtime=86400`(24 h)을 단다
   (`kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py:15,24`, `run_tags.py`). `mv_refresh`는 21600이고
   그 기대값은 `kor-travel-geo-dagster/tests/test_definitions.py:76-88`에 고정돼 있다(`"mv_refresh": "21600"` `:86`).
5. **백업·drill·janitor는 손잡이가 셋이고 서로 독립이다.** (ⅰ) `scheduled_backup` 스케줄은 코드에서 RUNNING 기본이나
   실제로 백업을 enqueue할지는 API의 `KTG_BACKUP_SCHEDULE_ENABLED`(기본 `false`, `src/kortravelgeo/settings.py:227`)가
   정한다(`kor-travel-geo-dagster/src/kortravelgeo_dagster/backup.py:121` 주석). (ⅱ) restore drill 스케줄
   `backup_restore_drill_daily`(cron `0 4 * * *`, `backup_maintenance.py:74-75`)는 **STOPPED 기본·배포별 수동 enable**
   (`:330-336` "STOPPED by default; enable per deployment")이고 백업 스케줄과 **연동되지 않으며**, DB role이 CREATE DATABASE를
   못 하면 tick을 skip한다(T-321, `:339-344`; journal 2026-08-18 "drill은 STOPPED 유지"). drill 1회는 전체 restore(n150 2.18 h)와
   같다. (ⅲ) janitor(06:00, `:79`)는 RUNNING 기본(`:368`)이나 백업 artifact가 없으면 지울 것이 없다.
   설계 §3.3·§5.7의 "백업 스케줄을 켜면 drill이 따라온다"는 head와 다르다 — 정정 대상은 **설계 문서 그 두 절만**(저장소 밖);
   Manager ADR-58 결정 (8)(ⅶ)는 이미 "geo 백업·restore drill은 odroid에서 off"로 둘을 독립 서술하므로 고칠 문구가 없다.
6. **이미지의 네이티브 의존.** API 이미지는 `python:3.12-trixie`에 `gdal-bin libgdal-dev`를 apt로 얹고
   (`docker/api.Dockerfile:1,13-19`), Dagster 이미지도 같은 방식으로 `gdal==$(gdal-config --version)` 바인딩을
   빌드한다(`kor-travel-geo-dagster/docker/dagster.Dockerfile:10-12,45-49`; base는 digest 핀 `:34`이고
   `kor-travel-geo-dagster/tests/test_image_constraints.py:96-102`가 두 FROM이 같은 `python:3.12-slim@sha256:…` 형식임을
   단언한다). arm64에서는 둘 다 소스 컴파일이다. 이미지 태그 규칙은 Manager 것(내용 해시, arch 없음).
7. **데이터셋 버전 API도 공개 키 경로다.** `POST /v2/dataset/version`은 v2 공통 public-key auth
   (`src/kortravelgeo/api/routers/dataset.py:3-4`) — Track 1(ADR-069) 소비자 센서의 ≤5분 폴링이 전환 뒤 LAN·
   키 경로로 간다.

## 결정

**geo 스택은 odroid에서 n150과 같은 포트·이름으로 돌며(호스트만 `.13`), 빈 odroid의 `kor_travel_geo`는
원천 ZIP에서 serving DB에 직접 풀로드한다. 공개 키는 오늘도 발급 키로 대조되고 있고 빈 DB로 플립하면 그 키가
무효가 되므로 정책을 전환 전에 고정하고(소비자별 발급 추천), 풀로드 재적재마다 다시 발급한다. 레지스트리는 두지 않고 odroid에서 현지 빌드한다(설계 §14-6 추천안, 소유자 승인 대기).**

교차 저장소 인용 규칙: `§n`은 저장소 밖 설계 최종본의 절이고, Manager ADR-58은 절 번호가 없는 결정 (1)~(13) 목록이라
"설계 §x(Manager ADR-58 결정 (n))"으로 쓴다.

### D1 — 호스트만 바뀐다

- api `12501`·ui `12505`·code-server `127.0.0.1:12503`, 컨테이너명·compose 프로젝트명·이미지 태그 규칙은 n150과
  동일(ADR-048 불변). `KTG_PG_DSN`은 odroid **전용** PG 인스턴스(이름·포트도 같은 `kor-travel-shared-postgres`
  11000, loopback scram, arm64 이미지 `imresamu/postgis:16-3.5` — 설계 §5, Manager ADR-58 결정 (3)·(8))를 가리키는
  loopback DSN으로 **문자열 불변**(`.env.prod.example:57` 모양 그대로). RustFS `127.0.0.1:12101`, Dagster code-server·plane도
  odroid 안 loopback(odroid 자체 plane, 설계 §6, Manager ADR-58 결정 (3)). 이 저장소에서 바뀌는 운영 값은 없다 — 값의 자리는
  Manager compose·root `.env`다(ADR-045 원칙). `docs/ports.md:27`의 PG 행은 지금도 맞고(n150 공용 instance), odroid 이전 뒤의
  모습은 그 행 비고에 "계획" 한 줄로만 둔다(이번 PR).
- `KTG_ADMIN_TRUSTED_PROXY_CIDRS`는 **loopback 유지**(`.env.prod.example:35` placeholder 불변): admin 호출자(geo-ui
  BFF·code-server)는 odroid 로컬이고, 공개 키 발급(ADR-064)도 odroid 로컬 admin API에서만 한다. `.14`를 CIDR에
  **넣지 않는다** — 넣으면 컨텍스트 1의 면제가 Map/concierge에도 열려 키 정책이 무의미해진다.
- `KTG_DAGSTER_PUBLIC_URL`(`.env.prod.example:47`)은 odroid plane의 공개 host(이름은 소유자 §14-4 — `weather-dagster.`/
  `geo-dagster.` 중 재사용 또는 새 이름, 설계 §4.4·§14-4; `docs/ports.md:34`의 `geo-dagster.digitie.mywire.org`는 독립 plane 시절
  도메인)이고 `KTG_DAGSTER_URL`은 odroid plane webserver loopback(Manager compose 주입;
  `.env.prod.example:43`의 `12502`는 standalone 스택 값이다 — geo의 공용 plane 전환 자체는 이 저장소에도 기록이 있으나
  (T-324 `docs/tasks.md:57`, `kor-travel-geo-dagster/src/kortravelgeo_dagster/run_tags.py:1-6` docstring, journal 2026-09-30)
  plane webserver 포트·Manager PR(#449)은 Manager 쪽 사실이라 여기 없고, `.env.prod.example:43`·`docs/ports.md:34`는 갱신되지
  않았다. 둘 다 T-326b에서 "Manager compose 주입" 주석으로 함께 정정).
- 소비자는 REST만 쓴다: Map `KOR_TRAVEL_MAP_DOCKER_GEO_BASE_URL`(Manager compose 기본값 → `http://192.168.1.13:12501`,
  Map ADR-110), concierge `KOR_TRAVEL_GEO_V2_BASE_URL`(concierge ADR-50). geo는 소비자를 모른다(의존 방향 불변).

### D2 — 공개 키 정책을 전환 전에 고정하고, 재적재 뒤 다시 적용한다

- 오늘(컨텍스트 1): n150 DB에 Map용 발급 키 ≥1, VWorld 폴백 **off**, Map은 발급 키로 키 경로. 전환 뒤에도 키 경로다 —
  바뀌는 것은 "어느 DB의 `public_api_keys`가 대조하는가"뿐이고, **빈 odroid DB(풀로드)로 플립하면 Map의 현재 발급 키는
  401이 된다**(폴백이 되살아나도 Map은 VWorld 키를 보내지 않는다). 정책은 둘 중 하나(소유자 §14-21) — 설계 §14-21의
  "(가) 추천, 변경 0"은 **철회**하고 (나)를 추천한다:
  - **(가) VWorld 공용 키 폴백으로 복귀** — DB `public_api_keys`를 비워 두고 소비자가 `KTG_VWORLD_API_KEY`와 같은 키를
    보내게 한다. 변경 0이 아니다: Map root `.env` `KOR_TRAVEL_MAP_KOR_TRAVEL_GEO_API_KEY`를 VWorld 키로 **되돌려야** 하는데
    Map은 T-VN-H46B/C(#979)로 VWorld 키가 geo 소비자 키로 흐르는 통로를 끊고 가드(테스트)를 세웠고 08-13 사고가 바로 그
    구성이었다 — Map ADR-110 결정 §4는 (가)를 **Map 쪽에서 채택 불가**로 둔다. 전제도 하나 더 있다: odroid root `.env`의
    `KOR_TRAVEL_GEO_VWORLD_API_KEY`가 비어 있지 않아야 한다(Manager compose `KTG_VWORLD_API_KEY: ${KOR_TRAVEL_GEO_VWORLD_API_KEY:-}`,
    ktdm-t2docs 체크아웃 `docker-compose.yml:1100,1163` 기본값 빈 문자열 → `public_api_key.py:144-150` 빈 집합 → `:66-67`
    전부 거부; 메모리 `empty-env-defeats-none-guards`와 같은 모양). **함정**: DB에 키가 하나라도 발급되면 폴백이 꺼진다(`:65`).
  - **(나) 소비자별 발급(추천)** — odroid 로컬 admin API에서만 발급 가능(D1 CIDR); Map root `.env`
    `KOR_TRAVEL_MAP_KOR_TRAVEL_GEO_API_KEY` 갱신 + n150 `ensure map`으로 Map 컨테이너 **전부** 재생성(08-13 사고는 api만
    재생성해 dagster/daemon이 옛 키를 들었다 — Map ADR-110 결정 §4(a)); concierge는 `system_settings['kor_travel_geo_v2_api_key']`
    (DB 우선 — env만 갱신하면 효과 없음, concierge ADR-50)를 갱신. 발급 시각은 풀로드 완료 뒤·URL 전환 **전**(9단계 필수 항목).
- **풀로드(D3 기본)·장애 뒤 drop → 재적재 뒤 `public_api_keys`는 비어 있다** → (나)면 재발급 + 소비자 갱신 + 키 경로 200
  확인이 필수. 반면 **dump 복원(D3-6 지름길)은 키를 보존한다** — `db_backup`의 pg_dump는 `ops` 스키마를 제외하지 않으므로
  (`src/kortravelgeo/infra/backup.py:1175-1206` — 제외는 `lean-serving`의 `geo_cache`와 MV data뿐) `ops.public_api_keys`가
  그대로 살아 Map의 현재 키가 유효하다. Map은 `kor_travel_geo_preflight_required`가 켜져 있으면 키 거부 시 API 기동 자체가
  막힌다(Map ADR-110) — 재적재 창에 Map 재시작을 겹치지 않는다.
- **전환 전 기록 1회(T-326a (2), 소유자 §14-21 입력)** — 목적은 "면제 여부 확인"이 아니라(그것은 코드·journal로 닫혔다,
  컨텍스트 1) **현재 값 기록**이다: n150 DB `SELECT count(*) FROM ops.public_api_keys WHERE state = 'active'`(기대 ≥1)와, n150에서
  `curl --interface 192.168.1.14 'http://192.168.1.14:12501/v2/reverse?…&key=<Map .env KOR_TRAVEL_MAP_KOR_TRAVEL_GEO_API_KEY>'`의
  200/401(= **Map `.env` 키가 오늘 DB에 대해 유효한가**; curl은 actor 헤더가 없어 항상 키 경로이므로 면제 여부를 측정할 수
  없다). 대상은 전환 **전**이므로 `.14`(전환 뒤 smoke는 `.13`, 런북 6단계).

### D3 — 빈 호스트 초기 적재는 소스에서 serving DB로 직접

1. **소스 재확보**: 전국 원천(JUSO 한글 전체분 + LOCSUM + NAVI + SHP 9 레이어 + pobox, 그 밖에 선택 원천)
   ZIP을 `/home/digitie/kor-travel-geo-data/source`(n150과 같은 경로; odroid에서는 fstab bind로 NVMe
   `/mnt/media/kor-travel/geo-data/source`가 실체 — 설계 §5.1, Manager ADR-58 결정 (4) 파생 규칙 R5, 미완)에 둔다. **용량·재확보 가능
   여부 미확인**(소유자 §14-8).
2. **소스 bind는 상시, 컨테이너 경로는 `/app/data/source`가 계약**: 추가 overlay(컨텍스트 3) 대신 Manager compose의 geo
   api/code-server volumes에 overlay와 **같은 bind 문자열**
   `${KOR_TRAVEL_GEO_SOURCE_DIR:-/home/digitie/kor-travel-geo-data/source}:/app/data/source:ro`를 **기본 경로로 상시** 넣는다
   (Manager T-MGR-01d; compose는 "변수가 비면 bind 없음"을 표현할 수 없다). **주의 — 교차 저장소 오기**: 설계 §5.6 ②와 Manager
   `docs/tasks.md` T-MGR-01d는 컨테이너 쪽을 `:/source:ro`로 적었다. geo의 payload 절대경로(`staging-full-load.md:51-58`)와
   overlay(`docker-compose.geo-source-vol.yml:30`)는 전부 `/app/data/source`이므로 `/source`로 구현하면 odroid 풀로드의 모든 파일
   open이 실패한다 — Manager PR은 `/app/data/source:ro`로 써야 하며, 이 불일치는 Manager PR 리뷰어에게 전달한다(한 줄 수정).
   n150에 디렉터리가 없으면 Docker가 빈 디렉터리를 만든다 — 무해. 풀로드 제출 전 프리플라이트는 **소스 파일
   수 > 0**(`find $SRC -type f | wc -l`)을 효과로 거부한다(런북 1단계 수동 프리플라이트 — 설계 §11.2 8b; Manager `ensure`
   프리플라이트 T-MGR-05는 이미지 arch·bind 소스 장치·compose 렌더만 본다, `ktdm-t2docs/docs/tasks.md:16`). overlay 파일은
   그 뒤 삭제 후보(이번 PR에서는 유지) — 단 overlay는 소스 bind 외에 named volume `geo-materialize:/app/data/rustfs/materialized`를
   api·dagster·daemon에 공유시킨다(`docker-compose.geo-source-vol.yml:16-18,31,34,37` — `source_rebuild_db`의 RustFS materialize를
   Dagster op가 보게 함). Manager compose에는 그 볼륨이 없으므로 삭제 조건은 "Manager compose에 `geo-materialize` 공유 볼륨이
   들어간 뒤 **또는** `source_rebuild_db` 경로 불사용 결정 뒤"다(파일 구동 풀로드에는 영향 없음; Manager 전달 목록에 추가).
3. **라우팅 설정 없음**: 풀로드는 head에서 무조건 Dagster로 간다(컨텍스트 2). `EXECUTED_JOB_KINDS`는 쓰지 않는다.
4. **serving DB 직접**: `payload.target_database`를 **주지 않는다** — 빈 호스트에는 보호할 serving MV가 없다.
   런북의 scratch DB·컷오버 절차는 "운영 중 재적재" 전용으로 남긴다(`docs/deploy/staging-full-load.md` 새 절).
   run 상한은 `full_load_batch` 24 h(컨텍스트 4) — A55 ×3 가정(12 h+)도 안에 든다.
5. **`full_load_batch` 한 run이 끝까지 간다**: 소스 로더 직렬 → `consistency_check` child → ERROR 게이트 → `mv_refresh` child
   (ADR-017 순서 그대로 — `src/kortravelgeo/loaders/batch_dag.py:3-4,22`; mv swap은 게이트 **뒤**다). 별도 standalone `mv_refresh`
   단계는 없다 — batch 안 child의 소요는 batch run의 24 h 상한 아래서 돈다. batch SUCCESS → D2 키 정책 적용(발급) → smoke
   (`/v2/reverse` 키 경로 200, `/v2/dataset/version`). D4 입력은 batch child가 아니라 **standalone `mv_refresh` 1회**
   (야간 schedule 또는 `POST /v1/admin/maintenance/refresh-mv`, `routers/admin.py:1867`)의 wall clock이다.
6. **지름길(소유자 §14-8)**: n150 geo `db_backup` dump(≈4.4 GiB)를 odroid에 반입해 복원. "보존"이 아니라 적재 수단이며,
   소유자 지시 "다시 로드"에 따라 **기본은 풀로드**. D8의 Track 1 비용과 D2의 키 보존이 둘을 가른다. **전제(실행 가능 조건)**:
   Dagster `db_restore`는 `CREATE DATABASE`/`ALTER DATABASE RENAME`(= CREATEDB) + maintenance DB `postgres` CONNECT를 요구하고,
   없으면 job 생성 전에 `UnsupportedOnInstanceError`(E0410/409)로 거절된다(`src/kortravelgeo/infra/db_capabilities.py:3-11`;
   API `routers/admin.py:2299-2310`, op `infra/backup.py:483-489`). odroid 롤은 n150과 같은 `kor_travel_geo_app`
   (NOSUPERUSER/NOCREATEDB, `.env.prod.example:54`; 설계 §5.4; Manager `shared-postgres-onboarding.md:228`)이므로 **기본 요청은
   E0410**이다 — 2.18 h는 전용 12500 시절 값(컨텍스트). `target_dsn`을 줘도 우회가 아니다: 대상이 현재 DB와 **달라야** 하고 비어
   있어야 해서(`infra/backup.py:570-573`) serving `kor_travel_geo`에는 복원할 수 없다. 따라서 지름길을 고르면 §14-8 답에 둘 중
   하나가 포함돼야 한다: **(a) Dagster 밖 수동 복원** — odroid에서 `shared_admin`으로 `pg_restore`(role-neutral, 런북 별도 절;
   추천 — 롤 설계 불변), 또는 (b) Manager db-init에서 geo 롤에 CREATEDB + `postgres` CONNECT 부여(ADR-58 결정 (3)/(8) amendment,
   Manager 전달) → `db_restore`(새 DB) + 수동 hot-swap(`/restores/hot-swap`, `routers/admin.py:2361,2422` — `db_restore`에
   포함되지 않는 별도 단계). 어느 쪽이든 복원 뒤 `ops.public_api_keys`는 살아 있다(D2).

### D4 — run 상한: `mv_refresh`만 결정이 남는다

- `full_load_batch`·`load_source`·`db_restore`는 24 h(컨텍스트 4) — 풀로드·복원에 충분, 변경 없음.
- `mv_refresh`는 21600(6 h). n150 1.22~1.59 h × A55 ×3 가정 = **3.7~4.8 h = 상한의 61~80 %** — 여유가 없다
  (설계 §3.3의 "4~5 h = 70~85 %"는 같은 입력의 반올림 표기이고 Manager ADR-58은 그 값을 싣는다; 본 ADR은 ×3 산수값을
  쓴다 — 결론은 같다). 결정은 **odroid 실측 뒤**(T-326b; 입력은 standalone `mv_refresh` 1회의 wall clock — D3-5): (ⅰ) `LONG_JOBS`에
  `mv_refresh` 추가(24 h, `recovery.py:15`) 또는 (ⅱ) 실측 ×1.5를 **`policy_for_job`의 job별 초 매핑**으로(예
  `MAX_RUNTIME_OVERRIDES = {"mv_refresh": N}` → `RecoveryPolicy(max_runtime_seconds=…)`, `recovery.py:21-27`). (ⅱ)를 job 태그
  인자로 넣으면 **안 된다**: `geo_job`은 `tags={**(tags or {}), **policy_for_job(name).tags(...)}`로 policy 태그를 **뒤에** 병합하므로
  (`recovery.py:30-37`, `:34`) `MV_REFRESH_JOB_TAGS`식 상수는 policy의 21600에 덮인다 — 두 선택지의 구현 자리는 비대칭이다
  (`RecoveryPolicy.tags`가 `dagster/max_runtime`을 내는지는 kortravelcommon 소스가 로컬에 없어 `test_definitions.py:76-88`
  기대값으로 추정 — 구현 전 1회 확인). 어느 쪽이든 `kor-travel-geo-dagster/tests/test_definitions.py:76-88`의 기대값을
  함께 바꾼다(테스트가 선택을 강제한다). 공용 `dagster.yaml`은 바꾸지 않는다(설계 §6.4, Manager ADR-58 결정 (7)).
- 수용 기준(효과로 결박 — "소요 < 상한의 70 %"는 (ⅱ)에서 정의상 참(66.7 %)이라 쓰지 않는다): 풀로드 run이 cancel 없이
  SUCCESS; (ⅱ)면 태그 값 == `round(실측 s × 1.5)`이고 `test_definitions.py` 기대값이 그 숫자와 같으며 한 줄 바꾸면 빨갛다;
  (ⅰ)은 실측(또는 ×3 산식 근거)이 21600 s를 **넘었을 때만** 고르고 그 숫자를 journal에 적는다 — 넘지 않으면 (ⅰ)을 고르지 않는다.

### D5 — odroid에서 geo 백업·restore drill은 off(켜지 않는다)

세 손잡이(컨텍스트 5)를 odroid에서 이렇게 둔다: (ⅰ) **`KTG_BACKUP_SCHEDULE_ENABLED=false` 유지**(기본값,
`settings.py:227`; Manager root `.env`에서 켜지 않는다) — `scheduled_backup` tick은 RUNNING이어도 no-op; (ⅱ) **drill 스케줄
`backup_restore_drill_daily`는 STOPPED 유지**(코드 기본, `backup_maintenance.py:330-336`) — 켜면 매일 04:00 전체 restore(A55
가정 6~7 h, +34 GB)가 돌고 odroid 7.5 GiB·4코어에서 야간 `mv_refresh`·weather·transport와 겹친다; odroid 롤도 NOCREATEDB
(설계 §5.4, D3-6)라 drill tick skip(T-321)·`db_restore` 거절(E0410) 둘 다 **기본**이고, 켜도 돌지 않는다; (ⅲ) janitor는 그대로(RUNNING 기본, 백업 artifact 0이면 0건 — 무해). 수동
`POST /v1/admin/backups`는 남는다(재적재 원칙과 일치). 이 결정은 설계 §5.7(Manager ADR-58 결정 (8)(ⅶ) — 백업 대상 =
transport 3일만)과 소유자 §14-7의 geo 몫이다. 설계 §3.3·§5.7의 "백업을 켜면 drill이 따라온다"는 head와 다르다(컨텍스트 5) —
결정(off)은 같고 서술만 설계 문서에 정정 전달(ADR-58 (8)(ⅶ)는 이미 독립 off 서술).

### D6 — 메모리 조건(플립 게이트)

메모리 예산·산식·구성 요소 수치는 설계 §3.2(Manager ADR-58 결정 (8), proposed)가 정본이고 여기에 복제하지 않는다. geo가
지켜야 할 것만: **code-server `mem_limit 2g` + `memswap_limit 2g`**(swap 0 → limit 도달 = OOM = run FAILURE; odroid는
cgroup v1 swap accounting on이라 memswap 없으면 Docker 기본 swap 2×가 실제로 적용된다), api+ui `0.4g`. **geo를 odroid로
옮기는 조건(플립 게이트)**: n150 실측(§11.1-0)에서 geo code-server의 무거운 run(`mv_refresh`·`db_backup`) 중 cgroup
anon ≤ **0.95 GiB**(설계 §3.2 조건 (3): RAM 7.5 − 여유 0.2 − geo 뺀 최악 창; 여유 0이면 1.15 — 여유 값은 소유자 §14-12).
종전 설계의 "≤1.2"는 근거 없는 값이었고 그 값으로도 최악 창이 RAM을 넘는다(3차 리뷰 E-10). 미달이면 **geo는 n150 잔류**
(혼합 배치 — Manager 모델이 그대로 수용). n150의 geo cs 피크 4,783 MiB는 dump 쓰기 page cache일 개연성(가정)이라 anon
실측이 선행한다. 측정 방법은 T-326a (2)(n150은 cgroup v2 — `memory.stat`의 `anon` 키, run 중 10 s 간격 샘플 최대값).
PG cgroup anon도 같은 창에 찍지만 그것은 이 게이트가 아니라 Manager 쪽 PG 가드 vs 하드 캡 결정(§14-14)의 입력이다.
대안: cs `mem_limit 1.5g`(memswap 정책이 있어야 "swap 대신 FAILURE"가 성립).

### D7 — GDAL·이미지는 odroid 현지 빌드, 레지스트리 없음(설계 §14-6 추천안, 소유자 승인 대기)

- arm64는 실측 확정이므로 API·Dagster 이미지의 GDAL 바인딩 소스 컴파일(컨텍스트 6)은 odroid에서 1회 빌드
  (가정 30~60분, 메모리 ≈2 GB)로 받는다. 검증은 효과로: `from osgeo import gdal`, `gdal.__version__ ==
  gdal-config --version`, `docker image inspect --format '{{.Os}}/{{.Architecture}}'` == `linux/arm64`,
  `pip check`(Dagster 이미지의 exact constraints `kor-travel-geo-dagster/docker/constraints-dagster.txt`가 aarch64 wheel을
  다 갖는지 — 없으면 빌드가 실패해 드러난다).
- `docs/t108-deploy-automation.md`의 ghcr 멀티아치 build/push·`deploy_app.py` 노드 배포는 **보류**: 레지스트리를
  도입하면 Manager의 내용 해시 태그에 arch가 없어 같은 태그가 두 arch 내용을 가리킨다 — 레지스트리 도입의 선결
  조건(설계 §8.4, Manager ADR-58 결정 (9)). n150 buildx+QEMU도 채택하지 않는다(binfmt 없음, 속도). 레지스트리 재검토
  조건: 호스트 셋 이상. 소유자가 §14-6에서 레지스트리를 고르면 이 항목과 t108 보류 블록을 되돌린다.
- Dagster base digest(`dagster.Dockerfile:34`)는 Dockerfile 주석이 **index digest**라고 적는다 — "the multi-arch index
  `python:3.12-slim` resolved to on 2026-09-29"(`dagster.Dockerfile:31-32`; 설계 §8.2의 weather `Dockerfile.python:6`도 같은
  `f77a…`). T-326a (3)에서 `docker buildx imagetools inspect python:3.12-slim@sha256:f77ac9e…`로 **arm64 manifest가 있음을 1회
  확인**하면(기대 결과) 아래 재핀·태그 완화 논의는 전부 해당 없음이고 odroid 빌드는 digest 그대로 간다. 아래는 **주석과 달리
  amd64 manifest로 나올 때만**(odroid pull이 실패해 드러난다) — 그 경우 **설계 §8.2("amd64면 태그로 완화")·§8.4("기존 digest
  핀은 제거하지 않고 odroid는 root `.env`/태그 완화")와 달리** 이 저장소는 **index digest(또는 arm64 manifest digest)로 재핀 + `tests/test_image_constraints.py:96-102` 기대값
  갱신**을 추천안으로 둔다(T-326b 수정 파일). 이유: 그 테스트가 두 FROM의 `python:3.12-slim@sha256:…` 형식과 builder/runtime 동일
  digest를 이미 결박하고 있고(GDAL 바인딩이 builder 단계 `gdal-config` 버전에 링크되므로 두 단계가 같은 base여야 한다), 태그는 두
  호스트가 서로 다른 base를 받을 수 있다. 이것은 새 결박이 아니라 **기존 테스트 결박의 유지**다(과결박 금지와 충돌하지 않음 —
  arch 리터럴은 여전히 넣지 않는다). 설계대로 "태그 완화 + `test_image_constraints.py` 완화"도 선택지로 병기하며 **소유자 §14-6
  결정에 함께 묻는다**; 설계 쪽에는 "geo Dagster 이미지는 테스트 결박 때문에 태그 완화가 테스트 변경을 수반한다"는 정정을 전달.

### D8 — Track 1(ADR-069)과의 상호작용

- 소비자 센서의 `POST /v2/dataset/version` 폴링과 릴리스마다의 전 장소 reverse 재호출은 전환 뒤 **LAN·공개 키
  경로**(컨텍스트 7, D2). Map의 전량 재지오코딩(35,754행, loopback 순차 p50 ≈51 min 하한 — Track 1 Map 쪽 설계 수치,
  저장소 밖; Map ADR-109/110에 실림, 이 저장소 문서에는 없다)은 RTT(+6 min 가정) + odroid CPU ×3 가정으로 **≈2.5 h+**.
  `GEO_HEAVY_POOL`(Map ADR-109 proposed, 미구현 — instance 전역 1)의 유지 근거는 'n150 디스크 대기'에서 **'odroid CPU
  보호'**로 바뀐다(Map ADR-110에 기록; pool 자체는 불변).
- **풀로드(D3 기본)는 새 릴리스 → 새 `data_token`**을 만든다. **ADR-069 구현(T-325) 뒤의 동작(계획)**: 소비자 URL을
  `.13`으로 돌리는 순간 Track 1 센서가 전량 재계획을 만들어 막 적재를 끝낸 odroid geo에 재지오코딩이 걸린다 → **수용**
  (새 소스로 적재했으면 재지오코딩이 정확성상 옳다; 소유자 §14-19). T-325 **미구현** 상태로 플립하면 센서·재계획은 없고
  소비자는 기존 호출 경로로 즉시 `.13`을 본다(Track 1·Track 2 어느 쪽이 먼저 머지돼도 플립은 막히지 않는다 — T-326c 수용
  기준은 조건부). 단 URL 전환은 `full_load_batch` SUCCESS(mv_refresh child 포함, D3-5) **다음 날**, geo 야간 job 창 밖에서
  하고 운영자 UI의 계획 skip은 쓰지 않는다. **같은 n150 dump의 복원(D3 지름길)은 서빙 내용 지문이 같아 토큰이
  같으므로 재계획이 0**이다(ADR-069 D1) — 소유자가 §14-8에서 둘을 함께 고른다.
- 전환 창: §11.2 8a는 n150 geo **code-server만** 멈추고 geo-api는 9단계 게이트까지 serving한다. 소비자(와 센서)가 `.14`를
  보면서 n150 geo가 없는 창은 **9단계에서 n150 geo-api를 멈춘 뒤 `ensure map`이 끝나기까지**뿐이고, 그 짧은 창에서만 connect
  timeout(2 s, Map ADR-110·concierge ADR-50)으로 실패한다.

### D9 — 실측 항목(T-326a, T-063 승계)

- odroid envelope: `scripts/capture_deployment_envelope.py --run-probes`는 **스크립트 기본 probe만** 돈다 — fio
  `randread 8k QD32 ×4 jobs`·`sysbench cpu`·`sysbench memory`(`scripts/capture_deployment_envelope.py:134-176`; randwrite·
  4k·seq 1M은 없다). 설계 §11.1-1이 요구하는 나머지는 **수동 fio 3종**(randread/randwrite 4k QD32, seq 1M read/write —
  명령줄은 `docs/t055-deployment-n150-odroid.md` 정정 블록)으로 `/mnt/media/kor-travel/` 위에서 Plex 유휴·재생 중 **2회**.
  스크립트는 바꾸지 않는다(이번 PR 문서만; probe 집합 확장은 별도 결정). 그 밖에 `nvme smart-log`, `docker info`
  (`Architecture: aarch64`, `No memory limit support`/`No swap limit support` 문자열 **부재**).
- geo 소요: 풀로드 phase별 wall clock(T-055 §1 항목 그대로), `mv_refresh` 소요(D4 결정 입력), `db_restore`(지름길
  선택 시), n150→odroid `/v2/reverse` p50/p95(D8 추정 검증).
- 산출물은 T-055의 `artifacts/perf/n150-vs-odroid-<date>/<env>/` 구조에 `odroid-m1s` 라벨로.

## 근거

| 안 | 내용 | 판정 |
|---|---|---|
| A. geo만 n150 잔류 | 메모리 조건이 가장 많은 서비스를 안 옮긴다 | **D6 미달 시의 기본값**으로 유지. 옮기면 n150은 디스크 ≈34 GB(geo 몫; +temp 13 GB·MV swap 11.7 GiB 창)·geo cs 피크 4.8 GiB를 해방한다(설계 §3.6의 183 GB는 geo+weather+transport 합계) |
| B. 레지스트리 + 멀티아치(T-108) | 한 번 빌드, 두 호스트 pull | 기각(보류) — 새 기제(레지스트리·인증), 내용 해시 태그에 arch 없음이 선결, 호스트 2개에는 과함 |
| C. n150 dump 복원만(풀로드 없음) | 2.18 h×3(전용 12500 시절 값), Track 1 재계획 0, 발급 키 보존 | 소유자 §14-8 선택지로 유지 — 지시 "다시 로드"가 우선이라 기본은 풀로드. **전제**: NOCREATEDB 롤에서 Dagster `db_restore`는 E0410 → 수동 `pg_restore`(`shared_admin`) 또는 ADR-58 롤 amendment가 답에 포함돼야 한다(D3-6) |
| D. 트러스트 CIDR에 `.14` 추가(키 없이 통과) | 변경 최소 | 기각 — admin 면제 경로를 소비자에게 여는 것이고(컨텍스트 1) 키 정책이 무의미해진다 |
| E. VWorld 폴백 복귀(설계 §14-21 (가)) | DB 키 0, env 키 공유 | 추천 철회 — Map이 VWorld 키 통로를 가드로 끊었고(Map ADR-110 결정 §4, #979) 08-13 사고 구성과 같다; (나) 소비자별 발급을 추천(D2) — 풀로드 재적재마다 재발급·Map 전부 재생성·concierge DB 설정 비용은 수용 |

- 정확성: 호스트 이동은 geo 코드·계약을 바꾸지 않는다 — 바뀌는 것은 "누가 키를 대조당하는가"뿐이라 그것을
  결정으로 박았다(D2).
- 단일 정본: 운영 값의 자리는 Manager(compose·root `.env`·registry `hosts:`)이고 이 저장소는 포인터만 둔다(ADR-045).
  호스트 초기화·PG 인스턴스·메모리 정책은 Manager ADR-58이 정본이라 여기에 복제하지 않는다.
- 단순성: 레지스트리·QEMU·overlay 없음; 풀로드는 serving DB 직접; 백업 off.
- 과결박 금지: 이미지 핀·태그에 arch 리터럴을 넣지 않고 arch는 `ensure` 프리플라이트의 효과 검사(Manager)로.

## 결과(긍정)

- geo의 운영 호스트가 한 줄(`host: odroid`, Manager registry)로 바뀌고 이 저장소의 포트·DSN·CORS 문자열은 그대로다.
- 전용 PG 인스턴스 + NVMe로 geo의 IO 병목(temp spill·MV swap·GIN 빌드·dump)이 n150 공용 디스크 대기에서 벗어난다
  (단 PCIe 2.0 ×1 — 이득은 IOPS/지연, fio로 확인).
- n150 디스크 ≈34 GB(geo 몫) 해방, geo cs 피크 메모리 해방, 공용 PG 연결 감소.
- 키 정책이 명시된다 — 전환 뒤 peer `.14`는 CIDR 밖이라 면제 가능성이 구조적으로 0이 된다. 오늘도 면제가 아니라 키 경로였음은
  코드(Map actor 헤더 0건)와 journal 2026-08-17(발급 키 전환 완료)로 닫혔다(컨텍스트 1); D2의 전환 전 기록 1회는 현재 값
  (active 키 수·Map 키 유효성 200/401)을 남기는 것이다.

## 결과(부정)

- `full_load_batch` 12 h+(가정; 로더 + 게이트 + `mv_refresh` child를 **한 run에** 포함 — 별도 합산 없음) 하루 창 + (ADR-069
  구현 뒤) Track 1 전량 재지오코딩 ≈2.5 h+(수용) — n150 geo-api는 9단계까지 serving하므로 데이터 공백은 9단계의 짧은 창뿐이고,
  소비자 URL 전환은 batch SUCCESS 다음 날이다.
- standalone `mv_refresh`가 6 h 상한의 61~80 %(가정; 설계 표기 70~85 %)라 실측 전에는 상한 결정을 못 한다(D4).
- 풀로드 재적재·장애 재배포마다 키 재발급(D2 (나)) — Map `.env` + Map 전부 재생성 + concierge DB 설정, 3곳.
- odroid 메모리 최악 창(geo run ‖ weather 적재 ‖ Opinet)은 RAM을 넘는다 — memswap 정책으로 run FAILURE가
  되게 두는 것이고, 그 run은 재실행이다. geo 백업·drill이 없어 복구 수단은 재적재뿐(비범위 승인).
- 소비자가 `.13`을 보는 동안 odroid 다운은 RST가 아니라 timeout이다(소비자 ADR에서 connect timeout 분리).
- `docs/t055`·`docs/t108`의 x86·레지스트리 서술은 역사 기록으로 남고 정정 블록만 붙는다(본문 전면 개정 없음).

## 후속

- (open) **소유자 결정(설계 §14 번호)**. accepted 게이트 3건: §14-8 소스 ZIP 재확보 가능 여부·용량 + serving DB 직접
  풀로드 승인 + dump 복원 지름길 허용 여부(복원이면 D8 재계획 0·발급 키 보존; **고르면 (a) 수동 `pg_restore` 또는 (b) ADR-58 롤
  amendment 중 하나를 함께 — D3-6**); §14-12 geo 플립 여유 값(0.2 → anon ≤ 0.95 GiB) 또는 n150 잔류(잔류면 상태 `rejected`,
  상태 줄); §14-21 키 정책 — **(나) 소비자별 발급 추천으로 재질의**(설계의 (가) 추천은 Map ADR-110·journal 2026-08-17로
  철회, D2). 이 셋이 닫히면 상태 `accepted`(T-326b PR에서 한 줄). 추천안 수용이면 변경 0인 것 4건: §14-19 Track 1 전량 재계획
  수용(ADR-069 구현 뒤의 동작); §14-4 odroid plane 공개 host 이름; §14-7 geo 백업 off; §14-6 빌드 경로(odroid 현지 — D7 추천안 —
  vs 레지스트리) + Dagster base digest 처리(index 확인이 기대 결과; amd64일 때만 재핀 vs 태그 완화, D7) — 달리 결정되면 amendment.
- (open) T-326a — odroid envelope 실측(D9) + n150 geo cs·PG anon 실측(D6·§14-14 입력) + 플립 전 현재 값 기록 1회(D2: active
  키 수·Map 키 200/401, journal에) + base digest index 확인(D7) + T-055·T-108 정정(이번 PR에서 완료).
- (open) T-326b — 빈 호스트 풀로드 실행(D3; 순서는 §11.2 8a 플립 PR·n150 geo cs stop·odroid 재설치 **뒤**의 8b) + standalone
  `mv_refresh` 1회 실측 → 상한 결정·코드(D4: `recovery.py:15` 또는 `policy_for_job` 매핑 `:21-27` +
  `kor-travel-geo-dagster/tests/test_definitions.py:76-88`) + Dagster base digest 재핀(D7: amd64 manifest로 확인될 때만,
  `dagster.Dockerfile:34` + `tests/test_image_constraints.py`) + `.env.prod.example`·`docs/ports.md:34` 주석(D1·D2) + 소요 기록.
- (open) T-326c — §11.2 9단계(소비자 URL 전환) 뒤 검증: 키 경로 200(발급 키), `/v2/reverse` p50/p95, odroid access log peer
  `.14`, Track 1 센서 계획(T-325 구현 완료 시 1건 — dump 복원이면 0건; 미구현이면 해당 없음, journal에 어느 쪽인지 기록).
- (open) `docs/deploy/docker-compose.geo-source-vol.yml` 삭제 조건: Manager T-MGR-01d(상시 bind) 머지 **그리고** `geo-materialize`
  공유 볼륨이 Manager compose에 들어가거나 `source_rebuild_db` 경로 불사용 결정(D3-2).
- (open, 저장소 밖) 전달할 정정: **Manager** — T-MGR-01d의 컨테이너 경로 `/source` → `/app/data/source`(D3-2); T-MGR-01d에
  `geo-materialize:/app/data/rustfs/materialized` 공유 볼륨 1줄(또는 불사용 결정, D3-2); 지름길 (b) 선택 시 db-init geo 롤
  CREATEDB + `postgres` CONNECT(ADR-58 결정 (3)/(8) amendment, D3-6). **설계** — §3.3/§5.7의 "백업을 켜면 drill이 따라온다"
  (컨텍스트 5 — ADR-58 (8)(ⅶ)는 이미 독립 off라 대상 아님); §8.2/§8.4의 "amd64면 태그로 완화"는 geo Dagster 이미지에서
  `test_image_constraints.py:96-102` 변경을 수반(D7, §14-6 병기); **§9.1 키 행 "유효성 검증된 적 없음"·§5.6 ⑥ "loopback 면제로
  통과"·§14-21 "(가) 추천, 변경 0"은 틀렸다**(컨텍스트 1·D2 — Map ADR-110 컨텍스트 4와 같은 정정); §11.2 8b의 "full load →
  mv_refresh" 두 단계는 batch 한 run(D3-5)이고 "mv_refresh 소요 < 태그 상한의 70 %"는 standalone 1회 기준으로.
- (open) GDAL arm64 빌드 시간·메모리 실측; T-290l scratch 풀로드의 n150 wall clock 회수(컨텍스트, `load_jobs`/run store).

## 실행 기록 (2026-10-14~15)

결정 본문(D1~D9)은 바꾸지 않고, 실제로 일어난 일과 그것이 결정에 주는 입력만 날짜와 함께 둔다. 출처: 운영자 확인(2026-10-14~15)
+ 2026-10-15 08:2xZ odroid·n150 읽기 전용 재확인(DB는 geo-api 컨테이너의 DSN으로 SELECT만, env는 비밀이 아닌 키만 — journal
2026-10-15).

1. **적재 수단 = D3-6 지름길 (a)**: n150 2026-10-12 백업 `kor_travel_geo_backup_20261012T231533Z_zstd3`을 odroid
   `kor-travel-shared-postgres` 11000(arm64 `imresamu/postgis:16-3.5`)에 Dagster 밖 수동 `pg_restore --jobs=2`(rc=0, 오류 0, 51표·
   153인덱스; 표 19 GB/인덱스 12 GB — n150 19/15 GB). DB 크기 31 GB. 그 뒤 Alembic 0028→0029(ADR-069) + `ktgctl serving
   fingerprint-active`. D3의 기본(serving DB 직접 풀로드)은 **실행되지 않았다**; odroid geo 컨테이너에는 `/app/data/source` bind도
   아직 없다(D3-2 — Manager 몫, 다음 재적재 때 필요).
2. **결과 수치**: `mv_geocode_target`·`tl_juso_text` `count(*)` = 6,416,637 / 6,416,637(복원 원본 = n150 운영이므로 동일; T-290l
   참고값과 같다). 활성 릴리스는 n150의 것 그대로(`e0db4ff8…`, 2026-09-28 `manual_rebuild`, `mv_refresh strategy=swap`) — 복원은
   새 릴리스를 만들지 않았다. `ops.serving_releases`에는 n150 이력의 `pending`/`restore`(활성화 시각 NULL) 2행도 함께 왔다.
3. **D2 키**: 예측대로 복원이 `ops.public_api_keys`를 보존했다 — active 2건(`kor-travel-map` 2026-08-08, `pinvi-api` 2026-10-14).
   Map 키 재발급 없이 키 경로가 이어졌고, PinVi 전용 키는 (나) 소비자별 발급의 첫 사례다. **concierge**는 그때까지 VWorld 형식
   키를 보내 odroid geo에서 401이었고(DB에 키가 있어 VWorld 폴백이 꺼진 상태 — D2 함정 그대로), 2026-10-15 ≈09:00Z 전용 키
   `kor-travel-concierge`를 발급해 odroid에서 정상 응답(운영자 확인). 이로써 active 3건 = 소비자별 1개.
   **문서 정정**: D2·T-326a·런북의 `SELECT count(*) FROM ops.public_api_keys WHERE active`는 열 이름이 틀렸다(열은
   `state TEXT`) — `WHERE state = 'active'`로 고쳤다(이 PR).
4. **D1·D5 env 확인(odroid geo-api)**: `KTG_ADMIN_TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128`(`.14` 없음),
   `KTG_BACKUP_SCHEDULE_ENABLED=false`, `KTG_VWORLD_API_KEY` 비어 있지 않음, `KTG_DAGSTER_URL=http://127.0.0.1:11002`(odroid 공용 plane
   webserver), `KTG_DAGSTER_PUBLIC_URL=https://dagster-sub.digitie.mywire.org` — §14-4(odroid plane 공개 host)는 `dagster-sub.`로
   실행됐다. `.env.prod.example`·`docs/ports.md`의 `12502` 서술을 이 사실로 정정(T-326b 수정 파일 중 둘).
5. **D7**: odroid에서 빌드한 geo code-server 이미지가 `linux/arm64`이고 `dagster 1.13.24`·`sqlalchemy 2.1.1`·GDAL 3.10.3 바인딩이
   동작 — digest 핀이 arm64로 풀렸다(기대 결과, 재핀 논의 해당 없음; 빌드가 저장소 Dockerfile 그대로였는지는 빌드한 세션 확인).
6. **Dagster**: geo code server는 2026-10-15 02:52Z odroid 자체 plane으로(n150 cs 02:42Z 정지). odroid geo schedule·sensor는
   **STOPPED**. `mv_refresh`는 odroid에서 아직 한 번도 돌지 않아 **D4 입력(standalone 실측)이 없다**; 열 제약(CPU 1.416 GHz 캡,
   load ≈20)이라 ×3 가정보다 길 수 있으므로 schedule을 켜기 전에 D4를 결정해야 한다.
7. **D6**: 플립 게이트(n150 geo cs anon ≤ 0.95 GiB)는 측정 없이 플립됐다 — 사후 관찰(odroid 첫 `mv_refresh` 중 cs 메모리 최대·
   OOM 여부)로 대신한다(T-326a).
8. **D8 수정 입력**: "dump 복원이면 서빙 내용 지문이 같아 토큰이 같으므로 재계획 0"은 **양쪽에 토큰이 있다는 가정**이었다. n150
   DB는 Alembic 0028이라 `data_token`이 없었고 odroid에서 처음 생겼다(`version_token`은 같음). 소비자 센서가 "판정 불가 → 첫 토큰"을
   재계획으로 보는지는 소비자 규칙에 달렸다 → **소유자 결정(2026-10-15)으로 "기준선"**: 저장된 토큰이 없던 소비자가 처음 받은
   토큰은 저장만 하고 재해석·재계획하지 않는다(재해석은 저장값과 새 값이 둘 다 있고 다를 때만). 열 제약 odroid에 전량
   재지오코딩이 몰리는 것을 막기 위함. ADR-069 D8 amendment·`docs/api-reference/v2/dataset-version.md`·`llm-summary.md`에도 같은
   문구; 소비자 쪽 구현은 Map ADR-109·concierge 몫. T-326c는 실제 계획 건수 **0**을 확인한다.
9. **아직 서 있지 않은 전제**: n150 geo-api·geo-ui는 아직 Up(T-326c의 "n150 geo-api stop 상태에서" 검증 전제 미충족).

**소유자 결정(2026-10-15)** — 상태 `accepted`: (1) §14-8 dump 복원 (a)로 갈음, 풀로드는 다음 재적재 때(그때 D3-2 소스 bind·
D3 절차를 쓴다); (2) §14-12 odroid 이전 확정 — D6 게이트 대신 사후 메모리 관찰(T-326a ⓐ'); (3) §14-21 (나) 소비자별 키 1개씩;
(4) Track 1 기준선 규칙(위 8); (5) GeoIP gate는 n150·odroid 모두 `off` 유지(`.env.prod.example`을 `off`로, 코드 변경 없음 —
ADR-037의 대한민국 IP 제한은 운영에서 적용하지 않는 상태); (6) odroid schedule 재가동 전에 standalone `mv_refresh` 1회 실측
(운영자 실행) → D4 상한 결정(T-326b 남은 항목).
