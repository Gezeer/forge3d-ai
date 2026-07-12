import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/inspect_hunyuan_api.py"
SPEC = importlib.util.spec_from_file_location("inspect_hunyuan_api", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_signature_uses_published_order_defaults_and_image_type():
    endpoint = {
        "parameters": [
            {
                "parameter_name": "prompt",
                "parameter_has_default": True,
                "parameter_default": "",
            },
            {"parameter_name": "image", "component": "ImageEditor"},
            {
                "parameter_name": "steps",
                "parameter_has_default": True,
                "parameter_default": 30,
            },
            {"parameter_name": "optional"},
        ]
    }

    signature = MODULE.build_signature(endpoint)

    assert signature == {
        "args": ["", {"$image": "imageeditor"}, 30, None],
        "kwargs": {},
    }


def test_inspector_redacts_signed_urls_tokens_and_paths():
    safe = MODULE.redact(
        {
            "url": "https://example/model.glb?token=SECRET",
            "token": "SECRET",
            "path": "/workspace/private/model.glb",
        }
    )
    assert safe == {"url": "[redacted]", "token": "[redacted]", "path": "[redacted]"}
