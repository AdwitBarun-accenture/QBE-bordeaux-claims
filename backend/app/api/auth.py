from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.security.auth import create_token, current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def _user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "initials": u.initials, "role": u.role}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_token(u), "user": _user(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user(user)
