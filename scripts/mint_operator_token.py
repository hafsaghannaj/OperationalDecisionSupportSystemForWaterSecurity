from __future__ import annotations

import argparse
from datetime import timedelta

from services.api.app.auth import create_operator_token
from services.api.app.config import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mint an ODSS-WS operator bearer token.")
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--roles", default="operator", help="Comma-separated roles, for example: operator,admin")
    parser.add_argument("--expires-hours", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if not settings.auth_token_secret:
        raise SystemExit("ODSSWS_AUTH_TOKEN_SECRET must be set before minting operator tokens.")

    token = create_operator_token(
        operator_id=args.operator_id,
        roles=[role.strip() for role in args.roles.split(",")],
        secret=settings.auth_token_secret,
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
        expires_in=timedelta(hours=args.expires_hours),
    )
    print(token)


if __name__ == "__main__":
    main()
