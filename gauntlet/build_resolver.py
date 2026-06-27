"""Decide how to build & run a checked-out repo, in priority order:

  1. A Dockerfile the customer declared (root or .devcontainer/Dockerfile).
  2. A declarative config: .gauntlet.json {runtime, install, run, twins, modes}.
  3. Heuristic detection (requirements.txt, package.json, go.mod) as a fallback.

Returns a Plan: the image always ends by running the harness (sandbox/harness.py)
wrapped around the run command, so the runner can poll the result. `twins`/`modes`
declare which third-party APIs the run is allowed to reach (everything else is
denied by the egress proxy).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

_RUNTIMES = {"python": "python:3.12-slim", "node": "node:20-slim", "go": "golang:1.22"}

# Harness is stdlib python3; debian-based non-python images need it installed.
_APT_PYTHON = "RUN apt-get update && apt-get install -y python3 && rm -rf /var/lib/apt/lists/*\n"


@dataclass
class Plan:
    dockerfile: str
    run: str
    twins: dict = field(default_factory=dict)   # {service: version}
    modes: dict = field(default_factory=dict)   # {service: twin|live|record}


def _synth(base: str, install: str) -> str:
    lines = [f"FROM {base}", "WORKDIR /app", "COPY . ."]
    if install:
        lines.append(f"RUN {install}")
    return "\n".join(lines) + "\n"


def _wrap(run: str) -> str:
    # Override CMD with the harness; it runs `run`, captures it, serves /result.
    return ("COPY .gauntlet_harness.py /harness.py\n"
            f"ENV HARNESS_CMD={json.dumps(run)}\n"
            "EXPOSE 8080\n"
            'CMD ["python3", "/harness.py"]\n')


def _base(root: Path, spec: dict | None):
    """Returns (dockerfile_without_cmd, default_run, base_has_python)."""
    for c in (root / "Dockerfile", root / ".devcontainer" / "Dockerfile"):
        if c.is_file():
            # ponytail: assume their base has python3 for the harness. If not,
            # they must declare `run` differently / add python3. Known ceiling.
            return c.read_text().rstrip() + "\n", "pytest -q", True
    if spec is not None:
        rt = spec.get("runtime", "")
        return _synth(_RUNTIMES.get(rt, rt or "ubuntu:24.04"), spec.get("install", "")), \
            spec.get("run", "echo no run command"), rt == "python"
    if (root / "requirements.txt").is_file():
        return _synth(_RUNTIMES["python"], "pip install -r requirements.txt"), "pytest -q", True
    if (root / "pyproject.toml").is_file():
        return _synth(_RUNTIMES["python"], "pip install ."), "pytest -q", True
    if (root / "package.json").is_file():
        return _synth(_RUNTIMES["node"], "npm ci || npm install"), "npm test", False
    if (root / "go.mod").is_file():
        return _synth(_RUNTIMES["go"], "go build ./..."), "go test ./...", False
    raise ValueError("Could not resolve how to build this repo. Add a Dockerfile "
                     "or a .gauntlet.json {runtime, install, run}.")


def resolve(root: Path) -> Plan:
    spec = None
    cfg = root / ".gauntlet.json"
    if cfg.is_file():
        spec = json.loads(cfg.read_text())

    base, default_run, has_python = _base(root, spec)
    run = (spec or {}).get("run", default_run)
    dockerfile = base + ("" if has_python else _APT_PYTHON) + _wrap(run)
    return Plan(dockerfile, run,
                twins=(spec or {}).get("twins", {}),
                modes=(spec or {}).get("modes", {}))


def _demo():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)

        # Declared Dockerfile + config twins/run.
        (root / "Dockerfile").write_text("FROM python:3.12-slim\n")
        (root / ".gauntlet.json").write_text(json.dumps(
            {"run": "pytest -q", "twins": {"stripe": "2022-11-15"}, "modes": {"stripe": "twin"}}))
        p = resolve(root)
        assert p.run == "pytest -q" and p.twins == {"stripe": "2022-11-15"}
        assert 'CMD ["python3", "/harness.py"]' in p.dockerfile
        assert 'ENV HARNESS_CMD="pytest -q"' in p.dockerfile

        (root / "Dockerfile").unlink()
        (root / ".gauntlet.json").unlink()
        # Heuristic node -> needs python3 installed for the harness.
        (root / "package.json").write_text("{}")
        p = resolve(root)
        assert p.run == "npm test" and _APT_PYTHON in p.dockerfile and not p.twins

        (root / "package.json").unlink()
        try:
            resolve(root)
            assert False, "expected failure"
        except ValueError:
            pass
    print("ok")


if __name__ == "__main__":
    _demo()
