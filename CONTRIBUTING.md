# Contributing

Thanks for considering a contribution.

## Ground rules

* One concern per PR.
* Tests for every change.
* No silent except blocks; use the typed exceptions in
  `agno_dcp.exceptions` or add a new one.
* Type hints on public functions; `mypy --strict` must pass.

## Local setup

```bash
git clone https://github.com/dcp-ai-protocol/agno-dcp-demo.git
cd agno-dcp-demo

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

## Running checks

```bash
ruff check .
ruff format --check .
pytest -ra
```

## Building the container

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Reporting security issues

Email `security@dcp-ai.org` rather than opening a public issue.

## Code of Conduct

Project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Be technical, kind, and direct.
