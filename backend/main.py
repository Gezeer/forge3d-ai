import os
import uuid
import shutil
import subprocess

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

app = FastAPI(
    title="Forge3D AI API",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/workspace/forge3d-ai/uploads"
OUTPUT_DIR = "/workspace/forge3d-ai/outputs"
TRIPOSR_RUN = "/workspace/kai3d/models/TripoSR/run.py"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.get("/")
def home():
    return {
        "name": "Forge3D AI",
        "status": "running",
        "version": "0.1.0"
    }


@app.post("/generate/image")
async def generate_image(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())

    input_path = os.path.join(
        UPLOAD_DIR,
        f"{job_id}_{file.filename}"
    )

    output_dir = os.path.join(
        OUTPUT_DIR,
        job_id
    )

    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    command = [
        "python",
        TRIPOSR_RUN,
        input_path,
        "--device",
        "cuda:0",
        "--model-save-format",
        "glb",
        "--output-dir",
        output_dir
    ]

    process = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    glb_path = os.path.join(output_dir, "0", "mesh.glb")
    success = process.returncode == 0 and os.path.exists(glb_path)

    return JSONResponse(
        {
            "status": "success" if success else "error",
            "job_id": job_id,
            "return_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "output_dir": output_dir,
            "glb_exists": os.path.exists(glb_path),
            "download_url": f"/download/{job_id}" if success else None
        }
    )


@app.get("/download/{job_id}")
def download_model(job_id: str):
    file_path = os.path.join(
        OUTPUT_DIR,
        job_id,
        "0",
        "mesh.glb"
    )

    if not os.path.exists(file_path):
        return JSONResponse(
            {
                "error": "Arquivo GLB não encontrado.",
                "path": file_path
            },
            status_code=404
        )

    return FileResponse(
        path=file_path,
        filename=f"{job_id}.glb",
        media_type="model/gltf-binary"
    )


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    glb_path = os.path.join(
        OUTPUT_DIR,
        job_id,
        "0",
        "mesh.glb"
    )

    exists = os.path.exists(glb_path)

    return {
        "job_id": job_id,
        "status": "completed" if exists else "not_found",
        "glb_exists": exists,
        "download_url": f"/download/{job_id}" if exists else None
    }


@app.get("/health")
def health():
    return {
        "api": "ok",
        "triposr_run_exists": os.path.exists(TRIPOSR_RUN),
        "upload_dir": UPLOAD_DIR,
        "output_dir": OUTPUT_DIR
    }