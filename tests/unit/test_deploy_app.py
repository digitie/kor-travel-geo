from __future__ import annotations

from argparse import ArgumentTypeError

import pytest

from scripts.deploy_app import (
    DEFAULT_PLATFORMS,
    build_parser,
    build_plan,
    buildx_commands,
    parse_node_spec,
    render_markdown,
    render_remote_script,
)


def test_deploy_app_plan_defaults_use_dual_platforms() -> None:
    args = build_parser().parse_args(["plan", "--tag", "abc123"])
    plan = build_plan(args)

    assert plan.options.platforms == DEFAULT_PLATFORMS
    assert plan.options.api_image == "ghcr.io/digitie/kor-travel-geo-api:abc123"
    assert plan.options.ui_image == "ghcr.io/digitie/kor-travel-geo-ui:abc123"
    assert [node.label for node in plan.nodes] == ["n150", "odroid"]
    assert plan.nodes[0].platform == "linux/amd64"
    assert plan.nodes[1].platform == "linux/arm64"


def test_parse_node_spec_defaults_platform_from_label() -> None:
    n150 = parse_node_spec("n150=deploy@n150.local")
    odroid = parse_node_spec("odroid=deploy@odroid.local")

    assert n150.platform == "linux/amd64"
    assert odroid.platform == "linux/arm64"


def test_parse_node_spec_rejects_unsupported_platform() -> None:
    with pytest.raises(ArgumentTypeError):
        parse_node_spec("box=deploy@example,linux/s390x")


def test_buildx_commands_include_push_platforms_and_tags() -> None:
    args = build_parser().parse_args(["plan", "--tag", "abc123", "--latest"])
    commands = buildx_commands(build_plan(args).options)

    api_command = commands[0].command

    assert api_command[:4] == ("docker", "buildx", "build", "--platform")
    assert api_command[4] == "linux/amd64,linux/arm64"
    assert "-f" in api_command
    assert "docker/api.Dockerfile" in api_command
    assert "ghcr.io/digitie/kor-travel-geo-api:abc123" in api_command
    assert "ghcr.io/digitie/kor-travel-geo-api:latest" in api_command
    assert "--push" in api_command


def test_remote_script_uses_env_file_without_expanding_secret_values() -> None:
    args = build_parser().parse_args(
        [
            "plan",
            "--tag",
            "abc123",
            "--remote-env-file",
            "/etc/kor-travel-geo/app.env",
            "--remote-data-dir",
            "/srv/kor-travel-geo/data",
            "--node",
            "n150=deploy@n150.local,linux/amd64",
        ]
    )
    plan = build_plan(args)
    script = render_remote_script(plan.nodes[0], plan.options)

    assert "--env-file /etc/kor-travel-geo/app.env" in script
    assert "-v /srv/kor-travel-geo/data:/data:ro" in script
    assert "KTG_PG_DSN=" not in script
    assert "KTG_RUSTFS_SECRET_KEY=" not in script
    assert "curl -fsS http://127.0.0.1:12201/v1/healthz" in script


def test_markdown_renders_build_and_deploy_commands() -> None:
    args = build_parser().parse_args(["plan", "--tag", "abc123"])
    markdown = render_markdown(build_plan(args))

    assert "# T-108 운영 배포 자동화 계획" in markdown
    assert "## 빌드 명령" in markdown
    assert "## 배포 명령" in markdown
    assert "deploy@n150.local" in markdown
