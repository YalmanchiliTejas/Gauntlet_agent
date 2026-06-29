# Gauntlet sandbox runner — setup runbook

Deployed backend: **`gauntlet-api`** on Fly → `https://gauntlet-api.fly.dev`
Webhook URL: **`https://gauntlet-api.fly.dev/api/sandbox/webhook/github`**

Steps 1–4 make the webhook live + verified. Steps 5–7 enable actual runs.

---

## 1. Create the GitHub App
GitHub → **Settings → Developer settings → GitHub Apps → New GitHub App**.

- **Name / Homepage URL:** anything.
- **Webhook → Active:** ✔ · **URL:** `https://gauntlet-api.fly.dev/api/sandbox/webhook/github`
- **Webhook secret:** generate a random string (`openssl rand -hex 32`) — keep it.
- **Repository permissions:**
  - Contents → **Read-only**
  - Checks → **Read & write**
  - Pull requests → **Read & write**
- **Subscribe to events:** **Push**, **Pull request**.
- Create → note the **App ID** → **Generate a private key** (downloads a `.pem`).

## 2. Put the secrets on the prod backend
```bash
cd ~/Desktop/temp/Gauntlet
fly secrets set -a gauntlet-api \
  GITHUB_WEBHOOK_SECRET='<the webhook secret>' \
  GITHUB_APP_ID='<app id>' \
  GITHUB_APP_PRIVATE_KEY="$(cat /path/to/private-key.pem)"
```
Fly restarts the machines. The webhook now verifies signatures instead of returning 500.

## 3. Install the App + smoke-test
- In the App page → **Install App** → pick the repo(s). The `installation.id` now rides in every webhook payload (no lookup needed).
- Test without a real PR: App → **Advanced → Recent Deliveries → Redeliver** the `ping`, or open a PR.
  - `ping`/unhandled event → `{"skipped": ...}` 200
  - PR opened/synchronize → `{"queued": true}` (the run then fails at the MicroVM stage until steps 5–7 are done — that's expected).

## 4. Per-repo config (`.gauntlet.json` at repo root)
Declares how to run + which twins egress is allowed to reach (everything else is denied).
```json
{
  "run": "pytest -q",
  "twins": { "stripe": "2022-11-15", "slack": "v1" },
  "modes": { "stripe": "twin", "slack": "twin" }
}
```
No Dockerfile? the resolver synthesizes one (python/node/go heuristics). Modes: `twin` | `live` | `record`.

---

## 5. AWS (needed before any run executes)
```bash
aws s3 mb s3://gauntlet-microvm-builds
fly secrets set -a gauntlet-api \
  AWS_ACCESS_KEY_ID='<key>' \
  AWS_SECRET_ACCESS_KEY='<secret>' \
  AWS_REGION='us-east-1' \
  MICROVM_S3_BUCKET='gauntlet-microvm-builds'
```
IAM for that key needs: `s3:PutObject` on the bucket, the Lambda **MicroVM** actions
(create image / run / terminate / get image), and `iam:PassRole` for the role the
MicroVM assumes. Also confirm **Lambda MicroVMs is enabled** for your account/region
(newer feature — may need allowlisting).

## 6. Pin the boto3 MicroVM op names
The op names in `gauntlet/sandbox_runner/microvm.py` are best-effort. Pin them against
a boto3 new enough to include MicroVMs:
```bash
python -c "import boto3; c=boto3.client('lambda'); print([m for m in dir(c) if 'microvm' in m.lower()])"
# then check params:
python -c "import boto3; print(boto3.client('lambda').meta.service_model.operation_model('RunMicrovm').input_shape.members.keys())"
```
Edit `microvm.py` (`create_microvm_image` / `get_microvm_image` / `run_microvm` /
`terminate_microvm` + param keys) to match, bump the `boto3` pin in `pyproject.toml`,
redeploy.

## 7. Wire up the sandboxes  ⚠️ one architectural decision
Two pieces:

**a. mitmproxy in the image.** Add `mitmproxy` to the `[server]` extra in `pyproject.toml`
(deferred at deploy time for size/conflict reasons). Pin a version compatible with the
image's `cryptography`/`httpx`, then redeploy. Without it, `Sandbox.start()` can't launch
the proxy and runs fail.

**b. The proxy must be reachable by the MicroVM — this is the real decision.**
`Sandbox` starts the twins + proxy as subprocesses on the host running `runner`
(the Fly machine), bound to `127.0.0.1`. But the MicroVM runs on **AWS**, a different
network — it can't reach `127.0.0.1` on the Fly box. Pick one:

  1. **Co-locate the orchestrator with the VM (recommended).** Run the twins+proxy where
     the MicroVM can reach them — e.g. on the AWS side / same VPC — and set the VM's
     `HTTPS_PROXY` to that address. Cleanest isolation, matches the intended model.
  2. **Expose the Fly proxy publicly.** Bind the proxy to `0.0.0.0`, publish its port via
     a Fly `[[services]]` entry, and have `env_for_sandbox()` return the public host:port
     instead of `127.0.0.1`. Simplest to stand up; the proxy is then internet-exposed
     (lock it down).

The CA trust inside the VM is already wired (`microvm.upload_bundle` bakes the proxy CA
into the image), so once the VM can *reach* the proxy, HTTPS to the twins validates.

---

## End-to-end smoke (after 5–7)
1. Open a PR on an installed repo with a `.gauntlet.json`.
2. Webhook → `{"queued": true}` → a **gauntlet** check appears on the PR.
3. The MicroVM builds, runs `run` through the proxy (declared twins answer, undeclared
   domains get 403), and the check reports pass/fail with the command output.
