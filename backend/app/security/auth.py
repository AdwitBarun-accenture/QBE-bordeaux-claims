"""JWT auth with two roles from the mockup:
  analyst     -> full pipeline, memory, settings, connections
  underwriter -> insights & reporting only
On Azure, swap this for Microsoft Entra ID (see docs/AZURE_GUIDE.md section 9);
the role checks below stay the same - only token issuance changes."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    s = get_settings()
    payload = {"sub": user.id, "email": user.email, "role": user.role,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expiry_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, payload["sub"])
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles and user.role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
        return user
    return dep


analyst_only = require_role("analyst")
any_user = require_role("analyst", "underwriter")


def seed_demo_users(db: Session) -> None:
    demo = [
        ("analyst@lloyds.com", "J. Davis", "JD", "analyst"),
        ("underwriter@lloyds.com", "S. Patel", "SP", "underwriter"),
    ]
    for email, name, initials, role in demo:
        if not db.query(User).filter_by(email=email).first():
            db.add(User(email=email, name=name, initials=initials, role=role, password_hash=hash_password("demo")))
    db.commit()
