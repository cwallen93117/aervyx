import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings as get_app_settings
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token, hash_password, verify_password
from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import LivePosition, Pilot, TrackingSession, User, UserEmail
from app.schemas import (
    AdminUserCredentialsUpdate,
    AdminUserResponse,
    AdminUserUpdate,
    AccountSettingsResponse,
    AccountSettingsUpdate,
    AccountSettingsUpdateResponse,
    GoogleAuthRequest,
    LoginRequest,
    MeshDeviceRegister,
    PasswordChangeRequest,
    PilotClaimRequest,
    PilotClaimResponse,
    PilotClaimSearchResult,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserEmailCreate,
    UserEmailResponse,
    UserSummary,
)

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/auth", tags=["auth"])
VALID_ACCOUNT_ROLES = {"pilot", "organizer"}
VALID_PROFILE_TYPES = {"pilot", "driver"}
# Admins may additionally assign a user as a stationary Meshtastic relay node.
VALID_PROFILE_TYPES_ADMIN = VALID_PROFILE_TYPES | {"stationary_node"}
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


def _find_pilot_broad_match(session: Session, email: str, competition_number: str | None, civl_id: str | None) -> Pilot | None:
    """Find a Pilot by email, user_emails table, competition_number, or civl_id."""
    # 1. Primary Pilot.email
    pilot = session.scalar(select(Pilot).where(func.lower(Pilot.email) == email))
    if pilot is not None:
        return pilot
    # 2. user_emails table → owning user → their pilot
    try:
        ue_row = session.scalar(select(UserEmail).where(func.lower(UserEmail.email) == email))
        if ue_row is not None:
            owner = session.get(User, ue_row.user_id)
            if owner and owner.pilot_id:
                pilot = session.get(Pilot, owner.pilot_id)
                if pilot is not None:
                    return pilot
    except Exception:
        # user_emails table may not exist yet — degrade gracefully
        logger.debug("user_emails lookup skipped (table may not exist)")
    # 3. competition_number
    if competition_number and competition_number.strip():
        pilot = session.scalar(select(Pilot).where(func.lower(Pilot.competition_number) == competition_number.strip().lower()))
        if pilot is not None:
            return pilot
    # 4. civl_id
    if civl_id and civl_id.strip():
        pilot = session.scalar(select(Pilot).where(func.lower(Pilot.civl_id) == civl_id.strip().lower()))
        if pilot is not None:
            return pilot
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
        pilot_id=user.pilot_id,
        has_password=bool(user.password_hash),
        access_token=access_token,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    submitted_username = payload.username.strip().lower()
    user = session.scalar(select(User).where(User.username == submitted_username, User.is_active.is_(True)))
    if user is None:
        user = session.scalar(select(User).where(User.username == payload.username.strip(), User.is_active.is_(True)))
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=create_access_token(user.username),
        refresh_token=create_refresh_token(user.username),
        user=UserSummary.model_validate(user),
    )


@router.get("/google-client-id")
def google_client_id() -> dict[str, str | None]:
    """Return the Google Client ID so the frontend can initialize the Sign-In button."""
    settings = get_app_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google sign-in not configured")
    return {"client_id": settings.google_client_id}


@router.post("/google", response_model=TokenResponse)
@limiter.limit("10/minute")
def google_auth(request: Request, payload: GoogleAuthRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Authenticate via Google ID token. Links to existing account if email matches, otherwise creates a new account."""
    settings = get_app_settings()
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

    # Only trust emails that Google has verified
    if not idinfo.get("email_verified", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google email is not verified")

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
        # 3. Find or create pilot, then find or create user account
        given_name = idinfo.get("given_name", "")
        family_name = idinfo.get("family_name", "")
        full_name = f"{given_name} {family_name}".strip() or email

        pilot = _find_pilot_broad_match(session, email, None, None)
        if pilot is None:
            pilot = Pilot(
                first_name=given_name or email.split("@")[0],
                last_name=family_name or "",
                email=email,
            )
            session.add(pilot)
            session.flush()

        # Auto-merge: if the pilot already has a linked User (e.g. organizer-created
        # slug account), upgrade that account instead of creating a duplicate.
        user = session.scalar(select(User).where(User.pilot_id == pilot.id))
        if user is not None:
            logger.info("Merging Google sign-in into existing account %s (pilot_id=%s)", user.username, pilot.id)
            user.username = email
            user.full_name = full_name
            user.oauth_provider = "google"
            user.oauth_id = google_id
            user.is_active = True
            session.add(user)
        else:
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
        logger.info("User %s authenticated via Google sign-in", user.username)

    return TokenResponse(
        access_token=create_access_token(user.username),
        refresh_token=create_refresh_token(user.username),
        user=UserSummary.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    email = payload.email.strip().lower()
    account_role = payload.account_role.strip().lower() if payload.account_role else "pilot"
    if account_role not in VALID_ACCOUNT_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose either pilot or organizer for the new account")

    # Check if an account with this email as username already exists
    existing_by_email = session.scalar(select(User).where(User.username == email))
    if existing_by_email is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists")

    pilot: Pilot | None = None
    if account_role == "pilot":
        pilot = _find_pilot_broad_match(session, email, payload.competition_number, payload.civl_id)
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

    # Auto-merge: if the pilot already has a linked User (e.g. organizer-created
    # slug account), upgrade that account instead of creating a duplicate.
    user: User | None = None
    if pilot is not None:
        user = session.scalar(select(User).where(User.pilot_id == pilot.id))
    if user is not None:
        logger.info("Merging registration into existing account %s (pilot_id=%s) — upgrading to email login", user.username, pilot.id)
        user.username = email
        user.full_name = f"{payload.first_name.strip()} {payload.last_name.strip()}"
        user.password_hash = hash_password(payload.password)
        user.is_active = True
        session.add(user)
    else:
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
    return TokenResponse(
        access_token=create_access_token(user.username),
        refresh_token=create_refresh_token(user.username),
        user=UserSummary.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh(request: Request, payload: RefreshRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    subject = decode_refresh_token(payload.refresh_token)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    user = session.scalar(select(User).where(User.username == subject, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(user.username),
        refresh_token=create_refresh_token(user.username),
        user=UserSummary.model_validate(user),
    )


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

    if payload.role is not None:
        requested_role = payload.role.strip().lower()
        if requested_role not in VALID_ACCOUNT_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be pilot or organizer")
        if user.role == "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role cannot be changed through settings")
        user.role = requested_role

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


# ---------------------------------------------------------------------------
# Meshtastic device self-registration
# ---------------------------------------------------------------------------

@router.put("/mesh-device")
def register_mesh_device(
    payload: MeshDeviceRegister,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Allow a logged-in user to register (or clear) their own Meshtastic device ID.

    If another user already holds the same device ID that device association is
    transferred to the caller — the latest BLE pairing wins.
    Sending null / empty string clears the current user's association.
    """
    device_id = (payload.mesh_device_id or "").strip() or None

    if device_id is not None:
        # Clear the device from any other user who currently holds it
        previous_owner = session.scalar(
            select(User).where(User.mesh_device_id == device_id, User.id != user.id)
        )
        if previous_owner is not None:
            previous_owner.mesh_device_id = None
            session.add(previous_owner)
            logger.info(
                "Transferred mesh_device_id %s from user %s to user %s",
                device_id,
                previous_owner.username,
                user.username,
            )

    user.mesh_device_id = device_id
    session.add(user)
    session.commit()
    logger.info("User %s set mesh_device_id=%s", user.username, device_id)
    return {"ok": True, "mesh_device_id": device_id}


# ---------------------------------------------------------------------------
# Additional-email management
# ---------------------------------------------------------------------------

@router.get("/emails", response_model=list[UserEmailResponse])
def list_emails(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[UserEmailResponse]:
    rows = session.scalars(
        select(UserEmail).where(UserEmail.user_id == user.id).order_by(UserEmail.created_at)
    ).all()
    return [UserEmailResponse.model_validate(r) for r in rows]


@router.post("/emails", response_model=UserEmailResponse, status_code=status.HTTP_201_CREATED)
def add_email(
    payload: UserEmailCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserEmailResponse:
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email address")
    # Check against users.username (primary email) and user_emails.email
    existing_user = session.scalar(
        select(User).where(func.lower(User.username) == email)
    )
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    existing_ue = session.scalar(
        select(UserEmail).where(func.lower(UserEmail.email) == email)
    )
    if existing_ue is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    ue = UserEmail(user_id=user.id, email=email)
    session.add(ue)
    session.commit()
    session.refresh(ue)
    return UserEmailResponse.model_validate(ue)


@router.delete("/emails/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_email(
    email_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    ue = session.scalar(
        select(UserEmail).where(UserEmail.id == email_id, UserEmail.user_id == user.id)
    )
    if ue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")
    session.delete(ue)
    session.commit()


# ---------------------------------------------------------------------------
# Pilot-record search & self-service claim
# ---------------------------------------------------------------------------

def _is_auto_generated_user(u: User) -> bool:
    """Return True when the user account was auto-created during pilot import
    (slug username like 'john-smith', not a real email)."""
    return "@" not in (u.username or "")


@router.get("/pilot-search", response_model=list[PilotClaimSearchResult])
def pilot_search(
    q: str = "",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[PilotClaimSearchResult]:
    """Search for unclaimed pilot records by name fragment."""
    term = q.strip()
    if len(term) < 2:
        return []
    like = f"%{term}%"
    pilots = session.scalars(
        select(Pilot)
        .where(
            or_(
                func.lower(Pilot.first_name).like(like.lower()),
                func.lower(Pilot.last_name).like(like.lower()),
                func.lower(Pilot.competition_number).like(like.lower()),
            )
        )
        .limit(20)
    ).all()

    # Gather user emails for instant-claim detection
    user_emails_lower: set[str] = {(user.username or "").lower()}
    extra_emails = session.scalars(
        select(UserEmail.email).where(UserEmail.user_id == user.id)
    ).all()
    for e in extra_emails:
        user_emails_lower.add(e.lower())

    results: list[PilotClaimSearchResult] = []
    for p in pilots:
        # Check if pilot is claimable: no linked user, or linked user is auto-generated
        linked_user = session.scalar(
            select(User).where(User.pilot_id == p.id, User.is_active.is_(True))
        )
        if linked_user is not None and not _is_auto_generated_user(linked_user):
            continue  # Already claimed by a real user
        # Determine if instant claim is possible
        can_instant = (p.email or "").lower() in user_emails_lower
        results.append(
            PilotClaimSearchResult(
                pilot_id=p.id,
                first_name=p.first_name or "",
                last_name=p.last_name or "",
                nation=getattr(p, "nation", None),
                competition_number=p.competition_number,
                civl_id=getattr(p, "civl_id", None),
                can_instant_claim=can_instant,
            )
        )
    return results


@router.post("/claim-pilot", response_model=PilotClaimResponse)
def claim_pilot(
    payload: PilotClaimRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PilotClaimResponse:
    """Claim an unclaimed pilot record.  Requires at least one matching field
    (email, competition_number, or civl_id)."""
    pilot = session.get(Pilot, payload.pilot_id)
    if pilot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pilot not found")

    # Verify pilot is unclaimed (or only linked to an auto-generated account)
    linked_user = session.scalar(
        select(User).where(User.pilot_id == pilot.id, User.is_active.is_(True))
    )
    if linked_user is not None and not _is_auto_generated_user(linked_user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pilot already claimed by another user")

    # Collect the requesting user's emails
    user_emails_lower: set[str] = {(user.username or "").lower()}
    extra_emails = session.scalars(
        select(UserEmail.email).where(UserEmail.user_id == user.id)
    ).all()
    for e in extra_emails:
        user_emails_lower.add(e.lower())

    # Verify at least one matching field
    matched = False
    # 1. Email match
    if (pilot.email or "").lower() in user_emails_lower:
        matched = True
    # 2. Competition number match
    if not matched and payload.competition_number and payload.competition_number.strip():
        if (pilot.competition_number or "").strip().lower() == payload.competition_number.strip().lower():
            matched = True
    # 3. CIVL ID match
    if not matched and payload.civl_id and payload.civl_id.strip():
        pilot_civl = getattr(pilot, "civl_id", None) or ""
        if pilot_civl.strip().lower() == payload.civl_id.strip().lower():
            matched = True

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot verify ownership. Please contact an administrator.",
        )

    # Deactivate old auto-generated user if present
    if linked_user is not None and _is_auto_generated_user(linked_user) and linked_user.id != user.id:
        linked_user.is_active = False
        linked_user.pilot_id = None
        session.add(linked_user)

    # Link requesting user to the pilot
    user.pilot_id = pilot.id
    # Populate user's full_name from pilot record if blank
    pilot_full = f"{pilot.first_name or ''} {pilot.last_name or ''}".strip()
    if pilot_full and not user.full_name:
        user.full_name = pilot_full
    session.add(user)
    session.commit()
    return PilotClaimResponse(
        success=True,
        pilot_id=pilot.id,
        message=f"Pilot record claimed: {pilot_full}",
    )


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
            first_name=pilots[user.pilot_id].first_name if user.pilot_id and user.pilot_id in pilots else None,
            last_name=pilots[user.pilot_id].last_name if user.pilot_id and user.pilot_id in pilots else None,
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
            mesh_device_id=user.mesh_device_id,
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
    if profile_type not in VALID_PROFILE_TYPES_ADMIN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current type must be pilot, driver, or stationary_node")
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
        first_name=pilot.first_name if pilot else None,
        last_name=pilot.last_name if pilot else None,
        role=target.role,
        profile_type=target.profile_type,
        pilot_id=target.pilot_id,
        email=pilot.email if pilot else None,
        pilot_name=f"{pilot.first_name} {pilot.last_name}".strip() if pilot else None,
        competition_number=pilot.competition_number if pilot else None,
        mesh_device_id=target.mesh_device_id,
        is_active=target.is_active,
        created_at=target.created_at,
    )


@router.delete("/users/{user_id}/mesh-device", status_code=204)
def clear_user_mesh_device(
    user_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    """Admin-only: clear a user's mesh device pairing (e.g. lost or stolen device).
    Device assignment happens automatically when the user pairs via BLE — this
    endpoint only exists to remove an association, never to create one.
    """
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.mesh_device_id = None
    session.add(target)
    session.commit()
    logger.info("Admin %s cleared mesh_device_id for user %s", admin.username, target.username)


@router.patch("/users/{user_id}/credentials", response_model=AdminUserResponse)
def update_user_credentials(
    user_id: int,
    payload: AdminUserCredentialsUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminUserResponse:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.username and payload.username.strip() and payload.username.strip() != target.username:
        new_username = payload.username.strip()
        conflict = session.scalar(select(User).where(User.username == new_username, User.id != target.id))
        if conflict is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        target.username = new_username
    if payload.password and payload.password.strip():
        target.password_hash = hash_password(payload.password.strip())
    session.add(target)
    session.commit()
    session.refresh(target)
    pilot = session.get(Pilot, target.pilot_id) if target.pilot_id else None
    return AdminUserResponse(
        id=target.id,
        username=target.username,
        full_name=target.full_name,
        first_name=pilot.first_name if pilot else None,
        last_name=pilot.last_name if pilot else None,
        role=target.role,
        profile_type=target.profile_type,
        pilot_id=target.pilot_id,
        email=pilot.email if pilot else None,
        pilot_name=f"{pilot.first_name} {pilot.last_name}".strip() if pilot else None,
        competition_number=pilot.competition_number if pilot else None,
        mesh_device_id=target.mesh_device_id,
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
    # Clean up tracking data so deleted users don't appear as ghosts
    # in Live Tracking.  TrackingSession / LivePosition FKs are SET NULL
    # on pilot deletion, but the Pilot row itself survives user deletion,
    # so we must explicitly deactivate sessions and purge positions.
    if target.pilot_id:
        session.query(TrackingSession).filter(
            TrackingSession.pilot_id == target.pilot_id,
        ).update({"is_active": False})
        session.query(LivePosition).filter(
            LivePosition.pilot_id == target.pilot_id,
        ).delete()

    session.delete(target)
    session.commit()
