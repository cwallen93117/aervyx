from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserSummary

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.scalar(select(User).where(User.username == payload.username, User.is_active.is_(True)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.username), user=UserSummary.model_validate(user))


@router.get("/me", response_model=UserSummary)
def me(user: User = Depends(get_current_user)) -> UserSummary:
    return UserSummary.model_validate(user)