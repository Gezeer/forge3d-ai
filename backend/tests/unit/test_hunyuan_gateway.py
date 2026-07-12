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
