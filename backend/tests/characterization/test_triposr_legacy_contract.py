from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.services.triposr import TripoSRService


class NoopRunner:
    def run(self, command, timeout):
        raise AssertionError("characterization does not execute TripoSR")


def _service() -> TripoSRService:
    return TripoSRService(Settings(), NoopRunner())


def test_legacy_image_generation_route_is_preserved() -> None:
    from app.main import app

    routes = {(route.path, frozenset(route.methods or [])) for route in app.routes}
    assert ("/generate/image", frozenset({"POST"})) in routes


def test_triposr_command_preserves_gpu_and_glb_contract() -> None:
    command = _service().command(Path("/input.png"), Path("/output"))

    assert "/workspace/kai3d/models/TripoSR/run.py" in command
    assert command[command.index("--device") + 1] == "cuda:0"
    assert command[command.index("--model-save-format") + 1] == "glb"
    assert "--output-dir" in command


def test_triposr_output_path_is_zero_mesh_glb() -> None:
    source = Path(__file__).resolve().parents[2] / "app/services/triposr.py"
    assert 'job_dir / "0" / "mesh.glb"' in source.read_text(encoding="utf-8")


def test_legacy_download_route_and_glb_media_type_are_preserved() -> None:
    from app.main import app

    routes = {(route.path, frozenset(route.methods or [])) for route in app.routes}
    assert ("/download/{job_id}", frozenset({"GET"})) in routes
    source = Path(__file__).resolve().parents[2] / "app/api/routes/downloads.py"
    assert '"model/gltf-binary"' in source.read_text(encoding="utf-8")
