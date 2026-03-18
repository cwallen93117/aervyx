from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_session
from app.deps import get_current_user
from app.models import Pilot, User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserSummary

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.scalar(select(User).where(User.username == payload.username, User.is_active.is_(True)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.username), user=UserSummary.model_validate(user))


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    email = payload.email.strip().lower()
    if session.scalar(select(User).where(User.username == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists")

    pilot = session.scalar(select(Pilot).where(func.lower(Pilot.email) == email))
    if pilot is None:
        pilot = Pilot(
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=email,
            nation=payload.nation,
            competition_number=payload.competition_number,
            civl_id=payload.civl_id,
        )
        session.add(pilot)
        session.flush()
    else:
        pilot.first_name = payload.first_name.strip() or pilot.first_name
        pilot.last_name = payload.last_name.strip() or pilot.last_name
        pilot.email = email
        pilot.nation = payload.nation or pilot.nation
        pilot.competition_number = payload.competition_number or pilot.competition_number
        pilot.civl_id = payload.civl_id or pilot.civl_id

    user = User(
        username=email,
        full_name=f"{payload.first_name.strip()} {payload.last_name.strip()}",
        role="pilot",
        pilot_id=pilot.id,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return TokenResponse(access_token=create_access_token(user.username), user=UserSummary.model_validate(user))


@router.get("/me", response_model=UserSummary)
def me(user: User = Depends(get_current_user)) -> UserSummary:
    return UserSummary.model_validate(user)
