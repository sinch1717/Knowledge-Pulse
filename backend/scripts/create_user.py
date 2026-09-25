"""Create a user who can sign in, or reset an existing user's password.

    python scripts/create_user.py --email asha@example.com --name Asha
    python scripts/create_user.py --email asha@example.com --name Asha --organization-id org_acme

Prompts for the password unless --password is given. Users belong to one
organisation; the default is the default organisation (org_default).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import create_or_update_user  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.migrate import upgrade  # noqa: E402
from app.tenant import ORG_ID_REGEX, ensure_default_workspace  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--organization-id", default=settings.default_organization_id)
    parser.add_argument("--password", help="Omit to be prompted (keeps it out of shell history)")
    args = parser.parse_args()

    if not ORG_ID_REGEX.match(args.organization_id):
        raise SystemExit("Organisation ids are 1-64 letters, digits, underscores or hyphens.")
    password = args.password or getpass.getpass("Password: ")
    if len(password) < 8:
        raise SystemExit("Use a password of at least 8 characters.")

    upgrade()
    db = SessionLocal()
    try:
        user = create_or_update_user(db, args.email, password, args.name, args.organization_id)
        ensure_default_workspace(db, args.organization_id)
        print(f"{user.email} can sign in; organisation {user.organization_id}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
