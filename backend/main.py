import os
import uuid
import shutil
import subprocess

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from services.hunyuan import HunyuanService

app = FastAPI(title="Forge3D AI API", version="0.2.0")

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

hunyuan_service = HunyuanService()


@app.get("/")
def home():
    return {"name": "Forge3D AI", "status": "running", "version": "0.2.0"}


@app.get("/health")
def health():
    return {
        "api": "ok",
        "triposr_run_exists": os.path.exists(TRIPOSR_RUN),
        "upload_dir": UPLOAD_DIR,
        "output_dir": OUTPUT_DIR,
    }


@app.post("/generate/image")
async def generate_image(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    input_image = os.path.join(job_dir, file.filename)

    with open(input_image, "wb") as f:
        shutil.copyfileobj(file.file, f)

    process = subprocess.run(
        [
            "/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python",
            TRIPOSR_RUN,
            input_image,
            "--device",
            "cuda:0",
            "--model-save-format",
            "glb",
            "--output-dir",
            job_dir,
        ],
        capture_output=True,
        text=True,
    )

    glb = os.path.join(job_dir, "0", "mesh.glb")

    if not os.path.exists(glb):
        return JSONResponse(
       
            status_code=500,
            content={
                "status": "error",
                "error": "mesh.glb não foi gerado",
                "stdout": process.stdout,
                "stderr": process.stderr,
            },
        )

    return {
        "status": "success",
        "job_id": job_id,
        "download_url": f"/download/{job_id}",
        "glb_exists": True,
    }


@app.get("/download/{job_id}")
def download(job_id: str):
    glb = os.path.join(OUTPUT_DIR, job_id, "0", "mesh.glb")

    if not os.path.exists(glb):
        return JSONResponse(
            status_code=404,
            content={"error": "Arquivo não encontrado"},
        )

    return FileResponse(
        glb,
        filename="model.glb",
        media_type="model/gltf-binary",
    )

@app.post("/generate/hunyuan")
async def generate_hunyuan(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    input_path = os.path.join(
        UPLOAD_DIR,
        f"hunyuan_{job_id}_{file.filename}"
    )

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = hunyuan_service.generate(input_path)

        return JSONResponse({
            "engine": "hunyuan",
            "status": "success",
            **result
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "engine": "hunyuan",
                "status": "error",
                "error": str(e)
            }
        )
