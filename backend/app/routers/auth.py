import logging
import json
import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import get_settings as get_app_settings
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token, hash_password, verify_password
from app.db import get_session
from app.deps import get_current_user, require_admin, resolve_user_from_token_subject, token_subject_for_user
from app.models import LivePosition, MeshDevice, PasskeyChallenge, PasskeyCredential, Pilot, TrackingSession, User, UserEmail
from app.schemas import (
    AdminUserCredentialsUpdate,
    AdminUserResponse,
    AdminUserUpdate,
    AccountSettingsResponse,
    AccountSettingsUpdate,
    AccountSettingsUpdateResponse,
    AccountPreferencesUpdate,
    CustomScoringFormula,
    CustomScoringFormulaList,
    GoogleAuthRequest,
    LoginRequest,
    MeshDeviceCreate,
    MeshDeviceRegister,
    MeshDeviceResponse,
    MeshDeviceUpdate,
    PasswordChangeRequest,
    PasskeyOptionsResponse,
    PasskeyRenameRequest,
    PasskeyResponse,
    PasskeyVerifyRequest,
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
from app.services.pilot_identity import (
    add_user_email_alias,
    find_canonical_pilot,
    find_user_by_login_email,
    merge_pilots,
    repair_user_email_alias_identity,
    repair_user_email_identity,
)
from app.services.mesh_ids import normalize_mesh_device_id

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
VALID_MESH_DEVICE_PURPOSES = {"tracking", "base_station", "driver_wifi", "driver_mesh", "relay"}
TRACKING_MESH_PURPOSE = "tracking"
PASSKEY_CHALLENGE_TTL = timedelta(minutes=5)
CUSTOM_SCORING_FORMULA_ROLES = {"admin", "organizer"}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _profile_type_updated_at(user: User) -> datetime:
    return _as_utc(user.profile_type_updated_at or user.created_at or _now_utc())


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
    """Find a Pilot through the shared canonical identity resolver."""
    return find_canonical_pilot(session, email=email, competition_number=competition_number, civl_id=civl_id)


def _settings_payload(user: User, pilot: Pilot | None, access_token: str | None = None) -> AccountSettingsUpdateResponse:
    return AccountSettingsUpdateResponse(
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        profile_type=user.profile_type,
        profile_type_updated_at=_profile_type_updated_at(user),
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


def _require_custom_scoring_formula_access(user: User) -> None:
    if user.role not in CUSTOM_SCORING_FORMULA_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and organizers can manage custom scoring parameters")


def _custom_scoring_formulas(user: User) -> list[CustomScoringFormula]:
    raw = user.custom_scoring_formulas_json or []
    if not isinstance(raw, list):
        return []
    formulas: list[CustomScoringFormula] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            formula = CustomScoringFormula.model_validate(item)
        except Exception:
            continue
        value = formula.value.strip()
        label = formula.label.strip()
        if not value or not label or value in seen:
            continue
        formulas.append(CustomScoringFormula(value=value, label=label, preset=formula.preset))
        seen.add(value)
    return formulas


def _normalize_mesh_device_id(value: str | None) -> str | None:
    return normalize_mesh_device_id(value)


def _normalize_mesh_purpose(value: str | None) -> str:
    candidate = (value or "").strip().lower() or TRACKING_MESH_PURPOSE
    if candidate not in VALID_MESH_DEVICE_PURPOSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device purpose must be tracking, base_station, driver_wifi, driver_mesh, or relay",
        )
    return candidate


def _default_mesh_device_label(user: User, device_id: str) -> str:
    return (user.full_name or user.username or device_id).strip()[:160] or device_id


def _mesh_device_response(device: MeshDevice, owner: User | None = None) -> MeshDeviceResponse:
    device_id = _normalize_mesh_device_id(device.device_id) or device.device_id
    owner_tracker_id = _normalize_mesh_device_id(owner.mesh_device_id) if owner is not None else None
    return MeshDeviceResponse(
        id=device.id,
        owner_user_id=device.owner_user_id,
        owner_name=owner.full_name if owner else None,
        device_id=device_id,
        label=device.label,
        purpose=device.purpose,
        is_pilot_tracker=owner_tracker_id == device_id,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


def _admin_user_response(
    user: User,
    session: Session,
    *,
    pilot: Pilot | None = None,
    mesh_devices: list[MeshDevice] | None = None,
) -> AdminUserResponse:
    if pilot is None and user.pilot_id:
        pilot = session.get(Pilot, user.pilot_id)
    if mesh_devices is None:
        mesh_devices = session.scalars(
            select(MeshDevice)
            .where(MeshDevice.owner_user_id == user.id)
            .order_by(MeshDevice.purpose.asc(), MeshDevice.label.asc(), MeshDevice.device_id.asc())
        ).all()
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        first_name=pilot.first_name if pilot else None,
        last_name=pilot.last_name if pilot else None,
        role=user.role,
        profile_type=user.profile_type,
        profile_type_updated_at=_profile_type_updated_at(user),
        pilot_id=user.pilot_id,
        email=pilot.email if pilot else None,
        pilot_name=f"{pilot.first_name} {pilot.last_name}".strip() if pilot else None,
        competition_number=pilot.competition_number if pilot else None,
        mesh_device_id=user.mesh_device_id,
        mesh_devices=[_mesh_device_response(device, user) for device in mesh_devices],
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _request_mqtt_refresh() -> None:
    from app.services.mqtt_subscriber import request_mqtt_reconnect

    request_mqtt_reconnect()


def _passkey_config() -> tuple[str, list[str]]:
    settings = get_app_settings()
    web_origin = settings.app_public_url.rstrip("/")
    rp_id = settings.passkey_rp_id or urlparse(web_origin).hostname
    if not rp_id or not web_origin:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Passkey sign-in is not configured")
    return rp_id, [web_origin, *settings.passkey_android_origins]


def _passkey_user_handle(user_id: int) -> bytes:
    return hmac.new(
        get_app_settings().app_secret_key.encode("utf-8"),
        f"passkey-user:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _issue_passkey_challenge(session: Session, purpose: str, user_id: int | None = None) -> PasskeyChallenge:
    now = _now_utc()
    session.execute(
        delete(PasskeyChallenge)
        .where(or_(PasskeyChallenge.expires_at <= now, PasskeyChallenge.used_at.is_not(None)))
        .execution_options(synchronize_session=False)
    )
    challenge = PasskeyChallenge(
        id=secrets.token_urlsafe(24),
        challenge=secrets.token_bytes(32),
        purpose=purpose,
        user_id=user_id,
        expires_at=now + PASSKEY_CHALLENGE_TTL,
    )
    session.add(challenge)
    session.commit()
    return challenge


def _consume_passkey_challenge(
    session: Session,
    ceremony_id: str,
    purpose: str,
    user_id: int | None,
) -> bytes:
    challenge = session.get(PasskeyChallenge, ceremony_id)
    if challenge is None or challenge.purpose != purpose or challenge.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey request expired; try again")
    challenge_bytes = challenge.challenge
    now = _now_utc()
    consumed = session.execute(
        update(PasskeyChallenge)
        .where(
            PasskeyChallenge.id == ceremony_id,
            PasskeyChallenge.used_at.is_(None),
            PasskeyChallenge.expires_at > now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    if consumed.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey request expired; try again")
    return challenge_bytes


def _passkey_name(value: str | None) -> str:
    return (value or "Passkey").strip()[:80] or "Passkey"


def _passkey_payload(passkey: PasskeyCredential) -> PasskeyResponse:
    return PasskeyResponse(
        id=passkey.id,
        name=passkey.name,
        transports=[str(value) for value in (passkey.transports or [])],
        created_at=passkey.created_at,
        last_used_at=passkey.last_used_at,
    )


def _clear_user_tracking_device(user: User, session: Session) -> None:
    user.mesh_device_id = None
    session.add(user)


def _set_user_tracking_device(
    user: User,
    device_id: str | None,
    session: Session,
    *,
    label: str | None = None,
    allow_transfer: bool = True,
) -> MeshDevice | None:
    normalized = _normalize_mesh_device_id(device_id)
    if normalized is None:
        _clear_user_tracking_device(user, session)
        return None

    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == normalized))
    if device is not None and device.owner_user_id != user.id and not allow_transfer:
        owner = session.get(User, device.owner_user_id)
        owner_name = owner.full_name if owner else "another user"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"That device is registered to {owner_name}")

    previous_owner = session.scalar(select(User).where(User.mesh_device_id == normalized, User.id != user.id))
    if previous_owner is not None:
        previous_owner.mesh_device_id = None
        session.add(previous_owner)

    if device is None:
        device = MeshDevice(
            owner_user_id=user.id,
            device_id=normalized,
            label=(label or _default_mesh_device_label(user, normalized)).strip()[:160],
            purpose=TRACKING_MESH_PURPOSE,
        )
    else:
        device.owner_user_id = user.id
        device.label = (label or device.label or _default_mesh_device_label(user, normalized)).strip()[:160]
        device.purpose = TRACKING_MESH_PURPOSE

    user.mesh_device_id = normalized
    session.add_all([user, device])
    return device


def _upsert_owned_mesh_device(
    user: User,
    payload: MeshDeviceCreate,
    session: Session,
    *,
    allow_transfer: bool = False,
) -> MeshDevice:
    device_id = _normalize_mesh_device_id(payload.device_id)
    if device_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_id is required")
    purpose = _normalize_mesh_purpose(payload.purpose)
    label = (payload.label or "").strip()[:160] or _default_mesh_device_label(user, device_id)

    if purpose == TRACKING_MESH_PURPOSE:
        device = _set_user_tracking_device(
            user,
            device_id,
            session,
            label=label,
            allow_transfer=allow_transfer,
        )
        assert device is not None
        session.add_all([user, device])
        return device

    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == device_id))
    if device is not None and device.owner_user_id != user.id and not allow_transfer:
        owner = session.get(User, device.owner_user_id)
        owner_name = owner.full_name if owner else "another user"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"That device is registered to {owner_name}")

    legacy_owner = session.scalar(select(User).where(User.mesh_device_id == device_id, User.id != user.id))
    if legacy_owner is not None and not allow_transfer:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"That device is registered to {legacy_owner.full_name}")
    if legacy_owner is not None:
        legacy_owner.mesh_device_id = None
        session.add(legacy_owner)

    if user.mesh_device_id == device_id:
        user.mesh_device_id = None
        session.add(user)

    if device is None:
        device = MeshDevice(
            owner_user_id=user.id,
            device_id=device_id,
            label=label,
            purpose=purpose,
        )
    else:
        device.owner_user_id = user.id
        device.label = label
        device.purpose = purpose
    session.add(device)
    return device


def _update_owned_mesh_device(
    device_id: str,
    payload: MeshDeviceUpdate,
    user: User,
    session: Session,
) -> MeshDevice:
    normalized = _normalize_mesh_device_id(device_id)
    if normalized is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_id is required")
    device = session.scalar(
        select(MeshDevice).where(MeshDevice.device_id == normalized, MeshDevice.owner_user_id == user.id)
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mesh device not found")

    next_device_id = normalized
    if payload.device_id is not None:
        next_device_id = _normalize_mesh_device_id(payload.device_id)
        if next_device_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_id is required")
        if next_device_id != normalized:
            existing_device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == next_device_id))
            if existing_device is not None and existing_device.id != device.id:
                owner = session.get(User, existing_device.owner_user_id)
                owner_name = owner.full_name if owner else "another user"
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"That device is registered to {owner_name}")
            legacy_owner = session.scalar(select(User).where(User.mesh_device_id == next_device_id, User.id != user.id))
            if legacy_owner is not None:
                owner_name = legacy_owner.full_name or legacy_owner.username or "another user"
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"That device is registered to {owner_name}")
            device.device_id = next_device_id

    next_purpose = _normalize_mesh_purpose(payload.purpose) if payload.purpose is not None else device.purpose
    if payload.label is not None:
        device.label = payload.label.strip()[:160] or _default_mesh_device_label(user, next_device_id)
    if next_purpose == TRACKING_MESH_PURPOSE:
        device.purpose = TRACKING_MESH_PURPOSE
        user.mesh_device_id = next_device_id
        session.add(user)
    else:
        device.purpose = next_purpose
        if user.mesh_device_id in {normalized, next_device_id}:
            user.mesh_device_id = None
            session.add(user)
    session.add(device)
    return device


def _delete_owned_mesh_device(device_id: str, user: User, session: Session) -> MeshDevice:
    normalized = _normalize_mesh_device_id(device_id)
    if normalized is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_id is required")
    device = session.scalar(
        select(MeshDevice).where(MeshDevice.device_id == normalized, MeshDevice.owner_user_id == user.id)
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mesh device not found")
    if _normalize_mesh_device_id(user.mesh_device_id) == normalized:
        user.mesh_device_id = None
        session.add(user)
    session.delete(device)
    return device


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    submitted_username = payload.username.strip().lower()
    user = find_user_by_login_email(session, submitted_username)
    if user is None:
        user = session.scalar(select(User).where(User.username == payload.username.strip(), User.is_active.is_(True)))
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if repair_user_email_identity(session, user) is not None:
        session.commit()
        session.refresh(user)
    return TokenResponse(
        access_token=create_access_token(token_subject_for_user(user)),
        refresh_token=create_refresh_token(token_subject_for_user(user)),
        user=UserSummary.model_validate(user),
    )


@router.post("/passkeys/register/options", response_model=PasskeyOptionsResponse)
@limiter.limit("20/minute")
def passkey_registration_options(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PasskeyOptionsResponse:
    rp_id, _ = _passkey_config()
    credentials = session.scalars(
        select(PasskeyCredential).where(PasskeyCredential.user_id == user.id)
    ).all()
    user_handle = credentials[0].user_handle if credentials else _passkey_user_handle(user.id)
    challenge = _issue_passkey_challenge(session, "register", user.id)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Aervyx",
        user_id=user_handle,
        user_name=user.username,
        user_display_name=user.full_name,
        challenge=challenge.challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(credential.credential_id))
            for credential in credentials
        ],
    )
    return PasskeyOptionsResponse(ceremony_id=challenge.id, public_key=json.loads(options_to_json(options)))


@router.post("/passkeys/register/verify", response_model=PasskeyResponse)
@limiter.limit("10/minute")
def passkey_registration_verify(
    request: Request,
    payload: PasskeyVerifyRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PasskeyResponse:
    challenge = _consume_passkey_challenge(session, payload.ceremony_id, "register", user.id)
    rp_id, origins = _passkey_config()
    try:
        verified = verify_registration_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origins,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        logger.info("Passkey registration rejected for user %s: %s", user.id, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey registration failed") from exc

    credential_id = bytes_to_base64url(verified.credential_id)
    if session.scalar(select(PasskeyCredential.id).where(PasskeyCredential.credential_id == credential_id)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That passkey is already registered")
    transports = payload.credential.get("response", {}).get("transports", [])
    passkey = PasskeyCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        user_handle=(
            session.scalar(
                select(PasskeyCredential.user_handle)
                .where(PasskeyCredential.user_id == user.id)
                .limit(1)
            )
            or _passkey_user_handle(user.id)
        ),
        sign_count=verified.sign_count,
        transports=transports if isinstance(transports, list) else [],
        aaguid=verified.aaguid,
        name=_passkey_name(payload.name),
    )
    session.add(passkey)
    session.commit()
    session.refresh(passkey)
    return _passkey_payload(passkey)


@router.post("/passkeys/login/options", response_model=PasskeyOptionsResponse)
@limiter.limit("20/minute")
def passkey_login_options(
    request: Request,
    session: Session = Depends(get_session),
) -> PasskeyOptionsResponse:
    rp_id, _ = _passkey_config()
    challenge = _issue_passkey_challenge(session, "login")
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge.challenge,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return PasskeyOptionsResponse(ceremony_id=challenge.id, public_key=json.loads(options_to_json(options)))


@router.post("/passkeys/login/verify", response_model=TokenResponse)
@limiter.limit("10/minute")
def passkey_login_verify(
    request: Request,
    payload: PasskeyVerifyRequest,
    session: Session = Depends(get_session),
) -> TokenResponse:
    challenge = _consume_passkey_challenge(session, payload.ceremony_id, "login", None)
    credential_id = str(payload.credential.get("id", ""))
    passkey = session.scalar(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id)
    )
    user = session.get(User, passkey.user_id) if passkey else None
    if passkey is None or user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey sign-in failed")
    rp_id, origins = _passkey_config()
    try:
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origins,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        logger.info("Passkey sign-in rejected for credential %s: %s", passkey.id, exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey sign-in failed") from exc
    if bytes_to_base64url(verified.credential_id) != passkey.credential_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey sign-in failed")

    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = _now_utc()
    session.add(passkey)
    session.commit()
    return TokenResponse(
        access_token=create_access_token(token_subject_for_user(user)),
        refresh_token=create_refresh_token(token_subject_for_user(user)),
        user=UserSummary.model_validate(user),
    )


@router.get("/passkeys", response_model=list[PasskeyResponse])
def list_passkeys(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[PasskeyResponse]:
    return [
        _passkey_payload(passkey)
        for passkey in session.scalars(
            select(PasskeyCredential)
            .where(PasskeyCredential.user_id == user.id)
            .order_by(PasskeyCredential.created_at.desc(), PasskeyCredential.id.desc())
        ).all()
    ]


@router.patch("/passkeys/{passkey_id}", response_model=PasskeyResponse)
def rename_passkey(
    passkey_id: int,
    payload: PasskeyRenameRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PasskeyResponse:
    passkey = session.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.id == passkey_id,
            PasskeyCredential.user_id == user.id,
        )
    )
    if passkey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")
    passkey.name = _passkey_name(payload.name)
    session.add(passkey)
    session.commit()
    session.refresh(passkey)
    return _passkey_payload(passkey)


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_passkey(
    passkey_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    passkey = session.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.id == passkey_id,
            PasskeyCredential.user_id == user.id,
        )
    )
    if passkey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")
    session.delete(passkey)
    session.commit()


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
        user = find_user_by_login_email(session, email)
        if user is not None:
            user.oauth_provider = "google"
            user.oauth_id = google_id
            if user.username.lower() != email:
                try:
                    add_user_email_alias(session, user, email)
                except ValueError:
                    pass
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

    if repair_user_email_identity(session, user) is not None:
        session.commit()
        session.refresh(user)

    return TokenResponse(
        access_token=create_access_token(token_subject_for_user(user)),
        refresh_token=create_refresh_token(token_subject_for_user(user)),
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
    existing_by_email = find_user_by_login_email(session, email)
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
        access_token=create_access_token(token_subject_for_user(user)),
        refresh_token=create_refresh_token(token_subject_for_user(user)),
        user=UserSummary.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh(request: Request, payload: RefreshRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    subject = decode_refresh_token(payload.refresh_token)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    user = resolve_user_from_token_subject(session, subject)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(token_subject_for_user(user)),
        refresh_token=create_refresh_token(token_subject_for_user(user)),
        user=UserSummary.model_validate(user),
    )


@router.get("/me", response_model=UserSummary)
def me(user: User = Depends(get_current_user)) -> UserSummary:
    return UserSummary.model_validate(user)


@router.get("/settings", response_model=AccountSettingsResponse)
def get_settings(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> AccountSettingsResponse:
    pilot = session.get(Pilot, user.pilot_id) if user.pilot_id else None
    return _settings_payload(user, pilot)


@router.get("/scoring-formulas", response_model=CustomScoringFormulaList)
def list_custom_scoring_formulas(user: User = Depends(get_current_user)) -> CustomScoringFormulaList:
    _require_custom_scoring_formula_access(user)
    return CustomScoringFormulaList(formulas=_custom_scoring_formulas(user))


@router.patch("/scoring-formulas", response_model=CustomScoringFormulaList)
def save_custom_scoring_formulas(
    payload: CustomScoringFormulaList,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CustomScoringFormulaList:
    _require_custom_scoring_formula_access(user)
    formulas: list[CustomScoringFormula] = []
    seen: set[str] = set()
    for item in payload.formulas:
        value = item.value.strip()
        label = item.label.strip()
        if not value or not label or value in seen:
            continue
        formulas.append(CustomScoringFormula(value=value, label=label, preset=item.preset))
        seen.add(value)
    user.custom_scoring_formulas_json = [item.model_dump() for item in formulas]
    session.add(user)
    session.commit()
    session.refresh(user)
    return CustomScoringFormulaList(formulas=formulas)


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

    existing_user = find_user_by_login_email(session, username)
    if existing_user is not None and existing_user.id == user.id:
        existing_user = None
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username / email is already in use")

    if user.profile_type != profile_type:
        user.profile_type_updated_at = _now_utc()

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
                merge_pilots(session, source_pilot_id=existing_pilot.id, target_pilot_id=pilot.id)
                session.flush()
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
    return _settings_payload(user, pilot, access_token=create_access_token(token_subject_for_user(user)))


@router.patch("/preferences", response_model=UserSummary)
def update_preferences(
    payload: AccountPreferencesUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserSummary:
    if payload.profile_type is not None:
        profile_type = payload.profile_type.strip().lower()
        if profile_type not in VALID_PROFILE_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose either pilot or driver for the current type")
        incoming_updated_at = _as_utc(payload.profile_type_updated_at or _now_utc())
        current_updated_at = _profile_type_updated_at(user)
        if incoming_updated_at >= current_updated_at:
            user.profile_type = profile_type
            user.profile_type_updated_at = incoming_updated_at

    if payload.altitude_unit is not None:
        altitude_unit = payload.altitude_unit.strip().lower()
        if altitude_unit not in VALID_ALTITUDE_UNITS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Altitude unit must be ft or m")
        user.altitude_unit = altitude_unit
    if payload.speed_unit is not None:
        speed_unit = payload.speed_unit.strip().lower()
        if speed_unit not in VALID_SPEED_UNITS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Speed unit must be kph or mph")
        user.speed_unit = speed_unit
    if payload.distance_unit is not None:
        distance_unit = payload.distance_unit.strip().lower()
        if distance_unit not in VALID_DISTANCE_UNITS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Distance unit must be km or mi")
        user.distance_unit = distance_unit
    if payload.vario_unit is not None:
        vario_unit = payload.vario_unit.strip().lower()
        if vario_unit not in VALID_VARIO_UNITS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vario unit must be fpm or m/s")
        user.vario_unit = vario_unit

    session.add(user)
    session.commit()
    session.refresh(user)
    return UserSummary.model_validate(user)


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
    device = _set_user_tracking_device(user, payload.mesh_device_id, session, allow_transfer=True)
    session.commit()
    _request_mqtt_refresh()
    mesh_device_id = device.device_id if device else None
    logger.info("User %s set mesh_device_id=%s", user.username, mesh_device_id)
    return {"ok": True, "mesh_device_id": mesh_device_id}


@router.get("/mesh-devices", response_model=list[MeshDeviceResponse])
def list_mesh_devices(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MeshDeviceResponse]:
    devices = session.scalars(
        select(MeshDevice)
        .where(MeshDevice.owner_user_id == user.id)
        .order_by(MeshDevice.purpose.asc(), MeshDevice.label.asc(), MeshDevice.device_id.asc())
    ).all()
    return [_mesh_device_response(device, user) for device in devices]


@router.post("/mesh-devices", response_model=MeshDeviceResponse, status_code=status.HTTP_201_CREATED)
def create_mesh_device(
    payload: MeshDeviceCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeshDeviceResponse:
    device = _upsert_owned_mesh_device(user, payload, session, allow_transfer=False)
    session.commit()
    _request_mqtt_refresh()
    session.refresh(device)
    return _mesh_device_response(device, user)


@router.put("/mesh-devices/tracking")
def set_tracking_mesh_device(
    payload: MeshDeviceRegister,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    device = _set_user_tracking_device(user, payload.mesh_device_id, session, allow_transfer=False)
    session.commit()
    _request_mqtt_refresh()
    return {"ok": True, "mesh_device_id": device.device_id if device else None}


@router.patch("/mesh-devices/{device_id}", response_model=MeshDeviceResponse)
def update_mesh_device(
    device_id: str,
    payload: MeshDeviceUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeshDeviceResponse:
    device = _update_owned_mesh_device(device_id, payload, user, session)
    session.commit()
    _request_mqtt_refresh()
    session.refresh(device)
    return _mesh_device_response(device, user)


@router.delete("/mesh-devices/{device_id}", status_code=204)
def delete_mesh_device(
    device_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    _delete_owned_mesh_device(device_id, user, session)
    session.commit()
    _request_mqtt_refresh()


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
    existing_user = find_user_by_login_email(session, email)
    if existing_user is not None and existing_user.id != user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    if existing_user is not None and existing_user.id == user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    try:
        ue = add_user_email_alias(session, user, email)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use") from None
    if ue is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    repair_user_email_alias_identity(session, user, email)
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

    if user.pilot_id is not None and user.pilot_id != pilot.id:
        merge_pilots(session, source_pilot_id=user.pilot_id, target_pilot_id=pilot.id)
    elif linked_user is not None and _is_auto_generated_user(linked_user) and linked_user.id != user.id:
        linked_user.is_active = False
        linked_user.pilot_id = None
        session.add(linked_user)

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
    user_ids = [user.id for user in users]
    devices_by_owner: dict[int, list[MeshDevice]] = {user.id: [] for user in users}
    if user_ids:
        devices = session.scalars(
            select(MeshDevice)
            .where(MeshDevice.owner_user_id.in_(user_ids))
            .order_by(MeshDevice.owner_user_id.asc(), MeshDevice.purpose.asc(), MeshDevice.label.asc(), MeshDevice.device_id.asc())
        ).all()
        for device in devices:
            devices_by_owner.setdefault(device.owner_user_id, []).append(device)
    return [
        _admin_user_response(
            user,
            session,
            pilot=pilots.get(user.pilot_id) if user.pilot_id else None,
            mesh_devices=devices_by_owner.get(user.id, []),
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
    if target.profile_type != profile_type:
        target.profile_type_updated_at = _now_utc()
    target.role = role
    target.profile_type = profile_type
    target.is_active = payload.is_active
    session.add(target)
    session.commit()
    session.refresh(target)
    return _admin_user_response(target, session)


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
    _clear_user_tracking_device(target, session)
    session.commit()
    _request_mqtt_refresh()
    logger.info("Admin %s cleared mesh_device_id for user %s", admin.username, target.username)


@router.get("/admin/mesh-device-lookup")
def admin_mesh_device_lookup(
    device_id: str,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    """Admin-only: check whether a mesh device ID is currently assigned to any user.

    Returns the current owner (if any) so the admin UI can warn about reclaiming
    the device from another user before saving the change.
    """
    normalized = _normalize_mesh_device_id(device_id)
    if not normalized:
        return {"device_id": None, "assigned_to": None}
    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == normalized))
    owner = session.get(User, device.owner_user_id) if device is not None else None
    if owner is None:
        owner = session.scalar(select(User).where(User.mesh_device_id == normalized))
    if owner is None:
        return {"device_id": normalized, "assigned_to": None}
    return {
        "device_id": normalized,
        "device": {
            "label": device.label if device else None,
            "purpose": device.purpose if device else "tracking",
        },
        "assigned_to": {
            "user_id": owner.id,
            "username": owner.username,
            "full_name": owner.full_name,
        },
    }


@router.patch("/users/{user_id}/mesh-device", response_model=AdminUserResponse)
def admin_set_user_mesh_device(
    user_id: int,
    payload: MeshDeviceRegister,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminUserResponse:
    """Admin-only: set or change a user's mesh device ID.

    - ``mesh_device_id = null`` or empty string: clears the pairing.
    - Non-null value already held by another user: reclaims it from the previous
      owner (same semantics as BLE pairing) so positions start routing to the
      new owner. Past LivePosition rows keep their original pilot_id attribution.
    """
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    device = _set_user_tracking_device(target, payload.mesh_device_id, session, allow_transfer=True)
    session.commit()
    _request_mqtt_refresh()
    session.refresh(target)
    mesh_device_id = device.device_id if device else None
    logger.info("Admin %s set mesh_device_id=%s for user %s", admin.username, mesh_device_id, target.username)

    return _admin_user_response(target, session)


@router.put("/users/{user_id}/mesh-devices/tracking", response_model=AdminUserResponse)
def admin_set_user_tracking_mesh_device(
    user_id: int,
    payload: MeshDeviceRegister,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminUserResponse:
    """Admin-only: select or clear the user's active pilot-tracker mesh device."""
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    normalized = _normalize_mesh_device_id(payload.mesh_device_id)
    if normalized is None:
        _clear_user_tracking_device(target, session)
        session.commit()
        _request_mqtt_refresh()
        session.refresh(target)
        logger.info("Admin %s cleared tracking mesh device for user %s", admin.username, target.username)
        return _admin_user_response(target, session)

    device = session.scalar(
        select(MeshDevice).where(MeshDevice.device_id == normalized, MeshDevice.owner_user_id == target.id)
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mesh device not found for that user")

    _set_user_tracking_device(target, normalized, session, label=device.label, allow_transfer=False)
    session.commit()
    _request_mqtt_refresh()
    session.refresh(target)
    logger.info("Admin %s set tracking mesh device %s for user %s", admin.username, normalized, target.username)
    return _admin_user_response(target, session)


@router.patch("/users/{user_id}/mesh-devices/{device_id}", response_model=AdminUserResponse)
def admin_update_user_mesh_device(
    user_id: int,
    device_id: str,
    payload: MeshDeviceUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminUserResponse:
    """Admin-only: edit an owned mesh device's inventory fields."""
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    device = _update_owned_mesh_device(device_id, payload, target, session)
    session.commit()
    _request_mqtt_refresh()
    session.refresh(target)
    logger.info("Admin %s updated mesh device %s for user %s", admin.username, device.device_id, target.username)
    return _admin_user_response(target, session)


@router.delete("/users/{user_id}/mesh-devices/{device_id}", response_model=AdminUserResponse)
def admin_delete_user_mesh_device(
    user_id: int,
    device_id: str,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminUserResponse:
    """Admin-only: remove an owned mesh device from a user's profile."""
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    device = _delete_owned_mesh_device(device_id, target, session)
    deleted_device_id = device.device_id
    session.commit()
    _request_mqtt_refresh()
    session.refresh(target)
    logger.info("Admin %s deleted mesh device %s for user %s", admin.username, deleted_device_id, target.username)
    return _admin_user_response(target, session)


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
        new_username = payload.username.strip().lower()
        conflict = find_user_by_login_email(session, new_username)
        if conflict is not None and conflict.id != target.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        target.username = new_username
    if payload.password and payload.password.strip():
        target.password_hash = hash_password(payload.password.strip())
    session.add(target)
    session.commit()
    session.refresh(target)
    return _admin_user_response(target, session)


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
