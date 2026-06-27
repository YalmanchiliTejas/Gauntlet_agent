"""Package source + Dockerfile, then drive the Lambda MicroVM lifecycle.

Flow (per the MicroVMs guide):
  zip(source + Dockerfile) -> S3
  -> create_microvm_image (Lambda runs the Dockerfile, snapshots it)
  -> run_microvm (launch from snapshot, get an HTTPS endpoint)
  -> ... use it ...
  -> terminate_microvm

ponytail: the exact boto3 operation names / param shapes for MicroVMs are new
and may differ from your installed botocore. They are isolated in the three
calls below — if boto3 errors with "object has no attribute", fix them here
against `aws lambda help` for your SDK version. Everything else is stable.
"""
import io
import time
import uuid
import zipfile
from pathlib import Path

import boto3

from . import config

_s3 = boto3.client("s3", region_name=config.AWS_REGION)
_lambda = boto3.client("lambda", region_name=config.AWS_REGION)


_HARNESS = Path(__file__).resolve().parent.parent / "sandbox" / "harness.py"


def _zip_with_dockerfile(root: Path, dockerfile: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Dockerfile", dockerfile)
        z.writestr(".gauntlet_harness.py", _HARNESS.read_text())  # the Dockerfile COPYs this
        for p in root.rglob("*"):
            if p.is_file() and p.name not in ("Dockerfile", ".gauntlet_harness.py"):
                z.write(p, p.relative_to(root).as_posix())
    return buf.getvalue()


def upload_bundle(root: Path, dockerfile: str) -> str:
    """Zip and upload; return the S3 key."""
    key = f"microvm-builds/{uuid.uuid4().hex}.zip"
    _s3.put_object(Bucket=config.MICROVM_S3_BUCKET, Key=key,
                   Body=_zip_with_dockerfile(root, dockerfile))
    return key


def build_image(key: str, name: str) -> str:
    """Create a MicroVM image from the bundle and wait until it's ready."""
    resp = _lambda.create_microvm_image(
        Name=name,
        Code={"S3Bucket": config.MICROVM_S3_BUCKET, "S3Key": key},
    )
    image_id = resp["ImageId"]
    # Poll until the Dockerfile build + snapshot finishes.
    for _ in range(60):
        img = _lambda.get_microvm_image(ImageId=image_id)
        state = img["State"]
        if state == "Active":
            return image_id
        if state == "Failed":
            raise RuntimeError(f"image build failed: {img.get('StateReason')}")
        time.sleep(5)
    raise TimeoutError("MicroVM image build timed out")


def run(image_id: str, env: dict | None = None) -> tuple[str, str]:
    """Launch a MicroVM from the image. Returns (microvm_id, https_endpoint).

    `env` is injected into the VM so all egress goes through the sandbox proxy
    (HTTPS_PROXY + CA). ponytail: exact param name is best-effort vs the live SDK.
    """
    kwargs = {"ImageId": image_id}
    if env:
        kwargs["Environment"] = {"Variables": env}
    resp = _lambda.run_microvm(**kwargs)
    return resp["MicroVmId"], resp["Endpoint"]


def terminate(microvm_id: str) -> None:
    _lambda.terminate_microvm(MicroVmId=microvm_id)
