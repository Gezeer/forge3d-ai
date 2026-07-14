import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/inspect_hunyuan_api.py"
SPEC = importlib.util.spec_from_file_location("inspect_hunyuan_api", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_inspector_resolves_openapi_json_properties():
    openapi = {
        "paths": {
            "/run/shape_generation": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Input"}
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Input": {
                    "properties": {
                        "image": {"type": "string"},
                        "steps": {"type": "integer", "default": 30},
                    }
                }
            }
        },
    }

    properties = MODULE.request_properties(openapi)

    assert properties["image"]["type"] == "string"
    assert properties["steps"]["default"] == 30
    assert MODULE.TARGET_ENDPOINT == "/run/shape_generation"


def test_inspector_redacts_signed_urls_tokens_and_paths():
    safe = MODULE.redact(
        {
            "url": "https://example/model.glb?token=SECRET",
            "token": "SECRET",
            "path": "/workspace/private/model.glb",
        }
    )
    assert safe == {"url": "[redacted]", "token": "[redacted]", "path": "[redacted]"}


def test_inspector_combines_prefix_and_logical_endpoint_without_duplication():
    prefix = MODULE.api_prefix({"api_prefix": "/gradio_api/"})

    assert prefix == "/gradio_api"
    assert (
        MODULE.execution_url(
            "http://127.0.0.1:8080/gradio_api",
            prefix,
            "/run/shape_generation",
        )
        == "http://127.0.0.1:8080/gradio_api/run/shape_generation"
    )
