from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.insights_agent import ask_portfolio, dashboard
from app.db.models import User
from app.db.session import get_db
from app.security.auth import any_user

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("")
def get_dashboard(db: Session = Depends(get_db), _: User = Depends(any_user)):
    return dashboard(db)


class AskIn(BaseModel):
    question: str


@router.post("/ask")
def ask(body: AskIn, db: Session = Depends(get_db), _: User = Depends(any_user)):
    return {"answer": ask_portfolio(db, body.question)}
