from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, TexturePipelineError
from app.engines.contracts import JobContext
from app.infrastructure.subprocess_runner import ProcessResult
from app.texture.contracts import TextureRequest
from app.texture.hunyuan import HunyuanTextureService


class PipelineRunner:
    def __init__(self, fail_at: int | None = None):
        self.fail_at = fail_at
        self.commands = []

    def run(self, command, timeout):
        self.commands.append((list(command), timeout))
        if self.fail_at == len(self.commands):
            return ProcessResult(1, stderr="private details")
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"artifact")
        return ProcessResult(0)


def settings(tmp_path: Path) -> Settings:
    root = tmp_path / "Hunyuan"
    root.mkdir()
    forge3d = tmp_path / "forge3d"
    scripts = forge3d / "backend" / "scripts"
    scripts.mkdir(parents=True)
    for name in (
        "run_hunyuan_paint.py",
        "blender_glb_to_obj.py",
        "blender_obj_to_glb.py",
    ):
        (scripts / name).write_text("# fixture", encoding="utf-8")
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    return Settings(
        texture_root=root,
        forge3d_root=forge3d,
        texture_python=python,
        blender_executable="blender",
        texture_timeout_seconds=4,
    )


def inputs(tmp_path: Path):
    job_id = uuid4()
    job_dir = tmp_path / str(job_id)
    job_dir.mkdir()
    mesh = job_dir / "model.glb"
    mesh.write_bytes(b"white")
    image = job_dir / "image.png"
    image.write_bytes(b"png")
    return JobContext(job_id, job_dir), mesh, image


def test_texture_service_runs_blender_paint_blender(tmp_path: Path):
    runner = PipelineRunner()
    service = HunyuanTextureService(settings(tmp_path), runner)
    context, mesh, image = inputs(tmp_path)

    result = service.generate_texture(
        context, mesh, image, TextureRequest(2048, "high")
    )

    assert [Path(call[0][3]).name for call in runner.commands[::2]] == [
        "blender_glb_to_obj.py",
        "blender_obj_to_glb.py",
    ]
    assert Path(runner.commands[1][0][1]).name == "run_hunyuan_paint.py"
    assert runner.commands[1][0][runner.commands[1][0].index("--cache-dir") + 1] == str(
        service.settings.texture_cache
    )
    assert result.artifact_path == context.job_dir / "model_textured.glb"
    assert result.artifact_path.read_bytes() == b"artifact"
    assert mesh.read_bytes() == b"white"
    assert (context.job_dir / "texture_metadata.json").is_file()
    assert result.metadata["resolution"] == 2048
    assert (context.job_dir / "texture_work" / "white_mesh.obj").is_file()
    assert (context.job_dir / "texture_work" / "textured_mesh.obj").is_file()


@pytest.mark.parametrize(
    ("failure", "step"),
    [(1, "glb_to_obj"), (2, "paint"), (3, "obj_to_glb")],
)
def test_texture_service_reports_exact_failed_step(
    tmp_path: Path, failure: int, step: str
):
    context, mesh, image = inputs(tmp_path)
    service = HunyuanTextureService(settings(tmp_path), PipelineRunner(failure))

    with pytest.raises(TexturePipelineError) as raised:
        service.generate_texture(context, mesh, image, TextureRequest(1024, "standard"))

    assert raised.value.to_dict() == {
        "status": "error",
        "step": step,
        "message": f"Falha na etapa {step}",
    }
    assert mesh.read_bytes() == b"white"
    assert not (context.job_dir / "model_textured.glb").exists()


def test_texture_service_builds_commands_without_python_expr(tmp_path: Path):
    runner = PipelineRunner()
    service = HunyuanTextureService(settings(tmp_path), runner)
    context, mesh, image = inputs(tmp_path)
    service.texture(context, mesh, image, TextureRequest(768, "fast"))

    assert all("--python-expr" not in command for command, _ in runner.commands)
    assert runner.commands[0][0][:3] == ["blender", "-b", "--python"]
    assert runner.commands[2][0][:3] == ["blender", "-b", "--python"]


def test_texture_service_rejects_missing_shape_artifact(tmp_path: Path):
    runner = PipelineRunner()
    service = HunyuanTextureService(settings(tmp_path), runner)
    context, mesh, image = inputs(tmp_path)
    mesh.unlink()

    with pytest.raises(ArtifactNotFoundError, match="Malha original não encontrada"):
        service.texture(context, mesh, image, TextureRequest(512, "fast"))

    assert runner.commands == []


class TimeoutRunner:
    def run(self, command, timeout):
        raise TimeoutError("timeout")


def test_texture_service_normalizes_timeout(tmp_path: Path):
    service = HunyuanTextureService(settings(tmp_path), TimeoutRunner())
    context, mesh, image = inputs(tmp_path)

    with pytest.raises(TexturePipelineError) as raised:
        service.texture(context, mesh, image, TextureRequest(512, "fast"))

    assert raised.value.step == "glb_to_obj"
    assert "timeout" not in str(raised.value).lower()
