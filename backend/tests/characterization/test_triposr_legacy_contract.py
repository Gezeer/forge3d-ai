from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MAIN_MODULE = BACKEND_ROOT / "main.py"


def _source() -> str:
    return MAIN_MODULE.read_text(encoding="utf-8")


def _subprocess_command() -> list[str]:
    tree = ast.parse(_source())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "run":
            continue
        command = node.args[0]
        if not isinstance(command, ast.List):
            continue
        result: list[str] = []
        for element in command.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                result.append(element.value)
            elif isinstance(element, ast.Name):
                result.append(f"<{element.id}>")
        return result
    raise AssertionError("subprocess.run command was not found")


def test_legacy_image_generation_route_is_preserved() -> None:
    assert '@app.post("/generate/image")' in _source()
    assert "UploadFile" in _source()


def test_triposr_command_preserves_gpu_and_glb_contract() -> None:
    command = _subprocess_command()

    assert "<TRIPOSR_RUN>" in command
    assert command[command.index("--device") + 1] == "cuda:0"
    assert command[command.index("--model-save-format") + 1] == "glb"
    assert "--output-dir" in command


def test_triposr_output_path_is_zero_mesh_glb() -> None:
    tree = ast.parse(_source())
    path_parts = [
        [
            element.value
            for element in node.args
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
    ]

    assert any(parts[-2:] == ["0", "mesh.glb"] for parts in path_parts)


def test_legacy_download_route_and_glb_media_type_are_preserved() -> None:
    source = _source()

    assert '@app.get("/download/{job_id}")' in source
    assert 'media_type="model/gltf-binary"' in source
    assert 'download_url": f"/download/{job_id}"' in source
