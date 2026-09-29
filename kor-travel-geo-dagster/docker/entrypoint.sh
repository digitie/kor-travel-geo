#!/bin/sh
# T-322: dagster_postgres는 psycopg2만 지원한다. bare postgresql:// storage URL은 SQLAlchemy 2.1부터
# psycopg 3로 바뀌어 run이 시작되지 못하고 webserver GraphQL이 500이 되는데, daemon liveness와
# healthcheck(repositoriesOrError)는 계속 통과해 "건강해 보이는 채로" 배포된다
# (docs/t322-dagster-storage-driver.md). 그래서 세 서비스(code-server/webserver/daemon)가 시작 전에
# 드라이버를 확인하고, 아니면 즉시 죽는다 — 조용히 run만 못 도는 것보다 재시작 루프가 낫다.
# 값이 비어 있으면 여기서 막지 않는다: dagster.yaml의 env 조회가 스스로 크게 실패한다.
set -eu
case "${KTG_DAGSTER_PG_URL:-}" in
  "" | postgresql+psycopg2://*) ;;
  *)
    scheme=$(printf '%s' "$KTG_DAGSTER_PG_URL" | sed -n 's#^\([A-Za-z0-9+.-]*\)://.*#\1#p')
    echo "FATAL: KTG_DAGSTER_PG_URL must use postgresql+psycopg2:// (got scheme '${scheme:-?}')." \
      "dagster_postgres only supports psycopg2; see docs/t322-dagster-storage-driver.md (T-322)." >&2
    exit 64
    ;;
esac
exec "$@"
