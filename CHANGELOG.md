# Changelog

All notable changes to `agno-dcp-demo` are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] (2026-04-30)

Initial release of the end-to-end demo. Reads as a banking
collections workflow.

### Added

* Singleton `DemoAgentService` that boots a `DCPAgent` (tier-3,
  strict mode) at app startup, persists its `CitizenshipBundle`
  beside the audit DB, and reuses the same identity across restarts.
* Four tool mocks (`lookup_customer`, `propose_payment_plan`,
  `schedule_callback`, `send_confirmation`) with realistic banking
  fixtures.
* Declarative YAML policy with seven rules including conservative
  payment plans, discount ceilings, balance escalation thresholds,
  and channel restrictions.
* FastAPI service exposing eight HTTP routes:
  * `GET /` — single-page dashboard.
  * `POST /api/agent/run` — run an arbitrary tool through the gate.
  * `POST /api/agent/scenario` — run a pre-baked sequence.
  * `GET /api/agent/info` — agent identity + capability snapshot.
  * `GET /api/audit/entries` — paginated audit log.
  * `GET /api/audit/stream` — Server-Sent Events live feed.
  * `GET /api/audit/verify` — offline chain integrity verifier.
  * `POST /api/audit/export` — signed Compliance Bundle ZIP.
  * `POST /api/audit/reset` — wipe back to genesis (demo replay).
* Banking-grade dashboard: HTMX + Tailwind CDN, dark theme, KPI
  strip, three one-click scenarios, live audit log with
  per-event-type styling, single-click verify and export buttons.
* Multi-stage `Dockerfile` (uv builder + slim runtime, non-root
  user, healthcheck) and `docker-compose.yml` for local runs with a
  named volume.
* Fly.io configuration (`fly/fly.toml`) targeting `scl` region with
  a 1 GB persistent volume and free-tier-friendly auto-stop.
* CI workflow (Python 3.11/3.12/3.13 on Ubuntu plus a Docker build
  smoke) and an auto-deploy workflow that publishes to Fly on push
  to `main`.
* Test suite covering agent service lifecycle, policy strict-mode
  denies, chain integrity after a workload, Compliance Bundle ZIP
  export, and every HTTP route.

### Notes

* Cryptographic primitives import from `agno-dcp >= 0.1.0` and
  `dcp-ai >= 2.8.1`. Bundles produced here are byte-exact compatible
  with every DCP-AI verifier.
* No real LLM provider is required; the demo defaults to `mock` and
  the workflow is deterministic. Set `LLM_PROVIDER=anthropic` or
  `openai` plus the matching API key to swap in.
* The persistent volume layout is documented in `fly/README.md`. The
  same shape works for any host with a writable `/app/data`.

