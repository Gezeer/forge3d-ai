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
                        "caption": {"default": None},
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


class FakeHttp:
    def __init__(self, gets=None, posts=None):
        self.gets = list(gets or [])
        self.posts = list(posts or [])
        self.calls = []

    def get(self, url, *, timeout):
        self.calls.append(("GET", url, timeout, None))
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


def test_client_posts_json_to_run_shape_generation(tmp_path: Path):
    image = tmp_path / "robot.png"
    image.write_bytes(b"png")
    http = FakeHttp(
        [response(200, openapi())],
        [response(200, {"value": "/tmp/white_mesh.glb"})],
    )
    client = HunyuanClient("http://hunyuan:8080", http_client=http)

    result = client.generate(image, 20)

    method, url, timeout, payload = http.calls[-1]
    assert (method, url, timeout) == (
        "POST",
        "http://hunyuan:8080/run/shape_generation",
        20,
    )
    assert payload == result.request_payload
    assert "args" not in payload


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
