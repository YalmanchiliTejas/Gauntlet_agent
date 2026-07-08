"""Modal-hosted, OpenAI-compatible inference endpoint for the fixer's primary coder.

vLLM already ships an OpenAI-compatible server (`vllm.entrypoints.openai.api_server`), so we
don't reimplement chat/completions — we just run it on a Modal GPU and expose it. codex points
at `${MODAL_INFER_URL}` (this app's `/v1`) with wire_api="chat".

Deploy:  modal deploy deploy/modal_infer.py
Set on the fixer host:  MODAL_INFER_URL=https://<you>--gauntlet-infer-serve.modal.run/v1
                        MODAL_INFER_KEY=<the token below>   MODAL_INFER_MODEL=<MODEL>

Auth: vLLM enforces the token (--api-key); codex sends it as `Authorization: Bearer`. Store it
as a Modal secret named `modal-infer-key` (key API_KEY) instead of hardcoding.
"""
import os
import subprocess

import modal

MODEL = os.getenv("MODAL_INFER_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")
PORT = 8000

image = (
    modal.Image.debian_slim()
    .pip_install("vllm==0.6.6", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
app = modal.App("gauntlet-infer")


@app.function(
    image=image,
    gpu="A100",
    scaledown_window=300,   # keep warm 5 min after last request; then scale to zero
    timeout=1800,
    secrets=[modal.Secret.from_name("modal-infer-key")],  # provides API_KEY
)
@modal.concurrent(max_inputs=32)
@modal.web_server(PORT, startup_timeout=600)
def serve():
    subprocess.Popen([
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", MODEL,
        "--host", "0.0.0.0", "--port", str(PORT),
        "--api-key", os.environ["API_KEY"],
    ])
