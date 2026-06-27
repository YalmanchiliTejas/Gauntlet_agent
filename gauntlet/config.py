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

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MICROVM_S3_BUCKET = os.environ.get("MICROVM_S3_BUCKET", "")
