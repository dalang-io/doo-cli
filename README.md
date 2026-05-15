# doo-cli

Command-line interface for the Odoo PaaS platform. Manage instances, tail logs, and check metrics from your terminal or CI/CD pipeline.

## Installation

### GitHub Release Artifact

Download the latest release asset from the repository Releases page. The release includes:

- a wheel: `doo_cli-<version>-py3-none-any.whl`
- a source archive: `doo_cli-<version>.tar.gz`

Install from the downloaded wheel:

```bash
pip install ./doo_cli-1.0.0-py3-none-any.whl
```

Or install directly from a release URL:

```bash
pip install https://github.com/your-org/doo-cli/releases/download/v1.0.0/doo_cli-1.0.0-py3-none-any.whl
```

### pip

```bash
pip install doo-cli
```

### GitHub Actions

Use the repository action when you want `doo-cli` available inside a workflow job:

```yaml
- name: Install doo-cli
  uses: your-org/doo-cli@v1
```

The installed CLI version matches the Git ref you pin in `uses:`. For example, `@v1` installs the code from that action tag or branch.

For CI or other non-interactive automation, you can pass an API key override so later `run:` steps can call `doo-cli` without running `doo-cli auth login`:

```yaml
- name: Install doo-cli
  uses: your-org/doo-cli@v1
  with:
    python-version: "3.12"
    api-key: ${{ secrets.ODOO_PAAS_API_KEY }}
    api-url: https://app.odoo.dalang.io

- name: List instances
  run: doo-cli instances list
```

Supported action inputs:

| Input | Default | Description |
|------|---------|-------------|
| `python-version` | `3.12` | Python runtime used during installation |
| `api-key` | empty | Optional CI-only API key override for later workflow steps |
| `api-url` | empty | Optional API URL override for non-default environments |

The repository also publishes release artifacts automatically whenever a Git tag such as `v1.0.0` is pushed.

### From source

```bash
git clone <repo>
cd doo-cli
pip install -e .
```

## Quick Start

```bash
# Log in with your account
doo-cli auth login

# List your instances
doo-cli instances list

# Create a staging instance
doo-cli instances create \
  --name my-staging \
  --odoo-version 17.0 \
  --edition community \
  --postgres-version 17 \
  --environment staging \
  --wait

# Tail logs
doo-cli logs tail --instance my-staging

# Check metrics
doo-cli metrics snapshot --instance my-staging
```

## Authentication

The CLI uses `https://app.odoo.dalang.io` by default.

| Method | Priority |
|--------|----------|
| `ODOO_PAAS_API_KEY` env var | Highest |
| Stored local config | Lowest |

```bash
# Interactive login (prompts for email/password and stores a generated API key)
doo-cli auth login

# Non-interactive user login
doo-cli auth login --email you@example.com --password "$PASSWORD"

# Import an existing API key
doo-cli auth login --api-key "$MY_KEY"

# Check auth status
doo-cli auth status
```

## Command Reference

### Global Flags

Every command accepts these flags:

| Flag | Short | Description |
|------|-------|-------------|
| `--output FORMAT` | `-o` | `table` (default), `json`, `yaml` |
| `--api-url URL` | | Override the default API base URL |
| `--quiet` | `-q` | Suppress non-essential output |
| `--verbose` | `-v` | Emit debug info to stderr |
| `--no-color` | | Disable color output |
| `--version` | | Print version and exit |

### Instances

```bash
# List all instances
doo-cli instances list
doo-cli instances list --status running
doo-cli instances list --environment staging
doo-cli instances list --output json

# Get instance detail
doo-cli instances get --name my-prod
doo-cli instances get --name my-prod --output json

# Create instance
doo-cli instances create \
  --name my-staging \
  --odoo-version 17.0 \
  --edition community \
  --postgres-version 17 \
  --environment staging \
  [--install-type docker|system] \
  [--github-repository org/repo] \
  [--github-repository-clone-url URL] \
  [--size small|medium|large] \
  [--topology single|split] \
  [--app-size SIZE] \
  [--app-vm-count 1-5] \
  [--db-size SIZE] \
  [--region REGION] \
  [--wait] \
  [--timeout SECS]

# Start / stop
doo-cli instances start --name my-staging [--wait]
doo-cli instances stop  --name my-staging [--confirm] [--wait]

# Delete
doo-cli instances delete --name my-staging [--confirm] [--wait]
```

### Logs

```bash
# Tail live logs (polls every 2s, Ctrl+C to stop)
doo-cli logs tail --instance my-prod
doo-cli logs tail --instance my-prod --service odoo
doo-cli logs tail --instance my-prod --level error
doo-cli logs tail --instance my-prod --output json

# Query historical logs
doo-cli logs query --instance my-prod --since 1h
doo-cli logs query --instance my-prod --since 2026-04-12T00:00:00Z --until 2026-04-12T06:00:00Z
doo-cli logs query --instance my-prod --level error --since 24h --output json
doo-cli logs query --instance my-prod --grep "ValueError" --since 2h
```

`--since` accepts:
- Duration shorthand: `30m`, `1h`, `7d`
- ISO 8601: `2026-04-12T00:00:00Z`

### Metrics

```bash
# Point-in-time snapshot
doo-cli metrics snapshot --instance my-prod
doo-cli metrics snapshot --instance my-prod --metric cpu
doo-cli metrics snapshot --instance my-prod --output json

# Refreshing watch (Ctrl+C to stop)
doo-cli metrics watch --instance my-prod --interval 5s
```

### Config

```bash
# Show current config (API keys are masked)
doo-cli config show

# Set values
doo-cli config set api-url https://app.odoo.dalang.io
doo-cli config set default-instance my-prod
doo-cli config set default-output json

# Remove a value
doo-cli config unset default-instance
```

## CI/CD Usage

The CLI is safe for non-interactive environments. In CI:

1. Set `ODOO_PAAS_API_KEY`
2. Use `--confirm` for destructive operations (stop, delete)
3. Use `--output json` and `--quiet` for machine-readable output

```yaml
# GitHub Actions example
- name: Install doo-cli
  uses: your-org/doo-cli@v1
  with:
    api-key: ${{ secrets.ODOO_PAAS_API_KEY }}
    api-url: https://app.odoo.dalang.io

- name: Provision staging instance
  run: |
    doo-cli instances create \
      --name pr-${{ github.event.pull_request.number }} \
      --odoo-version 17.0 \
      --edition community \
      --postgres-version 17 \
      --environment staging \
      --wait \
      --output json > instance.json

- name: Delete staging on PR close
  if: github.event.action == 'closed'
  run: |
    doo-cli instances delete \
      --name pr-${{ github.event.pull_request.number }} \
      --confirm \
      --wait
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid command usage or missing arguments |
| 3 | Authentication error |
| 4 | Resource not found |
| 5 | Operation timeout (`--wait`) |
| 6 | API rate limit exceeded |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ODOO_PAAS_API_KEY` | API key override for CI or non-interactive automation |
| `ODOO_PAAS_API_URL` | Override the default API base URL |
| `NO_COLOR` | Disable color output (https://no-color.org/) |

## Config File

Location: `~/.config/doo-cli/config.yaml` (permissions `0600`)

```yaml
version: 1
api_key: your-api-key-here
api_url: https://app.odoo.dalang.io
default_instance: my-prod
default_output: table
```
