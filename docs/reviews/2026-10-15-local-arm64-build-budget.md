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
