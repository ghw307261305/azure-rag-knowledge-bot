"""Create a short-lived local JWT for AUTH_MODE=local_jwt development."""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.auth_service import create_local_token  # noqa: E402
from app.services.config import get_settings, validate_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a local development JWT")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--role", choices=("user", "operator", "admin"), default="user")
    parser.add_argument("--group", action="append", default=[])
    parser.add_argument("--expires-in", type=int, default=3600)
    args = parser.parse_args()

    settings = get_settings()
    validate_settings(settings)
    if settings.auth_mode != "local_jwt":
        raise SystemExit("Set AUTH_MODE=local_jwt before creating a local token.")
    print(
        create_local_token(
            args.subject,
            role=args.role,
            groups=args.group,
            expires_in_seconds=args.expires_in,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
