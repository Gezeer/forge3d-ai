import os
import shutil
import subprocess
import uuid
from hunyuan_service import generator
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(
    title="Forge3D AI API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = "/workspace/forge3d-ai"
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

TRIPOSR_DIR = "/workspace/models/TripoSR"
TRIPOSR_RUN = os.path.join(TRIPOSR_DIR, "run.py")
TRIPOSR_PYTHON = os.path.join(TRIPOSR_DIR, "venv", "bin", "python")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
@app.get("/")
def home():
    return {
        "name": "Forge3D AI",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {
        "api": "ok",
        "triposr_run_exists": os.path.exists(TRIPOSR_RUN),
        "triposr_python_exists": os.path.exists(TRIPOSR_PYTHON),
        "upload_dir_exists": os.path.isdir(UPLOAD_DIR),
        "output_dir_exists": os.path.isdir(OUTPUT_DIR),
    }
@app.post("/generate/image")
async def generate_image(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())

    input_path = os.path.join(
        UPLOAD_DIR,
        f"{job_id}_{os.path.basename(file.filename)}",
    )

    output_dir = os.path.join(
        OUTPUT_DIR,
        job_id,
    )

    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    cmd = [
        TRIPOSR_PYTHON,
        TRIPOSR_RUN,
        input_path,
        "--device",
        "cuda:0",
        "--model-save-format",
        "glb",
        "--output-dir",
        output_dir,
    ]

    result = subprocess.run(
        cmd,
        cwd=TRIPOSR_DIR,
        capture_output=True,
        text=True,
    )

    glb = os.path.join(output_dir, "0", "mesh.glb")
    success = result.returncode == 0 and os.path.exists(glb)

    data = {
        "status": "success" if success else "error",
        "job_id": job_id,
        "return_code": result.returncode,
        "glb_exists": os.path.exists(glb),
        "download_url": f"/download/{job_id}" if success else None,
    }

    if not success:
        data["stdout"] = result.stdout[-3000:]
        data["stderr"] = result.stderr[-3000:]

    return JSONResponse(
        content=data,
        status_code=200 if success else 500,
    )


@app.post("/generate/hunyuan")
async def generate_hunyuan(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())

    safe_filename = os.path.basename(file.filename or "imagem.png")

    input_path = os.path.join(
        UPLOAD_DIR,
        f"{job_id}_{safe_filename}",
    )

    output_dir = os.path.join(
        OUTPUT_DIR,
        job_id,
        "0",
    )

    output_glb = os.path.join(
        output_dir,
        "mesh.glb",
    )

    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        generator.generate(
            image_path=input_path,
            output_glb=output_glb,
        )

        success = os.path.exists(output_glb)

        return JSONResponse(
            content={
                "status": "success" if success else "error",
                "engine": "hunyuan3d-2.1",
                "quality": "high",
                "job_id": job_id,
                "glb_exists": success,
                "download_url": (
                    f"/download/{job_id}"
                    if success
                    else None
                ),
            },
            status_code=200 if success else 500,
        )

    except Exception as error:
        return JSONResponse(
            content={
                "status": "error",
                "engine": "hunyuan3d-2.1",
                "job_id": job_id,
                "message": str(error),
            },
            status_code=500,
        )




@app.get("/download/{job_id}")
def download_model(job_id: str):
    glb = os.path.join(
        OUTPUT_DIR,
        job_id,
        "0",
        "mesh.glb",
    )

    if not os.path.exists(glb):
        return JSONResponse(
            {"error": "Arquivo não encontrado"},
            status_code=404,
        )

    return FileResponse(
        glb,
        filename=f"{job_id}.glb",
        media_type="model/gltf-binary",
    )


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    glb = os.path.join(
        OUTPUT_DIR,
        job_id,
        "0",
        "mesh.glb",
    )

    return {
        "job_id": job_id,
        "status": "completed" if os.path.exists(glb) else "processing",
        "glb_exists": os.path.exists(glb),
        "download_url": f"/download/{job_id}" if os.path.exists(glb) else None,
    }
