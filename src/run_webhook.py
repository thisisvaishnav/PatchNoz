"""
PatchNoz Webhook Receiver -- CLI entry point

Runs an HTTP server that accepts real SigNoz alert webhooks as an
alternate entry point into the investigation pipeline -- instead of only
the `--scenario` simulated alert in run_patchnoz.py, or the periodic sweep
in run_scanner.py.

Usage:
    python src/run_webhook.py
    python src/run_webhook.py --host 0.0.0.0 --port 8787

Point a SigNoz "Webhook" notification channel at:
    http://<this-host>:<port>/webhook/signoz

Environment variables:
    PATCHNOZ_WEBHOOK_HOST       Default: 0.0.0.0
    PATCHNOZ_WEBHOOK_PORT       Default: 8787
    PATCHNOZ_WEBHOOK_TOKEN      Optional shared secret. If set, requests must
                                include it via the X-PatchNoz-Webhook-Token
                                header or a ?token= query parameter.
    (plus all the usual GEMINI_API_KEY / SIGNOZ_* / SLACK_* / GITHUB_* vars
    used by the investigation + action pipeline -- see .env.example.)
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.env import load_env

load_env()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PatchNoz: HTTP receiver for real SigNoz alert webhooks."
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host (default: PATCHNOZ_WEBHOOK_HOST env var, or 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: PATCHNOZ_WEBHOOK_PORT env var, or 8787).",
    )
    args = parser.parse_args()

    host = args.host or os.getenv("PATCHNOZ_WEBHOOK_HOST", "0.0.0.0")
    port = args.port or int(os.getenv("PATCHNOZ_WEBHOOK_PORT", "8787"))

    if not os.getenv("PATCHNOZ_WEBHOOK_TOKEN"):
        print(
            "[run_webhook] WARNING: PATCHNOZ_WEBHOOK_TOKEN is not set -- "
            "/webhook/signoz will accept unauthenticated requests. Set it "
            "(and send it as a custom header from SigNoz's Webhook channel "
            "config) before exposing this endpoint outside a trusted network."
        )

    print("=" * 60)
    print("PatchNoz — SigNoz alert webhook receiver")
    print(f"Listening on:      http://{host}:{port}")
    print(f"Webhook endpoint:  http://{host}:{port}/webhook/signoz")
    print(f"Health check:      http://{host}:{port}/healthz")
    print("=" * 60)

    import uvicorn
    from src.webhook_server import app

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
