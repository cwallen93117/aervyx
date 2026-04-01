import logging

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import Pilot, User
from app.schemas import (
    AdminUserResponse,
    AdminUserUpdate,
    AccountSettingsResponse,
    AccountSettingsUpdate,
    AccountSettingsUpdateResponse,
    GoogleAuthRequest,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
VALID_ACCOUNT_ROLES = {"pilot", "organizer"}
VALID_PROFILE_TYPES = {"pilot", "driver"}
VALID_ALTITUDE_UNITS = {"ft", "m"}
VALID_SPEED_UNITS = {"kph", "mph"}
VALID_DISTANCE_UNITS = {"km", "mi"}
VALID_VARIO_UNITS = {"fpm", "ms"}
VALID_AIRCRAFT_ICONS = {"hang_glider", "paraglider", "sailplane"}


def _is_valid_email(value: str) -> bool:
    candidate = value.strip()
    if not candidate or "@" not in candidate:
        return False
    local, _, domain = candidate.partition("@")
    return bool(local and domain and "." in domain)


def _normalize_email_identity(username: str | None, email: str | None) -> str | None:
    candidates = [email, username]
    for raw in candidates:
        if raw and raw.strip():
            candidate = raw.strip().lower()
            if _is_valid_email(candidate):
                return candidate
    return None


def _settings_payload(user: User, pilot: Pilot | None, access_token: str | None = None) -> AccountSettingsUpdateResponse:
    return AccountSettingsUpdateResponse(
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        profile_type=user.profile_type,
        altitude_unit=user.altitude_unit,
        speed_unit=user.speed_unit,
        distance_unit=user.distance_unit,
        vario_unit=user.vario_unit,
        aircraft_icon=user.aircraft_icon,
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
    submitted_username = payload.username.strip().lower()
    user = session.scalar(select(User).where(User.username == submitted_username, User.is_active.is_(True)))
    if user is None:
        user = session.scalar(select(User).where(User.username == payload.username.strip(), User.is_active.is_(True)))
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.username), user=UserSummary.model_validate(user))


@router.get("/google-client-id")
def google_client_id() -> dict[str, str | None]:
    """Return the Google Client ID so the frontend can initialize the Sign-In button."""
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google sign-in not configured")
    return {"client_id": settings.google_client_id}


@router.post("/google", response_model=TokenResponse)
def google_auth(payload: GoogleAuthRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Authenticate via Google ID token. Links to existing account if email matches, otherwise creates a new account."""
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google sign-in is not configured")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential")

    google_id = idinfo["sub"]
    email = idinfo.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google account has no email")

    # 1. Check if we already have a user linked to this Google ID
    user = session.scalar(select(User).where(User.oauth_provider == "google", User.oauth_id == google_id, User.is_active.is_(True)))

    if user is None:
        # 2. Check if there's an existing account with the same email — link it
        user = session.scalar(select(User).where(User.username == email, User.is_active.is_(True)))
        if user is not None:
            user.oauth_provider = "google"
            user.oauth_id = google_id
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info("Linked Google account %s to existing user %s", google_id, user.username)

    if user is None:
        # 3. Create a new account
        given_name = idinfo.get("given_name", "")
        family_name = idinfo.get("family_name", "")
        full_name = f"{given_name} {family_name}".strip() or email

        pilot = session.scalar(select(Pilot).where(func.lower(Pilot.email) == email))
        if pilot is None:
            pilot = Pilot(
                first_name=given_name or email.split("@")[0],
                last_name=family_name or "",
                email=email,
            )
            session.add(pilot)
            session.flush()

        user = User(
            username=email,
            full_name=full_name,
            role="pilot",
            profile_type="pilot",
            pilot_id=pilot.id,
            password_hash=None,
            oauth_provider="google",
            oauth_id=google_id,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("Created new user %s via Google sign-in", user.username)

    return TokenResponse(access_token=create_access_token(user.username), user=UserSummary.model_validate(user))


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    email = payload.email.strip().lower()
    account_role = payload.account_role.strip().lower() if payload.account_role else "pilot"
    if account_role not in VALID_ACCOUNT_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose either pilot or organizer for the new account")
    if session.scalar(select(User).where(User.username == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists")

    pilot: Pilot | None = None
    if account_role == "pilot":
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
        role=account_role,
        profile_type="pilot" if account_role == "pilot" else "driver",
        pilot_id=pilot.id if pilot else None,
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
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Full name is required")
    profile_type = payload.profile_type.strip().lower() if payload.profile_type else "pilot"
    if profile_type not in VALID_PROFILE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose either pilot or driver for the current type")
    altitude_unit = payload.altitude_unit.strip().lower() if payload.altitude_unit else "ft"
    speed_unit = payload.speed_unit.strip().lower() if payload.speed_unit else "kph"
    distance_unit = payload.distance_unit.strip().lower() if payload.distance_unit else "km"
    vario_unit = payload.vario_unit.strip().lower() if payload.vario_unit else "fpm"
    aircraft_icon = payload.aircraft_icon.strip().lower() if payload.aircraft_icon else "hang_glider"
    if altitude_unit not in VALID_ALTITUDE_UNITS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Altitude unit must be ft or m")
    if speed_unit not in VALID_SPEED_UNITS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Speed unit must be kph or mph")
    if distance_unit not in VALID_DISTANCE_UNITS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Distance unit must be km or mi")
    if vario_unit not in VALID_VARIO_UNITS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vario unit must be fpm or m/s")
    if aircraft_icon not in VALID_AIRCRAFT_ICONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aircraft icon must be hang_glider, paraglider, or sailplane")

    normalized_email_identity = _normalize_email_identity(payload.username, payload.email)
    if normalized_email_identity is None:
        if "@" in user.username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username / email must be a valid email address")
        normalized_email_identity = user.username
    username = normalized_email_identity

    existing_user = session.scalar(select(User).where(User.username == username, User.id != user.id))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username / email is already in use")

    user.username = username
    user.full_name = full_name
    user.profile_type = profile_type
    user.altitude_unit = altitude_unit
    user.speed_unit = speed_unit
    user.distance_unit = distance_unit
    user.vario_unit = vario_unit
    user.aircraft_icon = aircraft_icon

    pilot = session.get(Pilot, user.pilot_id) if user.pilot_id else None
    if pilot is not None:
        email = normalized_email_identity
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
    if user.password_hash and not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a new password that is different from the current one")
    user.password_hash = hash_password(payload.new_password)
    session.add(user)
    session.commit()
    return {"status": "ok"}


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> list[AdminUserResponse]:
    users = session.scalars(select(User).order_by(User.created_at.desc(), User.username.asc())).all()
    pilot_ids = [user.pilot_id for user in users if user.pilot_id]
    pilots = {}
    if pilot_ids:
        pilots = {pilot.id: pilot for pilot in session.scalars(select(Pilot).where(Pilot.id.in_(pilot_ids))).all()}
    return [
        AdminUserResponse(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            profile_type=user.profile_type,
            pilot_id=user.pilot_id,
            email=pilots[user.pilot_id].email if user.pilot_id and user.pilot_id in pilots else None,
            pilot_name=(
                f"{pilots[user.pilot_id].first_name} {pilots[user.pilot_id].last_name}".strip()
                if user.pilot_id and user.pilot_id in pilots
                else None
            ),
            competition_number=pilots[user.pilot_id].competition_number if user.pilot_id and user.pilot_id in pilots else None,
            is_active=user.is_active,
            created_at=user.created_at,
        )
        for user in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user_account(
    user_id: int,
    payload: AdminUserUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminUserResponse:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    role = payload.role.strip().lower()
    profile_type = payload.profile_type.strip().lower()
    if role not in {"admin", "organizer", "pilot"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be admin, organizer, or pilot")
    if profile_type not in VALID_PROFILE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current type must be pilot or driver")
    if target.id == admin.id and role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use another admin account before changing your own admin role")
    if target.role == "admin" and role != "admin":
        admin_count = session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one active admin account must remain")
    target.role = role
    target.profile_type = profile_type
    target.is_active = payload.is_active
    session.add(target)
    session.commit()
    session.refresh(target)
    pilot = session.get(Pilot, target.pilot_id) if target.pilot_id else None
    return AdminUserResponse(
        id=target.id,
        username=target.username,
        full_name=target.full_name,
        role=target.role,
        profile_type=target.profile_type,
        pilot_id=target.pilot_id,
        email=pilot.email if pilot else None,
        pilot_name=f"{pilot.first_name} {pilot.last_name}".strip() if pilot else None,
        competition_number=pilot.competition_number if pilot else None,
        is_active=target.is_active,
        created_at=target.created_at,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_account(user_id: int, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> None:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own admin account")
    if target.role == "admin":
        admin_count = session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one active admin account must remain")
    session.delete(target)
    session.commit()
