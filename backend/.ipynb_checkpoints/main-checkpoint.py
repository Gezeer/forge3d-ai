from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import os
import uuid
import shutil

app = FastAPI(title="Forge3D AI API")

UPLOAD_DIR = "/workspace/forge3d-ai/uploads"
OUTPUT_DIR = "/workspace/forge3d-ai/outputs"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.get("/")
def home():
    return {
        "name": "Forge3D AI",
        "status": "running",
        "message": "AI 3D generation API online"
    }

@app.post("/generate/image")
async def generate_from_image(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return JSONResponse({
        "status": "received",
        "job_id": job_id,
        "input": input_path,
        "message": "Imagem recebida. Próximo passo: conectar ao TripoSR."
    })
