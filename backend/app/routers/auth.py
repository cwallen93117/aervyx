from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_session
from app.deps import get_current_user
from app.models import Pilot, User
from app.schemas import (
    AccountSettingsResponse,
    AccountSettingsUpdate,
    AccountSettingsUpdateResponse,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _settings_payload(user: User, pilot: Pilot | None, access_token: str | None = None) -> AccountSettingsUpdateResponse:
    return AccountSettingsUpdateResponse(
        username=user.username,
        full_name=user.full_name,
        email=pilot.email if pilot else (user.username if "@" in user.username else None),
        first_name=pilot.first_name if pilot else None,
        last_name=pilot.last_name if pilot else None,
        nation=pilot.nation if pilot else None,
        competition_number=pilot.competition_number if pilot else None,
        civl_id=pilot.civl_id if pilot else None,
        access_token=access_token,
    )


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


@router.get("/settings", response_model=AccountSettingsResponse)
def get_settings(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> AccountSettingsResponse:
    pilot = session.get(Pilot, user.pilot_id) if user.pilot_id else None
    return _settings_payload(user, pilot)


@router.patch("/settings", response_model=AccountSettingsUpdateResponse)
def update_settings(
    payload: AccountSettingsUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AccountSettingsResponse:
    username = payload.username.strip()
    full_name = payload.full_name.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Full name is required")

    existing_user = session.scalar(select(User).where(User.username == username, User.id != user.id))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already in use")

    user.username = username
    user.full_name = full_name

    pilot = session.get(Pilot, user.pilot_id) if user.pilot_id else None
    if pilot is not None:
        email = payload.email.strip().lower() if payload.email and payload.email.strip() else None
        if email:
            existing_pilot = session.scalar(select(Pilot).where(func.lower(Pilot.email) == email, Pilot.id != pilot.id))
            if existing_pilot is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already linked to another pilot")
        pilot.email = email
        pilot.first_name = (payload.first_name or pilot.first_name or "").strip() or pilot.first_name
        pilot.last_name = (payload.last_name or pilot.last_name or "").strip() or pilot.last_name
        pilot.nation = payload.nation.strip().upper() if payload.nation and payload.nation.strip() else None
        pilot.competition_number = payload.competition_number.strip() if payload.competition_number and payload.competition_number.strip() else None
        pilot.civl_id = payload.civl_id.strip() if payload.civl_id and payload.civl_id.strip() else None
        rebuilt_name = " ".join(part for part in [pilot.first_name, pilot.last_name] if part).strip()
        if rebuilt_name:
            user.full_name = rebuilt_name

    session.add(user)
    session.commit()
    session.refresh(user)
    if pilot is not None:
        session.refresh(pilot)
    return _settings_payload(user, pilot, access_token=create_access_token(user.username))


@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a new password that is different from the current one")
    user.password_hash = hash_password(payload.new_password)
    session.add(user)
    session.commit()
    return {"status": "ok"}
