# Repository Guidelines

## Project Structure & Module Organization
This repository is a small, flat Python codebase rather than a package directory. Core BLE logic lives in `miband.py`, shared constants and UUID maps are in `constants.py`, and the interactive demo/CLI is `miband4_console.py`. `quick_call.py` contains a minimal example entry point. Project documentation is in `README.md`, CI is defined in `.github/workflows/python-app.yml`, and `screen/` holds image assets used by the README.

## Build, Test, and Development Commands
Use Python 3.10 locally to match CI, even though the README mentions older versions.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install flake8 pytest
python miband4_console.py -m AA:BB:CC:DD:EE:FF
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
pytest
```

`pytest` is installed in CI, but there is currently no test suite, so use it only when adding tests.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, snake_case for functions and variables, and UPPER_CASE for constants. Preserve the current module layout unless a refactor is part of the change. Keep CLI flags short and explicit, matching existing patterns such as `-m/--mac` and `-k/--authkey`. Run `flake8` before opening a PR; CI enforces syntax checks and basic complexity/line-length rules.

## Testing Guidelines
There is no dedicated `tests/` directory yet. For bug fixes or protocol changes, add focused `pytest` coverage where practical and place tests under `tests/` with names like `test_auth.py` or `test_notifications.py`. When hardware interaction cannot be automated, document the manual verification steps in the PR, including device state, auth requirements, and the command you ran.

## Commit & Pull Request Guidelines
Recent commits use short, imperative subjects such as `Add diagrams...`, `more BLE protocol examples`, and `Create python-app.yml`. Prefer concise, descriptive commit titles under roughly 72 characters. Pull requests should explain the user-visible change, call out any BLE/auth-key risks, link related issues, and include terminal output or screenshots when CLI behavior changes.

## Security & Configuration Tips
Never commit real `auth_key.txt`, `mac.txt`, or device-specific secrets. Keep personal band credentials in ignored local files only, and scrub logs/screenshots before sharing them in reviews.
