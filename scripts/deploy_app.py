"""Plan, build, and deploy kor-travel-geo API/UI Docker images."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

DEFAULT_PLATFORMS = ("linux/amd64", "linux/arm64")
DEFAULT_NODES = (
    "n150=deploy@n150.local,linux/amd64",
    "odroid=deploy@odroid.local,linux/arm64",
)
SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class NodeSpec:
    label: str
    ssh_target: str
    platform: str


@dataclass(frozen=True, slots=True)
class DeployOptions:
    registry: str
    tag: str
    api_image_name: str
    ui_image_name: str
    api_image: str
    ui_image: str
    api_container: str
    ui_container: str
    network_name: str
    restart_policy: str
    remote_env_file: str
    remote_data_dir: str
    api_host_port: int
    api_container_port: int
    ui_host_port: int
    ui_container_port: int
    platforms: tuple[str, ...]
    push: bool
    include_latest: bool


@dataclass(frozen=True, slots=True)
class CommandPlan:
    name: str
    command: tuple[str, ...]
    stdin: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentPlan:
    schema_version: int
    generated_at: str
    options: DeployOptions
    nodes: tuple[NodeSpec, ...]
    build_commands: tuple[CommandPlan, ...]
    deploy_commands: tuple[CommandPlan, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Write a dry-run deployment plan.")
    _add_common_args(plan_parser)
    plan_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/deploy/t108"),
        help="Directory for deploy-plan.json and deploy-plan.md.",
    )

    build_parser_ = subparsers.add_parser("build", help="Run docker buildx build commands.")
    _add_common_args(build_parser_)

    deploy_parser = subparsers.add_parser("deploy", help="Deploy API/UI containers over SSH.")
    _add_common_args(deploy_parser)
    deploy_parser.set_defaults(require_nodes=True)

    all_parser = subparsers.add_parser("all", help="Build images, then deploy over SSH.")
    _add_common_args(all_parser)
    all_parser.set_defaults(require_nodes=True)

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", default="ghcr.io/digitie")
    parser.add_argument("--tag", help="Image tag. Defaults to git short SHA, then 'dev'.")
    parser.add_argument("--api-image-name", default="kor-travel-geo-api")
    parser.add_argument("--ui-image-name", default="kor-travel-geo-ui")
    parser.add_argument("--api-image", help="Full API image ref. Overrides registry/name/tag.")
    parser.add_argument("--ui-image", help="Full UI image ref. Overrides registry/name/tag.")
    parser.add_argument("--api-container", default="kor-travel-geo-api")
    parser.add_argument("--ui-container", default="kor-travel-geo-ui")
    parser.add_argument("--network-name", default="kor-travel-geo-net")
    parser.add_argument("--restart-policy", default="unless-stopped")
    parser.add_argument("--remote-env-file", default="/etc/kor-travel-geo/app.env")
    parser.add_argument("--remote-data-dir", default="/data/kor-travel-geo")
    parser.add_argument("--api-host-port", type=int, default=12201)
    parser.add_argument("--api-container-port", type=int, default=12201)
    parser.add_argument("--ui-host-port", type=int, default=12205)
    parser.add_argument("--ui-container-port", type=int, default=12205)
    parser.add_argument(
        "--platform",
        action="append",
        dest="platforms",
        help="Buildx platform. May be passed more than once.",
    )
    parser.add_argument(
        "--push",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use buildx --push. --no-push is only valid for a single platform.",
    )
    parser.add_argument(
        "--latest",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also tag images as :latest.",
    )
    parser.add_argument(
        "--node",
        action="append",
        dest="nodes",
        help=(
            "Remote node in LABEL=SSH_TARGET,PLATFORM form. "
            "Example: n150=deploy@n150.local,linux/amd64"
        ),
    )


def parse_node_spec(value: str) -> NodeSpec:
    head, sep, platform = value.partition(",")
    if not sep:
        platform = _default_platform_for_label(head.partition("=")[0])
    label, eq, ssh_target = head.partition("=")
    if not eq or not label.strip() or not ssh_target.strip():
        msg = "node must use LABEL=SSH_TARGET,PLATFORM"
        raise argparse.ArgumentTypeError(msg)
    label = _safe_label(label.strip())
    platform = platform.strip()
    if platform not in DEFAULT_PLATFORMS:
        msg = f"unsupported node platform: {platform}"
        raise argparse.ArgumentTypeError(msg)
    return NodeSpec(label=label, ssh_target=ssh_target.strip(), platform=platform)


def build_options(args: argparse.Namespace) -> DeployOptions:
    tag = args.tag or _git_short_sha() or "dev"
    platforms = tuple(args.platforms or DEFAULT_PLATFORMS)
    if len(platforms) > 1 and not args.push:
        msg = "--no-push can only be used with one --platform"
        raise SystemExit(msg)
    registry = args.registry.rstrip("/")
    api_image = args.api_image or f"{registry}/{args.api_image_name}:{tag}"
    ui_image = args.ui_image or f"{registry}/{args.ui_image_name}:{tag}"
    return DeployOptions(
        registry=registry,
        tag=tag,
        api_image_name=args.api_image_name,
        ui_image_name=args.ui_image_name,
        api_image=api_image,
        ui_image=ui_image,
        api_container=args.api_container,
        ui_container=args.ui_container,
        network_name=args.network_name,
        restart_policy=args.restart_policy,
        remote_env_file=args.remote_env_file,
        remote_data_dir=args.remote_data_dir,
        api_host_port=args.api_host_port,
        api_container_port=args.api_container_port,
        ui_host_port=args.ui_host_port,
        ui_container_port=args.ui_container_port,
        platforms=platforms,
        push=args.push,
        include_latest=args.latest,
    )


def build_plan(args: argparse.Namespace) -> DeploymentPlan:
    options = build_options(args)
    node_values = tuple(args.nodes or DEFAULT_NODES)
    nodes = tuple(parse_node_spec(value) for value in node_values)
    if getattr(args, "require_nodes", False) and tuple(args.nodes or ()) == ():
        msg = "--node is required for deploy/all"
        raise SystemExit(msg)
    return DeploymentPlan(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        options=options,
        nodes=nodes,
        build_commands=buildx_commands(options),
        deploy_commands=tuple(remote_deploy_command(node, options) for node in nodes),
    )


def buildx_commands(options: DeployOptions) -> tuple[CommandPlan, ...]:
    return (
        CommandPlan(
            name="build-api",
            command=_buildx_command(
                dockerfile="docker/api.Dockerfile",
                context=".",
                image=options.api_image,
                latest_image=_latest_image(options.registry, options.api_image_name)
                if options.include_latest
                else None,
                platforms=options.platforms,
                push=options.push,
            ),
        ),
        CommandPlan(
            name="build-ui",
            command=_buildx_command(
                dockerfile=None,
                context="kor-travel-geo-ui",
                image=options.ui_image,
                latest_image=_latest_image(options.registry, options.ui_image_name)
                if options.include_latest
                else None,
                platforms=options.platforms,
                push=options.push,
            ),
        ),
    )


def remote_deploy_command(node: NodeSpec, options: DeployOptions) -> CommandPlan:
    script = render_remote_script(node, options)
    return CommandPlan(
        name=f"deploy-{node.label}",
        command=("ssh", node.ssh_target, "bash", "-s"),
        stdin=script,
    )


def render_remote_script(node: NodeSpec, options: DeployOptions) -> str:
    api_run = _docker_run_api(options)
    ui_run = _docker_run_ui(options)
    lines = [
        "set -euo pipefail",
        f"echo '[deploy:{node.label}] platform {node.platform}'",
        f"test -f {_q(options.remote_env_file)}",
        "docker --version",
        _network_command(options.network_name),
        _remove_container_command(options.ui_container),
        _remove_container_command(options.api_container),
        _shell_join(api_run),
        _shell_join(ui_run),
        _healthcheck_command(options.api_host_port, "/v1/healthz", "api"),
        _healthcheck_command(options.ui_host_port, "/api/runtime-config", "ui"),
    ]
    lines.append(f"echo '[deploy:{node.label}] done'")
    return "\n".join(lines) + "\n"


def write_plan(plan: DeploymentPlan, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "deploy-plan.json").write_text(
        json.dumps(_plan_to_dict(plan), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "deploy-plan.md").write_text(render_markdown(plan), encoding="utf-8")


def render_markdown(plan: DeploymentPlan) -> str:
    lines = [
        "# T-108 운영 배포 자동화 계획",
        "",
        "| 항목 | 값 |",
        "|------|----|",
        f"| generated_at | `{plan.generated_at}` |",
        f"| api_image | `{plan.options.api_image}` |",
        f"| ui_image | `{plan.options.ui_image}` |",
        f"| platforms | `{', '.join(plan.options.platforms)}` |",
        f"| remote_env_file | `{plan.options.remote_env_file}` |",
        f"| remote_data_dir | `{plan.options.remote_data_dir}` |",
        "",
        "## 노드",
        "",
        "| label | ssh_target | platform |",
        "|-------|------------|----------|",
    ]
    for node in plan.nodes:
        lines.append(f"| `{node.label}` | `{node.ssh_target}` | `{node.platform}` |")
    lines.extend(["", "## 빌드 명령", ""])
    lines.extend(_command_blocks(plan.build_commands))
    lines.extend(["", "## 배포 명령", ""])
    lines.extend(_command_blocks(plan.deploy_commands))
    lines.append("")
    return "\n".join(lines)


def execute_commands(commands: Iterable[CommandPlan]) -> None:
    for command in commands:
        print(f"[deploy-app] running {command.name}: {_shell_join(command.command)}")
        subprocess.run(command.command, input=command.stdin, text=True, check=True)


def main() -> None:
    args = build_parser().parse_args()
    plan = build_plan(args)
    if args.command == "plan":
        write_plan(plan, args.output_dir)
        print(args.output_dir)
    elif args.command == "build":
        execute_commands(plan.build_commands)
    elif args.command == "deploy":
        execute_commands(plan.deploy_commands)
    elif args.command == "all":
        execute_commands((*plan.build_commands, *plan.deploy_commands))
    else:
        msg = f"unknown command: {args.command}"
        raise SystemExit(msg)


def _buildx_command(
    *,
    dockerfile: str | None,
    context: str,
    image: str,
    latest_image: str | None,
    platforms: Sequence[str],
    push: bool,
) -> tuple[str, ...]:
    command = ["docker", "buildx", "build", "--platform", ",".join(platforms)]
    if dockerfile is not None:
        command.extend(("-f", dockerfile))
    command.extend(("-t", image))
    if latest_image is not None:
        command.extend(("-t", latest_image))
    command.append("--push" if push else "--load")
    command.append(context)
    return tuple(command)


def _docker_run_api(options: DeployOptions) -> tuple[str, ...]:
    return (
        "docker",
        "run",
        "-d",
        "--name",
        options.api_container,
        "--restart",
        options.restart_policy,
        "--pull",
        "always",
        "--network",
        options.network_name,
        "--network-alias",
        "kor-travel-geo-api",
        "-p",
        f"{options.api_host_port}:{options.api_container_port}",
        "-v",
        f"{options.remote_data_dir}:/data:ro",
        "--env-file",
        options.remote_env_file,
        "-e",
        f"PORT={options.api_container_port}",
        "-e",
        "KTG_API_HOST=0.0.0.0",
        "-e",
        "KTG_RUSTFS_LOCAL_IMPORT_ROOTS=/data",
        options.api_image,
    )


def _docker_run_ui(options: DeployOptions) -> tuple[str, ...]:
    return (
        "docker",
        "run",
        "-d",
        "--name",
        options.ui_container,
        "--restart",
        options.restart_policy,
        "--pull",
        "always",
        "--network",
        options.network_name,
        "-p",
        f"{options.ui_host_port}:{options.ui_container_port}",
        "--env-file",
        options.remote_env_file,
        "-e",
        f"PORT={options.ui_container_port}",
        "-e",
        "HOSTNAME=0.0.0.0",
        "-e",
        f"KTG_API_INTERNAL_URL=http://kor-travel-geo-api:{options.api_container_port}",
        "-e",
        "NEXT_PUBLIC_API_BASE_URL=/api/proxy",
        options.ui_image,
    )


def _network_command(network_name: str) -> str:
    quoted = _q(network_name)
    return f"docker network inspect {quoted} >/dev/null 2>&1 || docker network create {quoted}"


def _remove_container_command(container_name: str) -> str:
    return f"docker rm -f {_q(container_name)} >/dev/null 2>&1 || true"


def _healthcheck_command(port: int, path: str, label: str) -> str:
    url = f"http://127.0.0.1:{port}{path}"
    return (
        "for i in $(seq 1 30); do "
        f"curl -fsS {_q(url)} >/dev/null && break; "
        "if [ \"$i\" = 30 ]; then "
        f"echo '{label} healthcheck failed' >&2; exit 1; "
        "fi; sleep 2; done"
    )


def _latest_image(registry: str, image_name: str) -> str:
    return f"{registry}/{image_name}:latest"


def _default_platform_for_label(label: str) -> str:
    cleaned = label.lower()
    if "odroid" in cleaned or "arm" in cleaned:
        return "linux/arm64"
    return "linux/amd64"


def _git_short_sha() -> str | None:
    try:
        result = subprocess.run(
            ("git", "rev-parse", "--short", "HEAD"),
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _plan_to_dict(plan: DeploymentPlan) -> dict[str, object]:
    return {
        "schema_version": plan.schema_version,
        "generated_at": plan.generated_at,
        "options": asdict(plan.options),
        "nodes": [asdict(node) for node in plan.nodes],
        "build_commands": [asdict(command) for command in plan.build_commands],
        "deploy_commands": [asdict(command) for command in plan.deploy_commands],
    }


def _command_blocks(commands: Iterable[CommandPlan]) -> list[str]:
    lines: list[str] = []
    for command in commands:
        if command.stdin:
            lines.extend(
                [
                    f"### {command.name}",
                    "",
                    "```bash",
                    f"{_shell_join(command.command)} <<'REMOTE_SCRIPT'",
                    command.stdin.rstrip(),
                    "REMOTE_SCRIPT",
                ]
            )
        else:
            lines.extend([f"### {command.name}", "", "```bash", _shell_join(command.command)])
        lines.extend(["```", ""])
    return lines


def _safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
    return cleaned or "node"


def _shell_join(command: Sequence[str]) -> str:
    return " ".join(_q(part) for part in command)


def _q(value: str) -> str:
    return shlex.quote(value)


if __name__ == "__main__":
    main()
