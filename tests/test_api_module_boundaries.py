from __future__ import annotations

import importlib

from server.api import payloads, schemas

SCHEMA_DOMAINS = (
    "server.api.schema.analytics",
    "server.api.schema.improvement",
    "server.api.schema.overview",
    "server.api.schema.query",
    "server.api.schema.system",
    "server.api.schema.traces",
)
PAYLOAD_DOMAINS = (
    "server.api.payload_domains.analytics",
    "server.api.payload_domains.budget",
    "server.api.payload_domains.compare",
    "server.api.payload_domains.files",
    "server.api.payload_domains.guard",
    "server.api.payload_domains.improvement",
    "server.api.payload_domains.overview",
    "server.api.payload_domains.system",
    "server.api.payload_domains.tools",
    "server.api.payload_domains.traces",
)


def _public_names(modules: tuple[str, ...], *, prefix: str) -> dict[str, object]:
    names: dict[str, object] = {}
    for module_name in modules:
        module = importlib.import_module(module_name)
        for name, value in vars(module).items():
            if name.startswith(prefix) and getattr(value, "__module__", None) == module_name:
                assert name not in names, f"{name} has more than one owning domain"
                names[name] = value
    return names


def test_schema_facade_reexports_each_domain_model_by_identity() -> None:
    expected = _public_names(SCHEMA_DOMAINS, prefix="")
    expected = {name: value for name, value in expected.items() if isinstance(value, type)}

    assert set(schemas.__all__) == set(expected)
    for name, value in expected.items():
        assert getattr(schemas, name) is value


def test_payload_facade_reexports_each_public_builder_by_identity() -> None:
    expected = _public_names(PAYLOAD_DOMAINS, prefix="build_")

    assert set(payloads.__all__) == set(expected)
    for name, value in expected.items():
        assert getattr(payloads, name) is value
