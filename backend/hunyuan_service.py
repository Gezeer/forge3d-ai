import os
import sys
import torch
from PIL import Image

ROOT = "/workspace/models/Hunyuan3D-2.1"

sys.path.insert(0, os.path.join(ROOT, "hy3dshape"))
sys.path.insert(0, os.path.join(ROOT, "hy3dpaint"))

from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
from hy3dshape.rembg import BackgroundRemover


class HunyuanGenerator:

    def __init__(self):

        self.pipeline = None
        self.remover = BackgroundRemover()

    def load(self):

        if self.pipeline is None:

            print("Carregando Hunyuan3D...")

            self.pipeline = (
                Hunyuan3DDiTFlowMatchingPipeline
                .from_pretrained("tencent/Hunyuan3D-2.1")
            )

            self.pipeline.to("cuda")

            print("Hunyuan carregado.")

    def generate(self, image_path, output_glb):

        self.load()

        image = Image.open(image_path)

        if image.mode == "RGB":
            image = self.remover(image)
        else:
            image = image.convert("RGBA")

        with torch.inference_mode():

            mesh = self.pipeline(
                image=image,
                num_inference_steps=30,
                guidance_scale=5,
                octree_resolution=256,
            )[0]

        os.makedirs(os.path.dirname(output_glb), exist_ok=True)

        mesh.export(output_glb)

        return output_glb


generator = HunyuanGenerator()
