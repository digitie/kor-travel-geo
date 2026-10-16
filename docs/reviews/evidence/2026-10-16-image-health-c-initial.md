# Geo579 이미지 health·stdlib bytecode 독립 검토 C

판정: SOURCE_PASS. 열린 P0/P1/P2=0. 범위 FULL10이며 저자·A 리뷰 결과를 읽거나 합산하지 않았다.

- 기준 HEAD a316c340bd9ecec3d0eb0907f74dc830cbd8c0d2 / base Geo578 9a3d68770e0c4978b57228fb101785873d180486.
- root 요청: 새 APIHTTP2xx headers 경량화/최종 stdlib compile 위치/Common344 pin/constraints/기존 CS guard와 defaultSTOPPED/실패 전달/메모리/Compose override 계약 전체10파일 검토.
- 기존 Geo577의 본인 저술은 신규 독립 검토로 세지 않는다. 현재10파일 delta와 연결 실행 경로를 직접 검토했다.
- AGENTS/SKILL/README/architecture/resume/ADR 색인 및 workflow·failure-patterns를 읽고 Linux Git object와 자체 ext4 archive를 사용했다. 원 WT 제품/문서 수정0.

## 전체 변경과 실행 경계

두 Dockerfile, pyproject 두 개, 회귀 두 파일, CHANGELOG/journal/resume와 새 runbook 전체를 읽었다. API는 새 core Common만 api extra로 설치하며 main core에는 Common·gRPC·Dagster 강제가 없다. CS는 기존 dagster/grpc-health extras에 같은344 pin이다. API VCS 설치용 git 추가는 맞고 별도 가변 경로 설치를 만들지 않는다.

API는 설치·GDAL ABI 검사 후 최종 interpreter/root로 compile을 한 번 실행한다. CS는 최종 runtime stage의 /install COPY 뒤/root에서 실행하고 이후 USER appuser·원 ENTRYPOINT/CMD로 돌아간다. 최종 stdlib를 덮는 후속 COPY는 없다. helper CLI가 실패하면 Docker RUN이 그대로 실패한다. 해당 helper는 별도 Common37 검토 대상이며 여기서 실제 stdlib를 컴파일하지 않았다.

API HC는 원 PORT와 같은 확장/default12501, exec Python -I Common HTTP CLI, /v1/healthz, 내부4초이며 원 운영 interval10/timeout5/retries12/start30을 명시한다. healthz 원 함수는 상수 응답이고 DB 준비·readiness는 별도다. 헤더2xx만 검사하므로 본문·redirect 의미를 기존 urllib와 같다고 하지 않는다. Compose 명시 HC가 이미지 HC를 덮으므로 Manager 소유 선언의 별도 변경/리뷰/배포가 필요하다는 안내를 확인했다.

constraints 전체·GDAL serial 설정·원 Dagster storage guard/entrypoint·dagster.yaml/workspace·API 및 Dagster runtime src·UI/NPM은 base와 byte 불변이다. Common d1aa→344에는 Common35 factory와 Common36 canonical leader 경로 변경 및37 build helper가 포함된다. 전체 runtime delta를 읽었고 기존 single factory API 위임과 기본 상태·원점/시계 guards를 확인했다. 이 제품을 다시 독립 승인한 수로 합산하지 않는다. Geo의 native sensor 등록/defaultSTOPPED·원 job/retry/cadence 설정 자체는 바뀌지 않는다.

## 직접 실행

작성자 환경은 읽기 전용 interpreter로만 사용하고, 소스는 Git archive a316의 자체 경로로 고정했다. pytest --noconftest로 신규8와 기존 설치·optional 경계8을 실행해 16 PASS(1.39초). 실제 합성 loopback 200/302/503, quiet stdout/stderr, proxy 우회·heavy import 차단, fake gRPC SERVING/NOT_SERVING/닫힌포트/optional부재, 기본/override PORT와 실패 종료 전달을 확인했다. no conftest/DB0/실제 stdlib compile0.

원578 archive에 신규8회귀만 넣어 실행하니 5 FAIL/3 PASS였다. compile 두 역할·pin·HC 기본/override가 없어서 각각 실패하며 설치된 Common HTTP 자체를 쓰는3개만 통과했다. 새 회귀의 판별력을 직접 확인했다. 원본 코드는 바꾸지 않았다.

- 새 실행 원문 geo579-review-c-a316-tests-20261016.log SHA49a1299aba86059abb8e404f6e6adb70e197b1e763a6033a02bcd1962a3884e4.
- old RED 원문 geo579-review-c-old-red-20261016.log SHAc73c87b7a26040a097744770129e29e002c2c21c03b9a6c38ba5e2d562e8d0b5.
- 저자 전체1915/141SKIP·148 등은 이번 본인 실행으로 세지 않는다.

## 미검증과 적용 조건

실제 Docker/ARM 빌드, 최종 interpreter magic/flags/sourcehash/pyc 읽기권한, 프로세스 메모리·CPU, Compose 현재 override 및 운영 응답은 NOT_RUN이다. main ancestor 확인→merged source 빌드→exact full metadata/원 source·Config 및 intended HC delta→배포→동일 부하 측정 순서가 필요하다. 기본 -I는 PYTHONDONTWRITEBYTECODE를 무시하지만 읽기만 막지 않는다는 문구는 맞다. stdlib 전체 compile은 단일worker라도 크기·메모리가 실제 이미지마다 다르므로 이16회귀를 자원 예산 증거로 쓰지 않는다.
