"""Characterization of the complete automatic texture pipeline."""

import json
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.engines.contracts import JobContext
from app.infrastructure.subprocess_runner import ProcessResult
from app.texture.contracts import TextureRequest
from app.texture.hunyuan import HunyuanTextureService


class ValidatedPipelineFixture:
    def __init__(self):
        self.steps = []

    def run(self, command, timeout):
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"glTF" if output.suffix == ".glb" else b"mesh")
        self.steps.append(Path(command[3]).name if command[0] == "blender" else "paint")
        return ProcessResult(0)


def test_complete_texture_pipeline_with_robot_example(tmp_path: Path):
    forge3d = tmp_path / "forge3d"
    scripts = forge3d / "backend" / "scripts"
    scripts.mkdir(parents=True)
    for script in (
        "blender_glb_to_obj.py",
        "run_hunyuan_paint.py",
        "blender_obj_to_glb.py",
    ):
        (scripts / script).write_text("# test fixture", encoding="utf-8")
    hunyuan = tmp_path / "Hunyuan3D-2.1"
    hunyuan.mkdir()
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    examples = tmp_path / "examples"
    examples.mkdir()
    robot = examples / "robot.png"
    robot.write_bytes(b"validated robot image fixture")
    job_id = uuid4()
    job_dir = tmp_path / "outputs" / str(job_id)
    job_dir.mkdir(parents=True)
    model = job_dir / "model.glb"
    model.write_bytes(b"glTF white mesh")
    runner = ValidatedPipelineFixture()
    service = HunyuanTextureService(
        Settings(
            texture_root=hunyuan,
            forge3d_root=forge3d,
            texture_python=python,
            blender_executable="blender",
        ),
        runner,
    )

    result = service.generate_texture(
        JobContext(job_id, job_dir),
        model,
        robot,
        TextureRequest(2048, "standard"),
    )

    assert runner.steps == ["blender_glb_to_obj.py", "paint", "blender_obj_to_glb.py"]
    assert result.artifact_path == job_dir / "model_textured.glb"
    assert result.artifact_path.stat().st_size > 0
    metadata = json.loads((job_dir / "texture_metadata.json").read_text())
    assert metadata["output"] == "model_textured.glb"
