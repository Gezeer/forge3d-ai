from concurrent.futures import Future
from pathlib import Path

import pytest
from app.core.exceptions import ServiceUnavailableError
from app.infrastructure.hunyuan_gateway import (
    GradioHunyuanGateway,
    HunyuanSignature,
)


class FakeClient:
    def __init__(self, result) -> None:
        self.result = result
        self.submission = None

    def submit(self, *args, **kwargs):
        self.submission = (args, kwargs)
        future = Future()
        future.set_result(self.result)
        return future


def test_gateway_injects_image_into_inspected_signature() -> None:
    client = FakeClient(["result"])
    gateway = GradioHunyuanGateway(
        "http://hunyuan:8080",
        client_factory=lambda _: client,
        file_handler=lambda path: f"handled:{path}",
    )
    signature = HunyuanSignature(args=[None, {"$image": True}], kwargs={"seed": 1234})

    result = gateway.predict(Path("/tmp/image.png"), signature, "/real", 5)

    assert result == ["result"]
    assert client.submission == (
        (None, "handled:/tmp/image.png"),
        {"api_name": "/real", "seed": 1234},
    )


def test_gateway_handles_unavailable_gradio_port() -> None:
    def unavailable(_):
        raise ConnectionError("refused")

    gateway = GradioHunyuanGateway(
        "http://127.0.0.1:8080",
        client_factory=unavailable,
        file_handler=lambda path: path,
    )

    with pytest.raises(ServiceUnavailableError, match="indisponível"):
        gateway.predict(Path("image.png"), HunyuanSignature(), "/api", 5)


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("simple", "handled:/tmp/image.png"),
        ("imagedata", "handled:/tmp/image.png"),
        (
            "imageeditor",
            {
                "background": "handled:/tmp/image.png",
                "layers": [],
                "composite": None,
            },
        ),
    ],
)
def test_gateway_builds_published_image_formats(marker, expected) -> None:
    client = FakeClient("ok")
    gateway = GradioHunyuanGateway(
        "http://hunyuan:8080",
        client_factory=lambda _: client,
        file_handler=lambda path: f"handled:{path}",
    )

    gateway.predict(
        Path("/tmp/image.png"),
        HunyuanSignature(
            args=[{"$image": marker}, "published-default"],
            kwargs={"optional": None},
        ),
        "/shape_generation",
        5,
    )

    assert client.submission[0] == (expected, "published-default")
    assert client.submission[1]["optional"] is None


def test_gateway_rejects_invalid_image_format() -> None:
    gateway = GradioHunyuanGateway(
        "http://hunyuan:8080",
        client_factory=lambda _: FakeClient("ok"),
        file_handler=lambda path: path,
    )

    with pytest.raises(ServiceUnavailableError, match="Formato"):
        gateway.predict(
            Path("image.png"),
            HunyuanSignature(args=[{"$image": "invalid"}]),
            "/shape_generation",
            5,
        )
