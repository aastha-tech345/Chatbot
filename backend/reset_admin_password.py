"""Reset an existing Master Chatbot admin password without deleting app data.

Run with the backend's Python environment:
    python reset_admin_password.py --email admin@example.com
Uses the same DATABASE_URL and .env loading as the backend.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import warnings


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes (bcrypt limit).")
    if "\0" in password:
        raise ValueError("Password cannot contain null bytes.")


async def reset_password(db, email: str, password: str) -> None:
    from app.crypto import hash_password
    from app.repositories import AdminUserRepo, AdminSessionRepo, AuditLogRepo

    validate_password(password)
    users = AdminUserRepo(db)
    user = await users.get_by_email(email)
    if user is None:
        raise ValueError("Admin not found. Check the email and backend DATABASE_URL.")
    if not user.is_active:
        raise ValueError("Admin is inactive. Reactivate the account separately before resetting its password.")
    await users.update_password_hash(user.id, hash_password(password))
    await AdminSessionRepo(db).revoke_all_for_user(user.id)
    await AuditLogRepo(db).record(action="admin_password_reset", admin_user_id=user.id)
    await db.commit()


async def run(email: str, password: str) -> None:
    from app.database import AsyncSessionLocal, engine

    try:
        async with AsyncSessionLocal() as db:
            await reset_password(db, email, password)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Existing admin email; prompted if omitted")
    args = parser.parse_args()
    try:
        email = (args.email or input("Admin email: ")).strip()
        if not email:
            raise ValueError("Admin email is required.")
        # Fail rather than echo a password if the terminal cannot hide input.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("New password: ")
            validate_password(password)
            if password != getpass.getpass("Confirm new password: "):
                raise ValueError("Passwords do not match.")
        asyncio.run(run(email, password))
    except (ValueError, getpass.GetPassWarning) as exc:
        print(f"Reset failed: {exc}")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nReset cancelled.")
        return 1
    except Exception:
        print("Reset failed. Check database availability and the backend environment.")
        return 1
    print("Admin password reset. Sign in with your new password.")
    print("Refresh sessions revoked. Existing access tokens remain valid until expiry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
