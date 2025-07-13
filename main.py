from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime
import torch, uuid, os
import trimesh

from shap_e.models.download import load_model, load_config
from shap_e.diffusion.sample import sample_latents
from shap_e.diffusion.gaussian_diffusion import diffusion_from_config
from shap_e.util.notebooks import create_pan_cameras, decode_latent_images, decode_latent_mesh


app = FastAPI()
start_time = datetime.utcnow()

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
transmitter = load_model("transmitter", device)
text_model = load_model("text300M", device)
diffusion = diffusion_from_config(load_config("diffusion"))

output_dir = "outputs"
os.makedirs(output_dir, exist_ok=True)


@app.get("/status")
def status():
    return {
        "model": "Shap-E (text300M + transmitter)",
        "uptime": str(datetime.utcnow() - start_time)
    }


@app.get("/generate3d")
def generate_3d(prompt: str = Query(..., description="Text prompt for 3D asset")):
    try:
        id = str(uuid.uuid4())[:8]

       
        latents = sample_latents(
            batch_size=1,
            model=text_model,
            diffusion=diffusion,
            guidance_scale=15.0,
            model_kwargs=dict(texts=[prompt]),
            progress=True,
            device=device,
            clip_denoised=True,
            use_fp16=True,
            use_karras=True,
            karras_steps=64,
            sigma_min=1e-3,
            sigma_max=160,
            s_churn=0,
        )

        
        mesh = decode_latent_mesh(transmitter, latents[0]).tri_mesh()

        
        ply_path = os.path.join(output_dir, f"{id}.ply")
        with open(ply_path, "wb") as f:
            mesh.write_ply(f)

      
        tmesh = trimesh.load(ply_path)
        glb_path = os.path.join(output_dir, f"{id}.glb")
        obj_path = os.path.join(output_dir, f"{id}.obj")
        tmesh.export(glb_path)
        tmesh.export(obj_path)

        return {
            "id": id,
            "prompt": prompt,
            "ply": f"/download/{id}.ply",
            "obj": f"/download/{id}.obj",
            "glb": f"/download/{id}.glb"
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(output_dir, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})
