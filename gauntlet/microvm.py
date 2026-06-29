"""Package source + Dockerfile, then drive the Lambda MicroVMs lifecycle.

Flow (per the MicroVMs guide):
  zip(source + Dockerfile + harness + CA) -> S3
  -> create_microvm_image (Lambda runs the Dockerfile, snapshots; CREATING->CREATED)
  -> run_microvm (launch; PENDING->RUNNING) -> create_microvm_auth_token
  -> ... poll the harness over the endpoint ... -> terminate_microvm

Clients are created lazily so importing this module never requires the
`lambda-microvms` service to exist (keeps the webhook path alive before AWS is
set up; a real run then fails loudly and is reported on the check).

ponytail: member casing follows the docs' camelCase response fields; confirm
against your boto3 with
  c.meta.service_model.operation_model("RunMicrovm").input_shape.members.keys()
"""
import io
import json
import time
import uuid
import zipfile
from pathlib import Path

import boto3

from . import config

_clients: dict = {}


def _client(service: str):
    if service not in _clients:
        _clients[service] = boto3.client(service, region_name=config.AWS_REGION)
    return _clients[service]


_HARNESS = Path(__file__).resolve().parent.parent / "sandbox" / "harness.py"
_CA_VM_PATH = "/gauntlet_ca.pem"
# Just place + system-trust the CA; the per-process CA env vars come via `env`.
_CA_COPY = (
    f"COPY .gauntlet_ca.pem {_CA_VM_PATH}\n"
    f"RUN cp {_CA_VM_PATH} /usr/local/share/ca-certificates/gauntlet.crt 2>/dev/null "
    "&& update-ca-certificates 2>/dev/null || true\n"
)

_IDLE_POLICY = {"autoResumeEnabled": True, "maxIdleDurationSeconds": 900,
                "suspendedDurationSeconds": 300}


def _connector(kind: str) -> str:
    return f"arn:aws:lambda:{config.AWS_REGION}:aws:network-connector:aws-network-connector:{kind}"


def _zip_with_dockerfile(root: Path, dockerfile: str, ca_pem: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    skip = {"Dockerfile", ".gauntlet_harness.py", ".gauntlet_ca.pem"}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Dockerfile", dockerfile)
        z.writestr(".gauntlet_harness.py", _HARNESS.read_text())  # the Dockerfile COPYs this
        if ca_pem is not None:
            z.writestr(".gauntlet_ca.pem", ca_pem)
        for p in root.rglob("*"):
            if p.is_file() and p.name not in skip:
                z.write(p, p.relative_to(root).as_posix())
    return buf.getvalue()


def upload_bundle(root: Path, dockerfile: str, ca_pem: bytes | None = None,
                  env: dict | None = None) -> str:
    """Zip and upload; return the S3 key. Bakes the proxy CA + env (HTTPS_PROXY,
    CA bundle vars) into the image, since run_microvm has no runtime-env param and
    each run builds a fresh image anyway."""
    if ca_pem is not None:
        dockerfile += _CA_COPY
    if env:
        dockerfile += "".join(f"ENV {k}={json.dumps(v)}\n" for k, v in env.items())
    key = f"microvm-builds/{uuid.uuid4().hex}.zip"
    _client("s3").put_object(Bucket=config.MICROVM_S3_BUCKET, Key=key,
                             Body=_zip_with_dockerfile(root, dockerfile, ca_pem))
    return key


def build_image(key: str, name: str) -> str:
    """Create a MicroVM image from the bundle; wait for CREATED. Returns the image id."""
    mvm = _client("lambda-microvms")
    mvm.create_microvm_image(
        name=name,
        codeArtifact={"uri": f"s3://{config.MICROVM_S3_BUCKET}/{key}"},
        baseImageArn=config.MICROVM_BASE_IMAGE_ARN,
        buildRoleArn=config.MICROVM_BUILD_ROLE_ARN,
    )
    for _ in range(120):
        img = mvm.get_microvm_image(imageIdentifier=name)
        if img["state"] == "CREATED":
            return name
        if img["state"] == "CREATE_FAILED":
            raise RuntimeError(f"image build failed: {img.get('stateReason', img)}")
        time.sleep(5)
    raise TimeoutError("MicroVM image build timed out")


def run(image_id: str) -> tuple[str, str, str]:
    """Launch a MicroVM, wait for RUNNING, mint an auth token.
    Returns (microvm_id, https_endpoint, auth_token)."""
    mvm = _client("lambda-microvms")
    resp = mvm.run_microvm(
        imageIdentifier=image_id,
        ingressNetworkConnectors=[_connector("ALL_INGRESS")],
        egressNetworkConnectors=[_connector("INTERNET_EGRESS")],
        idlePolicy=_IDLE_POLICY,
    )
    microvm_id = resp["microvmId"]
    for _ in range(120):
        st = mvm.get_microvm(microvmIdentifier=microvm_id)["state"]
        if st == "RUNNING":
            break
        if st in ("FAILED", "TERMINATED"):
            raise RuntimeError(f"microvm entered {st}")
        time.sleep(3)
    token = mvm.create_microvm_auth_token(
        microvmIdentifier=microvm_id, expirationInMinutes=30,
        allowedPorts=[{"allPorts": {}}])["authToken"]
    return microvm_id, "https://" + resp["endpoint"], token


def terminate(microvm_id: str) -> None:
    _client("lambda-microvms").terminate_microvm(microvmIdentifier=microvm_id)
