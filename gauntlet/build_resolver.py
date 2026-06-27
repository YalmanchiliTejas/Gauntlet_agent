"""Decide how to build & run a checked-out repo, in priority order:

  1. A Dockerfile the customer declared (root or .devcontainer/Dockerfile).
  2. A small declarative config: .gauntlet.json {runtime, install, run}.
  3. Heuristic detection (requirements.txt, package.json, go.mod) as a
     bootstrap fallback only.

Returns the Dockerfile *text* to drop at the zip root. For (2) and (3) we
synthesize one so the MicroVM image build path is always "run a Dockerfile".
"""
import json
from pathlib import Path

_RUNTIMES = {
    "python": "python:3.12-slim",
    "node": "node:20-slim",
    "go": "golang:1.22",
}


def _synth(base: str, install: str, run: str) -> str:
    lines = [f"FROM {base}", "WORKDIR /app", "COPY . ."]
    if install:
        lines.append(f"RUN {install}")
    lines.append(f'CMD {run}')
    return "\n".join(lines) + "\n"


def resolve(root: Path) -> str:
    # 1. Declared Dockerfile wins — build/run exactly as the customer says.
    for candidate in (root / "Dockerfile", root / ".devcontainer" / "Dockerfile"):
        if candidate.is_file():
            return candidate.read_text()

    # 2. Declarative config.
    cfg = root / ".gauntlet.json"
    if cfg.is_file():
        spec = json.loads(cfg.read_text())
        base = _RUNTIMES.get(spec.get("runtime", ""), spec.get("runtime", "ubuntu:24.04"))
        return _synth(base, spec.get("install", ""), spec.get("run", "echo no run command"))

    # 3. Heuristic bootstrap fallback.
    if (root / "requirements.txt").is_file():
        return _synth(_RUNTIMES["python"], "pip install -r requirements.txt", '["python", "main.py"]')
    if (root / "pyproject.toml").is_file():
        return _synth(_RUNTIMES["python"], "pip install .", '["python", "-m", "app"]')
    if (root / "package.json").is_file():
        return _synth(_RUNTIMES["node"], "npm ci || npm install", '["npm", "start"]')
    if (root / "go.mod").is_file():
        return _synth(_RUNTIMES["go"], "go build ./...", '["./app"]')

    raise ValueError(
        "Could not resolve how to build this repo. Add a Dockerfile or a "
        ".gauntlet.json {runtime, install, run}."
    )


def _demo():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Dockerfile wins over everything.
        (root / "Dockerfile").write_text("FROM scratch\n")
        (root / "requirements.txt").write_text("flask\n")
        assert resolve(root) == "FROM scratch\n"

        (root / "Dockerfile").unlink()
        # config beats heuristic
        (root / ".gauntlet.json").write_text(json.dumps(
            {"runtime": "python", "install": "pip install -r requirements.txt", "run": '["pytest"]'}))
        out = resolve(root)
        assert "python:3.12-slim" in out and "pytest" in out, out

        (root / ".gauntlet.json").unlink()
        # heuristic
        assert "pip install -r requirements.txt" in resolve(root)

        (root / "requirements.txt").unlink()
        try:
            resolve(root)
            assert False, "expected failure on undetectable repo"
        except ValueError:
            pass
    print("ok")


if __name__ == "__main__":
    _demo()
