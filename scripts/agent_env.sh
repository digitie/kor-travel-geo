# shellcheck shell=bash
# WSL ext4 테스트 미러 셸에서 backend/frontend 검증 전에 "source"한다 (실행 아님):
#   source scripts/agent_env.sh
#
# NTFS(/mnt) + WSL 혼용에서 에이전트가 반복적으로 헤매던 두 함정을 한 번에 없앤다.
# 배경/전체 셋업: docs/agent-workflow.md, docs/dev-environment.md
#
#   함정 1) TMP/TEMP가 Windows Temp(/mnt/c/...)를 가리키면 pytest capture가 시작 전 FileNotFoundError
#   함정 2) Windows npm/node shim(/mnt/c/.../npm)이 PATH 앞에 잡혀 `node: not found`/UNC 에러
#
# 이 스크립트는 현재 셸에만 영향을 준다 (전역 WSL interop를 바꾸지 않는다).

# 함정 1: Linux /tmp를 강제한다.
export TMPDIR=/tmp TMP=/tmp TEMP=/tmp

# 미러에 만든 프로젝트 venv가 있으면 활성화한다 (dev-environment.md §3).
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi

# 함정 2: 프론트 검증용 Linux Node가 Windows shim보다 앞서게 한다.
# nvm이 있으면 우선 사용하고, 없으면 경고만 한다(frontend_check.sh도 /mnt npm이면 hard-fail).
if [ -z "${KRADDR_SKIP_NVM:-}" ] && [ -s "$HOME/.nvm/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  nvm use --silent default >/dev/null 2>&1 || true
fi

_kg_npm="$(command -v npm 2>/dev/null || true)"
case "$_kg_npm" in
  "" | /mnt/* | *.exe | *.cmd)
    echo "agent_env: WARN Linux npm이 PATH 앞에 없음. 프론트 검증 전에 Linux Node를 PATH 앞에 두세요 (docs/agent-workflow.md §1)." >&2
    ;;
  *) : ;;
esac

echo "agent_env: TMPDIR=$TMPDIR; python=$(command -v python 2>/dev/null || echo '-'); npm=${_kg_npm:-'-'}"
unset _kg_npm
