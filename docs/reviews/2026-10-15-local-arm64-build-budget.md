# ARM64 UI 빌드 작업자 예산

## 실제 관측

로컬 CPU quota 2·cpuset 2개·메모리/메모리+swap 각 2GiB인 독립 BuildKit에서
기존 UI Dockerfile을 linux/arm64로 빌드했다. Next 16.2.12가 host의 CPU 수를 읽어
page data 작업자 15개를 시작했다. builder 메모리는 관측 시 1.988~1.991GiB에 닿았으며
page data 단계가 진행되지 않아 이미 오래된 후보의 본인 buildx CLI에 SIGINT를 보냈다.
전체 627.889초 뒤 exit 130을 확인했다. 이 실행은 성공이나 OOM 확정으로 표시하지 않는다.
다른 builder·프로세스나 운영 컨테이너를 중지하지 않았다. 원래 로그는 별도 증거로 보존한다.

## 최소 설정

Next 설치 소스의 config-shared.js는 기본 cpus를 host CPU 수에서 계산하고,
config-shared.d.ts와 config-schema.js는 experimental.cpus 숫자 옵션을 제공한다.
next.config.mjs에 experimental.cpus=2를 명시해 실제 빌드 CPU 예산과 맞춘다.
Next 자체 production config loader에서도 2를 확인했고 strict mode·Turbopack alias 2개·
webpack fallback은 보존한다. Dockerfile·의존성·렌더링 기능은 변경하지 않는다.

이는 2가 모든 환경의 최적값이라는 결론이 아니다. 15개 작업자와 2GiB 포화라는
실제 관측에 대응해 build fanout을 제한한 값이다. API·Dagster의 수집 동시성이나
런타임 메모리·DB 쿼리 예산을 변경하는 설정도 아니다.

## 최종 검증 범위

최종 불변 SHA를 같은 CPU2·2GiB builder에서 다시 빌드해 실제 worker 수와 완료 여부,
실측 메모리를 기록한다. cgroup memory high-water에는 file cache도 포함되므로 RSS와
같다고 부르지 않는다. 주기적으로 샘플링한 process RSS도 연속 측정의 정확한 최대값으로
과장하지 않는다. 원천 전체 manifest·이미지 revision/vendor·실제 bundle hash를 함께 남긴다.
최종 이미지·운영 배포/live E2E는 이 설정 구현만으로 통과했다고 표시하지 않는다.

## UI 재빌드 결과와 GDAL OOM

같은 CPU2·2GiB 한도에서 8614 UI는 270.843초에 완료했고 Next 로그의 page data/static
worker는 2개였다. 이전 빌드는 취소되었고 cache 상태도 같다고 증명하지 않았으므로
전체 속도 개선 비율은 산출하지 않는다. 새 빌드도 샘플 cgroup 사용량은 2GiB에 닿았다.
작업자 수와 완료를 검증했을 뿐 전체 메모리 최대 사용량 감소로 표시하지 않는다.

뒤이은 8614 API는 GDAL 3.10.3 wheel의 C++ wrapper 여러 개를 동시에 컴파일하다
659.422초에 실패했다. cc1plus의 Killed 로그와 본인 BuildKit cgroup의
memory.events oom=1/oom_kill=1을 함께 확인했다. 이 실패는 앞선 UI 취소와 달리
실제 OOM으로 분류한다. 원본 로그·실패 receipt를 보존하고 운영 빌드는 하지 않았다.

[GDAL 3.10.3 공식 setup 소스](https://github.com/OSGeo/gdal/blob/v3.10.3/swig/python/setup.py.in)의
build_ext는 initialize_options에서 parallel=True를 기본으로 둔다. CPU quota와 별개로
setuptools가 host CPU 수를 작업자 수로 사용할 수 있다. 공식 setuptools 사용자 설정
[build_ext] parallel=1이 이를 integer 1로 덮는 것을 실제 파싱으로 확인했다.
소형 실제 C extension 2개도 같은 기본 subclass와 임시 HOME 설정으로 각각 빌드했다.
기본 동시 compiler 최대 2 → 설정 적용 최대 1이며 양쪽 모두 extension 2개가 생성되었다.
이는 GDAL 전체 빌드 성공을 대신하지 않는 로컬 메커니즘 검증이다.

API와 Dagster builder의 해당 pip invocation 동안만 임시 HOME의 .pydistutils.cfg를
적용한다. 기본 이미지·GDAL 버전 일치 검사·Dagster constraints·의존성 resolve와 runtime
사용자는 보존하고, 임시 파일/빈 디렉터리는 같은 RUN에서 제거한다. CS는 기존 계약대로
GDAL과 loaders/code-location을 한 pip invocation으로 설치한다. 실패하면 image build 자체가
중단되어 설정이 남은 최종 이미지를 생성하지 않는다. 새 SHA의 실제 ARM64 API/CS 빌드와
archive 검증이 끝날 때까지 성공으로 표시하지 않는다. 운영 동시성/timeout/DB 스키마 변경은 없다.

## API 종료 신호 전달 계약

기존 API CMD의 sh -c uvicorn은 shell 아래 별도 API child를 만들었다.
본인 Linux 시험에서도 실제 Dockerfile CMD를 그대로 실행한 로컬 대역의 PID가
shell PID와 달라 기본/명시 host·port 두 회귀가 모두 실패했다.
CMD 앞에 exec만 추가해 shell을 API로 교체한다. 환경변수의 기본값/명시값 확장은
유지하고 API가 직접 SIGTERM을 받아 graceful shutdown할 수 있게 한다.

새 회귀는 실제 CMD를 본인 임시 session과 Python 대역 executable로 실행한다.
같은 PID와 host/port 인수, 그 PID에 보낸 SIGTERM의 handler 호출·exit0을 검증한다.
본인 session/group만 정리하며 Docker/운영 프로세스를 호출하지 않는다.
이는 실제 Uvicorn 요청/DB drain의 운영 검증이 아니므로 그 검증은 별도 배포에서 수행한다.
기존 c324 ARM64 실행은 불변 context에서 끝내 보존하고 새 HEAD의 CMD는 캐시 기반
재export와 source/이미지 검증 후에만 운영 후보로 사용한다.
