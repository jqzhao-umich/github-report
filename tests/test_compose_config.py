"""Compose configuration regression tests.

PROJECT_REVIEW.md called out that `docker-compose.yml` shipped without
`AUTH_TOKEN` passthrough, so the default deployment came up anonymous.
These tests pin the fixed contract at the YAML level so a future edit
can't silently reintroduce the fail-open regression.

We assert on the parsed compose file rather than shelling out to
`docker compose config`, both to keep tests hermetic (no docker
binary required) and to keep them fast.
"""

from pathlib import Path

import pytest
import yaml


@pytest.fixture(scope="module")
def compose_config():
    path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def _service_env_list(compose_config, service_name):
    env = compose_config["services"][service_name]["environment"]
    if isinstance(env, dict):
        return [f"{k}={v}" for k, v in env.items()]
    return list(env)


def test_compose_requires_auth_token_env_passthrough(compose_config):
    """AUTH_TOKEN must be listed in the service's environment so it
    reaches the container. Absent, the container would run with an
    unset AUTH_TOKEN and (per auth.py) return 503 on every request."""
    envs = _service_env_list(compose_config, "github-report-app")
    assert any(e.startswith("AUTH_TOKEN=") for e in envs), (
        "docker-compose.yml no longer passes AUTH_TOKEN through — the "
        "publisher/report routes will 503 on every request until it does."
    )


def test_compose_auth_token_uses_required_syntax(compose_config):
    """`docker compose up` must fail fast when AUTH_TOKEN is completely
    unset. The `${AUTH_TOKEN?...}` form does that at compose-time; the
    plain `${AUTH_TOKEN}` form silently expands to empty and reopens
    the fail-open regression."""
    envs = _service_env_list(compose_config, "github-report-app")
    auth_line = next(e for e in envs if e.startswith("AUTH_TOKEN="))
    assert "${AUTH_TOKEN?" in auth_line or "${AUTH_TOKEN:?" in auth_line, (
        "AUTH_TOKEN must use the ${AUTH_TOKEN?...} required-variable "
        "syntax so misconfiguration fails at `compose up` time.\n"
        f"Got: {auth_line}"
    )


def test_compose_allow_anonymous_is_optional(compose_config):
    """ALLOW_ANONYMOUS is the dev-mode opt-in and must be passed
    through with a default-empty expansion — otherwise operators
    couldn't run the service without a real token for local iteration."""
    envs = _service_env_list(compose_config, "github-report-app")
    assert any("ALLOW_ANONYMOUS=" in e for e in envs), (
        "ALLOW_ANONYMOUS is missing from Compose environment — dev mode "
        "won't work without setting AUTH_TOKEN to a placeholder."
    )


def test_compose_binds_loopback_by_default(compose_config):
    """The default port mapping must NOT expose the service on all
    interfaces. Users who explicitly want that set BIND_ADDRESS=0.0.0.0."""
    ports = compose_config["services"]["github-report-app"]["ports"]
    for mapping in ports:
        # Long-form (dict) or short-form ("HOST:PORT:CONTAINER")?
        if isinstance(mapping, dict):
            host_ip = str(mapping.get("host_ip", ""))
            assert host_ip in ("127.0.0.1", "::1") or "127.0.0.1" in host_ip, (
                f"Port mapping does not bind loopback: {mapping!r}"
            )
        else:
            # short form. Must be prefixed with an address (a bare
            # "8000:8000" is the fail-open all-interfaces bind).
            parts = str(mapping).split(":")
            assert len(parts) >= 3, (
                f"Port mapping {mapping!r} has no host address — this is "
                "the docker default 0.0.0.0 bind. Add a host address "
                "(e.g. 127.0.0.1:8000:8000 or ${BIND_ADDRESS:-127.0.0.1}:8000:8000)."
            )
            host = parts[0]
            # Accept either a literal loopback or the ${BIND_ADDRESS:-127.0.0.1}
            # variable expansion (loopback default).
            assert (
                host in ("127.0.0.1", "::1")
                or "127.0.0.1" in host
                or "BIND_ADDRESS" in host
            ), (
                f"Port mapping {mapping!r} does not default to loopback."
            )
