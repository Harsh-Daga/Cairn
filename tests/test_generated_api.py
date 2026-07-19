"""Committed OpenAPI-derived artifacts must remain deterministic and current."""

from scripts.build_ui import API_DOC_OUT, COMPAT_OUT, TYPES_OUT, generate_types
from server.app import create_app
from server.config import Settings


def test_generated_api_artifacts_are_current() -> None:
    assert TYPES_OUT.is_file()
    assert COMPAT_OUT.is_file()
    assert API_DOC_OUT.is_file()
    generate_types(check=True)


def test_openapi_uses_stable_ids_and_standard_error_contract(tmp_path) -> None:
    document = create_app(Settings(workspace_root=tmp_path)).openapi()
    operation_ids: list[str] = []
    for path_item in document["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operation_ids.append(operation["operationId"])
            for status in ("400", "401", "403", "404", "413", "422"):
                schema = operation["responses"][status]["content"]["application/json"]["schema"]
                assert schema == {"$ref": "#/components/schemas/ErrorResponse"}

    assert operation_ids
    assert len(operation_ids) == len(set(operation_ids))
    assert document["components"]["schemas"]["ErrorResponse"]["examples"]
