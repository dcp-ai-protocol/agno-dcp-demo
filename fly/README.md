# Deploying the demo to Fly.io

The demo is designed to deploy to Fly.io with a persistent volume so
the audit chain survives container restarts. Total monthly cost stays
inside the free tier.

## Prerequisites

* A Fly.io account with `flyctl` installed (`brew install flyctl`).
* DNS access to add a CNAME for the demo subdomain.

## First-time setup

```bash
cd /path/to/agno-dcp-demo

# 1. Create the app (uses fly/fly.toml)
fly launch \
  --copy-config \
  --config fly/fly.toml \
  --no-deploy \
  --name agno-dcp-demo

# 2. Create the persistent volume (agent state lives here)
fly volumes create agno_dcp_data \
  --size 1 \
  --region scl

# 3. Attach a custom domain (cert auto-provisioned)
fly certs add demo.dcp-ai.org

# 4. Update DNS:
#    CNAME demo.dcp-ai.org → agno-dcp-demo.fly.dev
#    Wait ~30s for cert validation. Confirm with:
fly certs show demo.dcp-ai.org

# 5. Deploy
fly deploy --config fly/fly.toml
```

## Subsequent deploys

The CI workflow at `.github/workflows/deploy.yml` deploys on every
push to `main`. To deploy manually:

```bash
fly deploy --config fly/fly.toml --remote-only
```

## Required secrets

Only required if you switch `LLM_PROVIDER` away from `mock`:

```bash
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set OPENAI_API_KEY=sk-...
```

For CI auto-deploy, generate a Fly token and add it as a GitHub
secret named `FLY_API_TOKEN`:

```bash
fly tokens create deploy
# Copy output, then in GitHub:
# Settings → Secrets → Actions → New repository secret
# Name: FLY_API_TOKEN  Value: <token>
```

## Free-tier tuning

* `auto_stop_machines = "stop"` puts the VM to sleep after inactivity.
  First request after sleep takes ~3 s to wake; subsequent requests
  are instant.
* `min_machines_running = 0` keeps the bill at $0 when nobody is
  hitting the demo.
* `memory = "512mb"` is generous; you can drop to 256mb for tighter
  cost control.

## Volume backup

The audit chain lives in `/app/data/agent.db` on the volume. Snapshot
periodically:

```bash
fly volumes snapshots create agno_dcp_data
```

## Resetting the demo state

```bash
# Inside the running machine
fly ssh console -C "rm -f /app/data/agent.db /app/data/agent_id.txt /app/data/keys/*"
fly machines restart
```
