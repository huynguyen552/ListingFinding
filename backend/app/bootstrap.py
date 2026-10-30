import os
import re

from sqlalchemy import select, text

from .models import User
from .security import hash_password


def bootstrap_admin(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(420201001)"))
    if db.scalar(select(User.id).limit(1)):
        return False
    username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,100}", username) or not 12 <= len(password) <= 128:
        raise RuntimeError(
            "Set INITIAL_ADMIN_USERNAME (3–100 allowed characters) and "
            "INITIAL_ADMIN_PASSWORD (12–128 characters) in Render before first deploy."
        )
    db.add(User(id=1, username=username, password_hash=hash_password(password)))
    db.commit()
    return True
