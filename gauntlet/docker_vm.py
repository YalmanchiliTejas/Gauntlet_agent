"""Local Docker backend — drop-in for microvm.py (same 4 functions), no AWS.

Builds the repo into an image with `docker build` and runs it publishing the
harness port on localhost; the runner then polls the same /result + /trajectory
endpoints it uses for MicroVMs. Egress still flows through the host egress proxy
— the container reaches it via host.docker.internal (we rewrite the proxy env,
which the sandbox sets to 127.0.0.1 on the host).

ponytail: shared-kernel isolation (a container), not a real VM. Fine for
dev/CI/self-hosted runs of code you trust. For hostile code, run these under
gVisor (`--runtime=runsc`) or use MicroVMs. Known ceiling, upgrade path named.

    python -m gauntlet.docker_vm   # self-check (no Docker required)
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx

_HARNESS = Path(__file__).resolve().parent.parent / "sandbox" / "harness.py"
_CA_VM_PATH = "/gauntlet_ca.pem"  # matches microvm._CA_VM_PATH / orchestrator env
_CA_COPY = (
    f"COPY .gauntlet_ca.pem {_CA_VM_PATH}\n"
    f"RUN cp {_CA_VM_PATH} /usr/local/share/ca-certificates/gauntlet.crt 2>/dev/null "
    "&& update-ca-certificates 2>/dev/null || true\n"
)


# container_id -> image tag, so terminate() can delete the throwaway run image.
_images: dict[str, str] = {}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _proxy_rewrite(env: dict | None) -> dict:
    """The sandbox sets HTTP(S)_PROXY to 127.0.0.1 on the host; from inside a
    container that's the container's own loopback. Point it at the host instead."""
    out = {}
    for k, v in (env or {}).items():
        if isinstance(v, str) and k in ("HTTP_PROXY", "HTTPS_PROXY"):
            v = v.replace("127.0.0.1", "host.docker.internal").replace("localhost", "host.docker.internal")
        out[k] = v
    return out


def upload_bundle(root: Path, dockerfile: str, ca_pem: bytes | None = None,
                  env: dict | None = None) -> str:
    """Assemble a Docker build context: the repo + harness + CA + baked env.
    Returns the context dir path (the 'key' build_image consumes)."""
    if ca_pem is not None:
        dockerfile += _CA_COPY
    for k, v in _proxy_rewrite(env).items():
        dockerfile += f"ENV {k}={json.dumps(v)}\n"
    ctx = Path.cwd() / f".gauntlet-build-{uuid.uuid4().hex}"
    # copy the checkout, then drop in the files the Dockerfile COPYs.
    shutil.copytree(root, ctx, ignore=shutil.ignore_patterns(".git"))
    (ctx / "Dockerfile").write_text(dockerfile)
    (ctx / ".gauntlet_harness.py").write_text(_HARNESS.read_text())
    if ca_pem is not None:
        (ctx / ".gauntlet_ca.pem").write_bytes(ca_pem)
    return str(ctx)


def build_image(key: str, name: str) -> str:
    """`docker build` the context; return the image tag. Deletes the context after."""
    tag = f"gauntlet-run/{name.lower()}:{uuid.uuid4().hex[:12]}"
    try:
        subprocess.run(["docker", "build", "-t", tag, key], check=True,
                       capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"docker build failed:\n{e.stderr[-2000:]}") from e
    finally:
        shutil.rmtree(key, ignore_errors=True)
    return tag


def run(image_id: str) -> tuple[str, str, str]:
    """Run the container, publish the harness port on localhost, wait for /health.
    Returns (container_id, http_endpoint, token). Token is unused locally (the
    harness has no auth; MicroVMs gate it at the network layer) but kept for
    interface parity."""
    port = _free_port()
    try:
        cid = subprocess.run(
            ["docker", "run", "-d", "--rm",
             "--add-host=host.docker.internal:host-gateway",
             "-p", f"127.0.0.1:{port}:8080", image_id],
            check=True, capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"docker run failed:\n{e.stderr[-2000:]}") from e
    _images[cid] = image_id
    endpoint = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(f"{endpoint}/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    return cid, endpoint, "local"


def terminate(microvm_id: str) -> None:
    # --rm cleans the container; also delete the throwaway run image (its top
    # layers). Shared base layers stay in the cache, so the next build is fast.
    subprocess.run(["docker", "rm", "-f", microvm_id], capture_output=True)
    tag = _images.pop(microvm_id, None)
    if tag:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)


def _demo() -> None:
    import tempfile
    assert _proxy_rewrite({"HTTPS_PROXY": "http://127.0.0.1:9000", "FOO": "127.0.0.1"}) == \
        {"HTTPS_PROXY": "http://host.docker.internal:9000", "FOO": "127.0.0.1"}, "proxy rewrite"
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "repo"
        root.mkdir()
        (root / "app.py").write_text("print('hi')\n")
        ctx = upload_bundle(root, "FROM python:3.12-slim\n",
                            ca_pem=b"CA", env={"HTTPS_PROXY": "http://127.0.0.1:9000"})
        df = (Path(ctx) / "Dockerfile").read_text()
        assert "host.docker.internal:9000" in df, df           # env rewritten + baked
        assert _CA_VM_PATH in df, df                            # CA copied
        assert (Path(ctx) / ".gauntlet_harness.py").is_file()   # harness present
        assert (Path(ctx) / "app.py").is_file()                 # repo copied
        assert (Path(ctx) / ".gauntlet_ca.pem").read_bytes() == b"CA"
        shutil.rmtree(ctx, ignore_errors=True)
    print("ok")


if __name__ == "__main__":
    _demo()
