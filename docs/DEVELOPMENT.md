# Linux development baseline

The fork targets Python 3.12, a Python backend/training engine and a TypeScript
frontend, with Docker and Linux AppImage delivery. No Rust is in scope.

## Dependency profiles

| File | Purpose |
|---|---|
| `requirements-server.txt` | FastAPI/scientific runtime and PNG report support; no desktop GUI. |
| `requirements-dev.txt` | Server plus pytest tools, independent FIT decoder and mocked desktop bridge tests; no Qt engine. |
| `requirements.txt` | Existing desktop entrypoint, including server requirements and platform-specific GUI dependencies. |
| `requirements-linux-py312.lock` | Exact direct/transitive versions for these profiles on Linux with Python 3.12. |

The lock is a constraint file: install the profile you need **with** the lock;
installing the entire lock would also install the desktop engine. It does not
claim reproducibility on Windows/macOS or lock native OS/build toolchains.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt -c requirements-linux-py312.lock
.venv/bin/python -m pytest tests/test_hermetic_home.py tests/test_gate_script.py -q
GATE_PYTHON="$PWD/.venv/bin/python" bash tools/gate.sh "$PWD" linux-baseline
```

A Debian-derived system without `ensurepip` needs its Python venv package
installed by the system administrator. Alternatively, create a venv using
`python3.12 -m venv --without-pip .venv`, then use an already installed pip:
`python3.12 -m pip --python .venv/bin/python install -r requirements-dev.txt -c requirements-linux-py312.lock`.
Do not install project packages into the system interpreter.

For a headless server, substitute `requirements-server.txt`. The clean server
profile was smoke-tested on Linux: Uvicorn startup, HTTP health and setup page,
and SIGTERM exit, without PySide6 or pywebview installed. This is not a Docker
or AppImage certification. Use disposable data and blank/mock external-service
credentials during verification; never point tests at your rider data.

To refresh the Linux lock deliberately, run from a Linux Python 3.12 environment:

```sh
python -m pip install pip-tools
python -m piptools compile requirements.txt requirements-dev.txt \
  --output-file requirements-linux-py312.lock \
  --no-emit-index-url --no-emit-trusted-host --strip-extras
```

Existing pins are retained unless an upgrade is requested. Review dependency
changes and run the relevant behavior checks/full gate before accepting them.
The lock pins versions, not artifact hashes; supply-chain/build hardening is a
separate release concern.

## Verification

See [tests/README.md](../tests/README.md) for isolation and gate semantics.
The full gate preserves failures and writes logs/status under
`/tmp/shepherd-gate`; a passing diagnostic rerun cannot turn it green.
The historical list is not a failure allow-list.

Pull requests run `.github/workflows/tests.yml` on GitHub-hosted runners: the
same gate on `ubuntu-latest` with the locked headless profile, and a `web` job
(`pnpm typecheck`, `lint`, `test`, `build`), and a browser smoke job. macOS and
Windows testing are retired: Linux (the Docker image and the AppImage are the
shipped artifacts) is the only supported target.

`.forgejo/workflows/tests.yml` runs the same Linux gate for the Forgejo mirror.
Forgejo is the owner's local host and is not the release identity: no Forgejo
runner was visible to the repository account, so that copy has not been
executed. GitHub is the public home, the release channel (`PACE-1/shepherd`)
and where CI is validated.

Inventory, candidate decisions and current measurement limits are recorded in
[code-bloat/README.md](code-bloat/README.md). Product defect fixes, algorithm
changes and structural cleanup must have separate evidence and commits.

## Browser smoke tests

`web/e2e/` drives the new UI in a real Chromium against a real backend on a
throwaway data root (a temporary `HOME` and `SHEPHERD_HOME`; credentials blank,
no network flag). It covers first-run setup, the new-profile wizard, profile
switching by keyboard, deleting with the typed confirmation, keyboard navigation,
and the DFA empty and error states.

```sh
cd web && pnpm install && pnpm build && pnpm exec playwright install chromium
E2E_PYTHON=/path/to/python-with-server-requirements pnpm e2e
```

Plan generation and editing, FIT import and workout or plan export have no browser
coverage yet because those workflows have not been migrated; add their specs with
each migration (roadmap #9, #25).
