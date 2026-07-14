from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from app.core.exceptions import GenerationTimeoutError, ServiceUnavailableError
from app.infrastructure.hunyuan_client import HunyuanClient


def response(status: int, payload) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("GET", "http://hunyuan.test"),
    )


def openapi(image_schema=None):
    return {
        "openapi": "3.1.0",
        "paths": {
            "/run/shape_generation": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ShapeInput"}
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "ShapeInput": {
                    "type": "object",
                    "required": ["image"],
                    "properties": {
                        "image": image_schema or {"type": "string"},
                        "mv_image_front": {"default": None},
                        "mv_image_back": {"default": None},
                        "mv_image_left": {"default": None},
                        "mv_image_right": {"default": None},
                        "steps": {"type": "integer", "default": 30},
                        "guidance_scale": {"type": "number", "default": 5.0},
                        "seed": {"type": "integer", "default": 1234},
                        "octree_resolution": {"type": "integer", "default": 256},
                        "check_box_rembg": {"type": "boolean", "default": True},
                        "num_chunks": {"type": "integer", "default": 8000},
                        "randomize_seed": {"type": "boolean", "default": False},
                    },
                }
            }
        },
    }


def gradio_config(*, include_state=True):
    components = [{"id": 1, "type": "image"}]
    inputs = [1]
    if include_state:
        components.insert(0, {"id": 0, "type": "state"})
        inputs.insert(0, 0)
    for component_id in range(2, 13):
        components.append({"id": component_id, "type": "component"})
        inputs.append(component_id)
    return {
        "api_prefix": "/gradio_api",
        "components": components,
        "dependencies": [{"api_name": "shape_generation", "inputs": inputs}],
    }


class FakeHttp:
    def __init__(self, gets=None, posts=None):
        self.gets = list(gets or [])
        self.posts = list(posts or [])
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append(("GET", url, timeout, None))
        if not self.gets:
            return response(404, {"detail": "not found"})
        value = self.gets.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def post(self, url, *, json, timeout):
        self.calls.append(("POST", url, timeout, json))
        value = self.posts.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_client_discovers_openapi_and_builds_named_json(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    http = FakeHttp([response(200, openapi())])
    client = HunyuanClient("http://127.0.0.1:8080", http_client=http)

    schema = client.discover(2)
    payload = client.build_payload(image, schema)

    assert payload["image"].startswith("data:image/png;base64,")
    assert payload["steps"] == 30
    assert payload["guidance_scale"] == 5.0
    assert payload["mv_image_front"] is None
    assert "args" not in payload
    assert http.calls[0][1].endswith("/gradio_api/openapi.json")


def test_client_adapts_imageditor_schema(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    schema = openapi(
        {
            "type": "object",
            "properties": {
                "background": {},
                "layers": {"type": "array"},
                "composite": {},
            },
        }
    )
    client = HunyuanClient("http://hunyuan", http_client=FakeHttp())

    value = client.build_payload(image, schema)["image"]

    assert value["background"].startswith("data:image/png;base64,")
    assert value["layers"] == []
    assert value["composite"] is None


def test_client_resolves_nullable_filedata_schema(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    schema = openapi(
        {
            "anyOf": [
                {"$ref": "#/components/schemas/FileData"},
                {"type": "null"},
            ]
        }
    )
    schema["components"]["schemas"]["FileData"] = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "url": {}},
    }
    client = HunyuanClient("http://hunyuan", http_client=FakeHttp())

    value = client.build_payload(image, schema)["image"]

    assert value["path"] == str(image.resolve())
    assert value["meta"] == {"_type": "gradio.FileData"}


def test_client_retries_while_gradio_is_loading():
    delays = []
    http = FakeHttp(
        [response(503, {"detail": "Models loading"}), response(200, openapi())]
    )
    client = HunyuanClient(
        "http://hunyuan",
        retry_attempts=2,
        retry_base_seconds=0.25,
        http_client=http,
        sleeper=delays.append,
    )

    assert client.available(2) is True
    assert delays == [0.25]


def test_health_discovery_never_executes_generation():
    http = FakeHttp(
        [response(200, openapi()), response(200, {"api_prefix": "/gradio_api"})]
    )
    client = HunyuanClient("http://hunyuan:8080", http_client=http)

    assert client.available(2) is True
    assert [call[0] for call in http.calls] == ["GET", "GET"]
    assert client.diagnostics()["execution_url"] == (
        "http://hunyuan:8080/gradio_api/run/shape_generation"
    )


def test_client_posts_json_to_run_shape_generation(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    http = FakeHttp(
        [response(200, openapi()), response(200, gradio_config())],
        [response(200, {"value": "/tmp/white_mesh.glb"})],
    )
    client = HunyuanClient("http://hunyuan:8080", http_client=http)

    result = client.generate(image, 20)

    method, url, timeout, payload = http.calls[-1]
    assert (method, url, timeout) == (
        "POST",
        "http://hunyuan:8080/gradio_api/run/shape_generation",
        20,
    )
    assert client.endpoint == "/run/shape_generation"
    assert payload == {
        "data": [
            None,
            result.request_payload["image"],
            None,
            None,
            None,
            None,
            30,
            5.0,
            1234,
            256,
            True,
            8000,
            False,
        ]
    }
    assert len(payload["data"]) == 13
    assert payload["data"][0] is None
    assert payload["data"][1] == result.request_payload["image"]


def test_client_uses_single_fallback_state_when_config_is_unavailable(
    tmp_path: Path,
):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    http = FakeHttp(
        [response(200, openapi()), response(404, {"detail": "not found"})],
        [response(200, {"data": []})],
    )
    client = HunyuanClient("http://hunyuan:8080", http_client=http)

    client.generate(image, 20)

    data = http.calls[-1][3]["data"]
    assert len(data) == 13
    assert data[0] is None
    assert data[1] is not None


def test_client_does_not_duplicate_state_published_by_contract(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    schema = openapi()
    shape_input = schema["components"]["schemas"]["ShapeInput"]
    shape_input["properties"] = {
        "state": {"type": "state"},
        **shape_input["properties"],
    }
    shape_input["required"].insert(0, "state")
    http = FakeHttp(
        [response(200, schema), response(200, gradio_config())],
        [response(200, {"data": []})],
    )
    client = HunyuanClient("http://hunyuan:8080", http_client=http)

    result = client.generate(image, 20)

    data = http.calls[-1][3]["data"]
    assert len(data) == 13
    assert data[:2] == [None, result.request_payload["image"]]


def test_client_preserves_safe_remote_http_500_summary(tmp_path: Path, caplog):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    http = FakeHttp(
        [response(200, openapi()), response(200, gradio_config())],
        [
            response(
                500,
                {
                    "error": (
                        "needed: 13, got: 12 "
                        "https://signed.test/file?token=SECRET /tmp/private.glb"
                    )
                },
            )
        ],
    )
    client = HunyuanClient("http://hunyuan:8080", http_client=http)

    with pytest.raises(
        ServiceUnavailableError,
        match=r"HTTP 500: needed: 13, got: 12 \[url\]",
    ):
        client.generate(image, 20)

    assert "SECRET" not in caplog.text
    assert "needed: 13, got: 12" in caplog.text


def test_client_does_not_duplicate_gradio_api_prefix(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    http = FakeHttp(
        [response(200, openapi()), response(200, {"api_prefix": "/gradio_api/"})],
        [response(200, {"value": "/tmp/white_mesh.glb"})],
    )
    client = HunyuanClient(
        "http://hunyuan:8080/gradio_api",
        endpoint="/run/shape_generation",
        http_client=http,
    )

    client.generate(image, 20)

    assert http.calls[-1][1] == ("http://hunyuan:8080/gradio_api/run/shape_generation")
    assert "/gradio_api/gradio_api/" not in http.calls[-1][1]


def test_client_normalizes_relative_gradio_file_url(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    http = FakeHttp(
        [response(200, openapi())],
        [response(200, {"data": [{"url": "/gradio_api/file=/tmp/model.glb"}]})],
    )
    client = HunyuanClient("http://hunyuan:8080", http_client=http)

    result = client.generate(image, 20)

    assert result.data["data"][0]["url"] == (
        "http://hunyuan:8080/gradio_api/file=/tmp/model.glb"
    )


def test_client_maps_generation_timeout(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    request = httpx.Request("POST", "http://hunyuan/run/shape_generation")
    http = FakeHttp(
        [response(200, openapi())],
        [httpx.ReadTimeout("timeout", request=request)],
    )
    client = HunyuanClient("http://hunyuan", http_client=http)

    with pytest.raises(GenerationTimeoutError):
        client.generate(image, 1)


def test_client_rejects_openapi_without_real_endpoint():
    http = FakeHttp([response(200, {"paths": {"/shape_generation": {"post": {}}}})])
    client = HunyuanClient("http://hunyuan", retry_attempts=1, http_client=http)

    with pytest.raises(ServiceUnavailableError, match="OpenAPI"):
        client.discover(1)
