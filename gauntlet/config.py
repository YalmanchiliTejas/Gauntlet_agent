"""Settings from the environment. No framework, just module-level reads."""
import os
import pathlib


def _private_key() -> str:
    path = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE")
    if path:
        return pathlib.Path(path).read_text()
    return os.environ.get("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")


GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY = _private_key()
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

# Shared secret the delegating backend (Fly) must present to POST /sandbox/run.
# Blank = open (dev only). Set the same value on both sides in production.
SANDBOX_INBOUND_SECRET = os.environ.get("SANDBOX_INBOUND_SECRET", "")

# API key for the read/trigger/generate endpoints (X-API-Key header).
# Blank = open (dev only). Set in production so runs/workflows aren't world-readable.
GAUNTLET_API_KEY = os.environ.get("GAUNTLET_API_KEY", "")

# Sandbox backend: "microvm" (AWS Lambda MicroVMs) or "docker" (local Docker).
# Blank = auto: docker when no MicroVM bucket is set, else microvm.
SANDBOX_BACKEND = os.environ.get("GAUNTLET_SANDBOX_BACKEND", "").strip().lower()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MICROVM_S3_BUCKET = os.environ.get("MICROVM_S3_BUCKET", "")
# Role Lambda assumes to build the image; Lambda-managed base image for the VM OS.
MICROVM_BUILD_ROLE_ARN = os.environ.get("MICROVM_BUILD_ROLE_ARN", "")
MICROVM_BASE_IMAGE_ARN = os.environ.get(
    "MICROVM_BASE_IMAGE_ARN",
    f"arn:aws:lambda:{AWS_REGION}:aws:microvm-image:al2023-1")
