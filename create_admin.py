#!/usr/bin/env python3
"""Grant the admin role.

Run it against the same MongoDB the app uses:

    python create_admin.py grant user@example.com
    python create_admin.py list
    python create_admin.py grant user@example.com --db OTHER_DB

Deliberately not an API endpoint and not driven by an environment variable:
the first admin has to be created out of band, or registration would be a way
to hand yourself a privileged role.
"""
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone
from pymongo import MongoClient
import argparse
import sys

from services.db import MONGO_URI, DB_NAME
from services.rbac import Role

def _users(db_name: str):
    # Sync client on purpose: this is a one-shot script, not the event loop
    return MongoClient(MONGO_URI)[db_name]['USERS']

def _find_user(users, email: str, db_name: str) -> dict | None:
    user = users.find_one({"email": email}, {"roles": 1})
    if not user:
        print(f"No user with email {email!r} in database {db_name!r}.", file=sys.stderr)
    return user

def grant(email: str, db_name: str) -> int:
    users = _users(db_name)
    email = email.lower()

    user = _find_user(users, email, db_name)
    if not user:
        print("Register the account first, then grant admin.", file=sys.stderr)
        return 1

    # Checked up front so re-running the script is a no-op. Bumping
    # token_version unconditionally would sign the user out for nothing.
    if str(Role.ADMIN) in user.get("roles", []):
        print(f"{email} is already an admin.")
        return 0

    users.update_one(
        {"_id": user["_id"]},
        {
            "$addToSet": {"roles": str(Role.ADMIN)},
            "$set": {"updated_at": datetime.now(timezone.utc)},
            # Invalidates tokens issued before the promotion, so the new role
            # takes effect on next login rather than silently lagging
            "$inc": {"token_version": 1}
        }
    )

    print(f"{email} is now an admin. They must log in again for it to take effect.")
    return 0


def list_admins(db_name: str) -> int:
    admins = list(_users(db_name).find({"roles": str(Role.ADMIN)}, {"email": 1, "roles": 1}))

    if not admins:
        print(f"No admins in database {db_name!r}.")
        return 0

    print(f"Admins in {db_name!r}:")
    for user in admins:
        print(f"  {user['email']}  {user.get('roles', [])}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=DB_NAME,
                        help=f"database to act on (default: {DB_NAME})")
    sub = parser.add_subparsers(dest="command", required=True)

    grant_parser = sub.add_parser("grant", help="give a user the admin role")
    grant_parser.add_argument("email")

    sub.add_parser("list", help="show every admin")

    args = parser.parse_args()

    if args.command == "grant":
        return grant(args.email, args.db)
    return list_admins(args.db)

if __name__ == "__main__":
    sys.exit(main())
