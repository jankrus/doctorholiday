# ADR-002: Python Package and Environment Manager (uv)

- **Status:** Accepted
- **Issue:** [#11 – Backend skeleton](https://github.com/jankrus/doctorholiday/issues/11)
- **Builds on:** [ADR-001](ADR-001-tech-stack.md) (Python 3.12 + FastAPI backend)

## 1. Context
The exam brief demands a reproducible supply chain: every build of the backend image must install exactly the same dependency versions, and SCA (Trivy) and the SBOM (Syft) must see exactly what runs. ADR-001 fixes the language and the libraries but not how dependencies are declared, resolved, locked and installed. The backend therefore needs one tool that:

- produces a **lockfile** with exact versions and **hashes** for every package, including transitive ones,
- installs from that lockfile **without re-resolving**, and fails if `pyproject.toml` and lockfile disagree,
- pins the **Python version**, so developers, CI and the container all use 3.12,
- works the same way on macOS/Linux developer machines, in GitHub Actions and in the Docker build stage.

## 2. Considered Options
*   **Option A: pip + pip-tools** (`requirements.in` → `pip-compile --generate-hashes` → `requirements.txt`)
    *   *Pros:* Minimal tooling, `pip install --require-hashes` is the reference way to install hash-pinned dependencies.
    *   *Cons:* No project or virtualenv management and no Python version management; separate files per dependency group; the lockfile is resolved for one platform only. Several manual steps that developers can get wrong.
*   **Option B: Poetry**
    *   *Pros:* Established, `poetry.lock` with hashes, dependency groups.
    *   *Cons:* Slow resolver, own non-standard `[tool.poetry]` metadata (older versions), does not manage Python versions. Exporting hashed requirements needs a plugin.
*   **Option C: uv** (Astral)
    *   *Pros:* One static binary for Python version, virtualenv, dependency resolution and lockfile. Standard `pyproject.toml` (PEP 621) and dependency groups (PEP 735). `uv.lock` is cross-platform and contains hashes for every artifact. `--locked`/`--frozen` guarantee installs without re-resolving. `uv export` produces a hashed `requirements.txt` for `pip install --require-hashes`. Very fast, which keeps CI short. Supported by Dependabot (#46).
    *   *Cons:* Younger tool and an additional binary every developer has to install. `uv.lock` is uv-specific. If a scanner cannot read it, `uv export` provides a standard `requirements.txt`.

## 3. Decision Outcome
We use **uv** for the backend.

| What | Where | Rule |
| :--- | :--- | :--- |
| Direct dependencies | `backend/pyproject.toml` (`[project.dependencies]`, `[dependency-groups].dev`) | Change only with `uv add` / `uv add --dev` / `uv remove`, never by editing versions by hand. |
| Lockfile | `backend/uv.lock` | Committed. Never edited by hand. Every change to `pyproject.toml` comes with the regenerated `uv.lock` in the same commit. |
| Python version | `backend/.python-version` (`3.12`), `requires-python = ">=3.12,<3.13"` | Same minor version as the container base image (ADR-001 §3.2). |
| uv version | `[tool.uv] required-version` in `pyproject.toml` | uv refuses to run with a version outside the range, so the lockfile format and resolver behaviour are the same for everyone. CI pins the exact uv version and the `astral-sh/setup-uv` action by commit SHA (#31). |
| Installs in Make/CI | `uv sync --locked`, `uv run --locked …` | `--locked` fails if `uv.lock` is out of date instead of silently updating it. |
| Container build (#28) | Build stage: `uv export --frozen --no-dev --no-emit-project --format requirements-txt` → `pip install --require-hashes --only-binary :all:`, or `uv sync --frozen --no-dev` with `UV_PYTHON_DOWNLOADS=never` | The runtime stage contains only the installed packages and the app, not uv. Inside the image the interpreter comes from the pinned base image, never from a uv download. |
| Dependency updates | Dependabot/Renovate (#46) | Update PRs change `pyproject.toml` and `uv.lock` together and run the full pipeline. |

Developer workflow and commands: [`backend/README.md`](../../../backend/README.md).

## 4. Consequences
*   **Security (Pros):** Every installed artifact is pinned by version **and** hash. A tampered or replaced package on PyPI fails the install instead of entering the image. Builds are reproducible because nothing is resolved at build time. A single lockfile is the source for SCA, the SBOM and the image.
*   **Development (Pros):** One command (`uv sync`) creates a correct environment including Python 3.12, also on machines that only have a different Python installed.
*   **Development (Cons):** Every developer has to install uv (see `backend/README.md`). Developers who are used to `pip install -r requirements.txt` have to switch to `uv add`/`uv sync`. Running `uv lock --upgrade` without review can pull in many updates at once; updates go through PRs only.
