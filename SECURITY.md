# Security Policy

## Supported Versions

PatchNoz is a hackathon MVP without tagged/versioned releases yet — there is
a single moving target, the `main` branch. Security fixes are applied there
and to any currently open feature branch derived from it.

| Version              | Supported          |
| --------------------- | ------------------ |
| `main` (latest commit) | :white_check_mark: |
| Older commits / tags   | :x:                |

Once PatchNoz starts cutting tagged releases, this table will be updated to
track specific version ranges instead of "latest `main`".

## Reporting a Vulnerability

If you find a security issue in PatchNoz (for example: a way to leak
credentials from `.env`, exfiltrate SigNoz/Slack/GitHub tokens, bypass the
dry-run safety fallback and trigger unintended external calls, or an
injection vector through alert/evidence data flowing into the Slack/GitHub
adapters), please report it privately rather than opening a public issue:

1. **Preferred**: use GitHub's private vulnerability reporting for this repo
   — go to the [Security tab](https://github.com/thisisvaishnav/PatchNoz/security)
   → **Report a vulnerability**. This opens a private advisory visible only
   to maintainers.
2. **Alternative**: open a GitHub issue with minimal detail (e.g. "Security
   issue — details sent privately") and mention `@thisisvaishnav`, without
   including exploit details in the public issue body.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a minimal proof of concept.
- Which component is affected (e.g. `signoz_mcp_adapter.py`,
  `adapters/slack.py`, `adapters/github.py`, `run_recorder.py`, artifacts
  under `runs/`).

### What to expect

- **Acknowledgement**: within 3–5 days of the report.
- **Triage**: we'll confirm whether the report is accepted as a valid
  vulnerability or declined (e.g. not exploitable, out of scope, or already
  known/fixed), typically within 7–14 days of acknowledgement.
- **If accepted**: we'll work on a fix, credit you in the fix's commit/PR
  (unless you prefer to stay anonymous), and let you know once it has
  landed on `main`.
- **If declined**: we'll explain the reasoning (e.g. it's expected/documented
  behavior, requires local/trusted access already, etc.).

Given this is an actively evolving MVP with no dedicated security team,
response times are best-effort rather than SLA-backed.

## Project-Specific Security Notes

These are things this project already does, and that any change should
preserve:

- **No hardcoded secrets.** Every credential (`SIGNOZ_API_KEY`,
  `SIGNOZ_EMAIL`/`SIGNOZ_PASSWORD`/`SIGNOZ_ORG_ID`, `SLACK_WEBHOOK_URL`,
  `GITHUB_TOKEN`) is read from the environment or a local, gitignored
  `.env` file — never committed. See `.env.example` for the full list of
  variables (with no real values).
- **Safe-by-default external actions.** `ActionAgent` (Slack, GitHub) only
  performs a real network call when its credentials are fully configured;
  otherwise it dry-runs and records what *would* have been sent. Any change
  to `src/action_agent.py` or `src/adapters/` must preserve this fallback.
- **Least-surprise error handling.** Adapter failures (SigNoz MCP calls,
  Slack, GitHub) are caught and recorded as structured results rather than
  leaking stack traces or partial credentials into logs or saved artifacts.
- If you believe an artifact under `runs/` was generated with real
  credentials embedded in it (it shouldn't be — payloads only ever contain
  incident data, not secrets), please report that as a vulnerability too.
