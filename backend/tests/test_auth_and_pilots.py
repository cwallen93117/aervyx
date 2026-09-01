from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request
from webauthn.helpers.exceptions import WebAuthnException

from app.core.security import create_access_token, create_refresh_token, decode_access_token
from app.db import Base
from app.deps import get_current_user, token_subject_for_user
from app.models import Event, EventPilot, LivePosition, MeshDevice, PasskeyChallenge, PasskeyCredential, Pilot, ScoreResult, Task, TaskScoringInput, TrackingSession, User, UserEmail
from app.routers.auth import (
    admin_delete_user_mesh_device,
    admin_set_user_tracking_mesh_device,
    admin_update_user_mesh_device,
    add_email,
    change_password,
    claim_pilot,
    create_mesh_device,
    delete_user_account,
    delete_passkey,
    login,
    list_passkeys,
    list_mesh_devices,
    list_users,
    passkey_login_options,
    passkey_login_verify,
    passkey_registration_options,
    passkey_registration_verify,
    register,
    register_mesh_device,
    refresh,
    rename_passkey,
    list_custom_scoring_formulas,
    save_custom_scoring_formulas,
    update_mesh_device,
    update_settings,
    update_user_account,
)
from app.routers.events import list_events, update_event
from app.routers.pilots import assign_existing_pilot, create_pilot, list_people, list_pilots, update_event_pilot_class, update_pilot
from app.schemas import AccountSettingsUpdate, AdminUserUpdate, CustomScoringFormula, CustomScoringFormulaList, EventCreate, LoginRequest, MeshDeviceCreate, MeshDeviceRegister, MeshDeviceUpdate, PasskeyRenameRequest, PasskeyVerifyRequest, PasswordChangeRequest, PilotClaimRequest, PilotClassUpdate, PilotUpsert, RefreshRequest, RegisterRequest, UserEmailCreate
from app.services.tracking import resolve_mesh_device_assignment
from app.services.pilot_identity import backfill_user_subject_pilot_links, merge_pilots, repair_pilot_email_identities


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/register",
            "headers": [],
            "client": ("testclient", 50000),
        }
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_new_tokens_use_immutable_user_identity() -> None:
    session = _session()
    user = User(username="jeff@example.com", full_name="Jeff Chipman", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(token_subject_for_user(user))
    assert decode_access_token(token) == f"user:{user.id}"

    user.username = "jeff.google@example.com"
    session.add(user)
    session.commit()

    resolved = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), session)
    assert resolved.id == user.id
    assert resolved.username == "jeff.google@example.com"


def test_refresh_accepts_existing_username_tokens_and_mints_user_id_tokens() -> None:
    session = _session()
    user = User(username="jeff@example.com", full_name="Jeff Chipman", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()
    session.refresh(user)

    response = refresh(_request(), RefreshRequest(refresh_token=create_refresh_token(user.username)), session)

    assert response.user.id == user.id
    assert decode_access_token(response.access_token) == f"user:{user.id}"


def test_staff_custom_scoring_formulas_are_saved_per_user() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    organizer = User(username="organizer@example.com", full_name="Organizer", role="organizer", password_hash="hash")
    pilot = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    session.add_all([admin, organizer, pilot])
    session.commit()
    session.refresh(admin)
    session.refresh(organizer)
    session.refresh(pilot)

    saved = save_custom_scoring_formulas(
        CustomScoringFormulaList(
            formulas=[
                CustomScoringFormula(value="custom_local", label="Local Rules", preset={"nominal_distance_km": 42}),
                CustomScoringFormula(value="custom_local", label="Duplicate", preset={}),
            ]
        ),
        admin,
        session,
    )

    assert [formula.label for formula in saved.formulas] == ["Local Rules"]
    assert list_custom_scoring_formulas(admin).formulas[0].preset == {"nominal_distance_km": 42}
    assert list_custom_scoring_formulas(organizer).formulas == []
    with pytest.raises(HTTPException) as caught:
        list_custom_scoring_formulas(pilot)
    assert caught.value.status_code == 403


def test_passkey_registration_and_passwordless_login_share_existing_tokens() -> None:
    session = _session()
    user = User(username="passkey@example.com", full_name="Pass Key", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()
    session.refresh(user)

    options = passkey_registration_options(_request(), user, session)
    assert options.public_key["authenticatorSelection"]["residentKey"] == "required"
    assert options.public_key["authenticatorSelection"]["userVerification"] == "required"

    with patch(
        "app.routers.auth.verify_registration_response",
        return_value=SimpleNamespace(
            credential_id=b"credential-one",
            credential_public_key=b"public-key",
            sign_count=0,
            aaguid="00000000-0000-0000-0000-000000000000",
        ),
    ) as verify_registration:
        registered = passkey_registration_verify(
            _request(),
            PasskeyVerifyRequest(
                ceremony_id=options.ceremony_id,
                credential={"id": "Y3JlZGVudGlhbC1vbmU", "response": {"transports": ["internal"]}},
                name="Windows Hello",
            ),
            user,
            session,
        )
    assert verify_registration.call_args.kwargs["expected_rp_id"] == "localhost"
    assert "android:apk-key-hash:K-eZP7LKduP4a_T6MeG0mShQPpYAnjFU7L1N03eRDe8" in verify_registration.call_args.kwargs["expected_origin"]
    assert verify_registration.call_args.kwargs["require_user_verification"] is True

    assert registered.name == "Windows Hello"
    assert registered.transports == ["internal"]
    login_options = passkey_login_options(_request(), session)
    with patch(
        "app.routers.auth.verify_authentication_response",
        return_value=SimpleNamespace(credential_id=b"credential-one", new_sign_count=7),
    ) as verify_authentication:
        response = passkey_login_verify(
            _request(),
            PasskeyVerifyRequest(
                ceremony_id=login_options.ceremony_id,
                credential={"id": "Y3JlZGVudGlhbC1vbmU", "response": {}},
            ),
            session,
        )
    assert verify_authentication.call_args.kwargs["credential_current_sign_count"] == 0
    assert verify_authentication.call_args.kwargs["require_user_verification"] is True

    assert response.user.id == user.id
    assert decode_access_token(response.access_token) == f"user:{user.id}"
    stored = session.scalar(select(PasskeyCredential))
    assert stored.sign_count == 7
    assert stored.last_used_at is not None
    assert list_passkeys(user, session)[0].name == "Windows Hello"

    with pytest.raises(HTTPException) as replay:
        passkey_login_verify(
            _request(),
            PasskeyVerifyRequest(
                ceremony_id=login_options.ceremony_id,
                credential={"id": "Y3JlZGVudGlhbC1vbmU", "response": {}},
            ),
            session,
        )
    assert replay.value.status_code == 400


def test_passkey_management_is_scoped_to_owner() -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner", role="pilot", password_hash="hash")
    other = User(username="other@example.com", full_name="Other", role="pilot", password_hash="hash")
    session.add_all([owner, other])
    session.flush()
    passkey = PasskeyCredential(
        user_id=owner.id,
        credential_id="credential",
        public_key=b"key",
        user_handle=b"handle",
        name="Phone",
    )
    session.add(passkey)
    session.commit()

    with pytest.raises(HTTPException) as rename_error:
        rename_passkey(passkey.id, PasskeyRenameRequest(name="Mine"), other, session)
    assert rename_error.value.status_code == 404
    with pytest.raises(HTTPException) as delete_error:
        delete_passkey(passkey.id, other, session)
    assert delete_error.value.status_code == 404

    renamed = rename_passkey(passkey.id, PasskeyRenameRequest(name="  Pixel  "), owner, session)
    assert renamed.name == "Pixel"
    delete_passkey(passkey.id, owner, session)
    assert session.get(PasskeyCredential, passkey.id) is None


def test_passkey_registration_options_exclude_all_existing_credentials() -> None:
    session = _session()
    user = User(username="multi@example.com", full_name="Multiple Keys", role="pilot", password_hash="hash")
    session.add(user)
    session.flush()
    user_handle = b"stable-user-handle"
    session.add_all(
        [
            PasskeyCredential(
                user_id=user.id,
                credential_id="Y3JlZGVudGlhbC1vbmU",
                public_key=b"key-one",
                user_handle=user_handle,
                name="Laptop",
            ),
            PasskeyCredential(
                user_id=user.id,
                credential_id="Y3JlZGVudGlhbC10d28",
                public_key=b"key-two",
                user_handle=user_handle,
                name="Phone",
            ),
        ]
    )
    session.commit()

    options = passkey_registration_options(_request(), user, session)

    assert len(options.public_key["excludeCredentials"]) == 2
    assert {item["id"] for item in options.public_key["excludeCredentials"]} == {
        "Y3JlZGVudGlhbC1vbmU",
        "Y3JlZGVudGlhbC10d28",
    }
    assert [item.name for item in list_passkeys(user, session)] == ["Phone", "Laptop"]


@pytest.mark.parametrize("reason", ["Unexpected client data origin", "Unexpected RP ID hash"])
def test_passkey_login_rejects_invalid_origin_or_rp(reason: str) -> None:
    session = _session()
    user = User(username="origin@example.com", full_name="Origin Check", role="pilot", password_hash="hash")
    session.add(user)
    session.flush()
    session.add(
        PasskeyCredential(
            user_id=user.id,
            credential_id="credential",
            public_key=b"key",
            user_handle=b"handle",
            name="Phone",
        )
    )
    session.commit()
    options = passkey_login_options(_request(), session)

    with patch(
        "app.routers.auth.verify_authentication_response",
        side_effect=WebAuthnException(reason),
    ):
        with pytest.raises(HTTPException) as rejected:
            passkey_login_verify(
                _request(),
                PasskeyVerifyRequest(
                    ceremony_id=options.ceremony_id,
                    credential={"id": "credential", "response": {}},
                ),
                session,
            )

    assert rejected.value.status_code == 401
    assert rejected.value.detail == "Passkey sign-in failed"


def test_expired_passkey_challenge_and_inactive_account_are_rejected() -> None:
    session = _session()
    user = User(
        username="inactive@example.com",
        full_name="Inactive",
        role="pilot",
        password_hash="hash",
        is_active=False,
    )
    session.add(user)
    session.flush()
    session.add_all(
        [
            PasskeyCredential(
                user_id=user.id,
                credential_id="credential",
                public_key=b"key",
                user_handle=b"handle",
                name="Phone",
            ),
            PasskeyChallenge(
                id="expired",
                challenge=b"challenge",
                purpose="login",
                expires_at=datetime(2020, 1, 1, tzinfo=UTC),
            ),
        ]
    )
    session.commit()

    with pytest.raises(HTTPException) as expired_error:
        passkey_login_verify(
            _request(),
            PasskeyVerifyRequest(ceremony_id="expired", credential={"id": "credential", "response": {}}),
            session,
        )
    assert expired_error.value.status_code == 400

    options = passkey_login_options(_request(), session)
    with pytest.raises(HTTPException) as inactive_error:
        passkey_login_verify(
            _request(),
            PasskeyVerifyRequest(ceremony_id=options.ceremony_id, credential={"id": "credential", "response": {}}),
            session,
        )
    assert inactive_error.value.status_code == 401


def test_backfill_user_subject_pilot_links_repairs_user_only_tracking_rows() -> None:
    session = _session()
    pilot = Pilot(first_name="Jeff", last_name="Chipman", email="jeff@example.com")
    session.add(pilot)
    session.flush()
    user = User(username="jeff@example.com", full_name="Jeff Chipman", role="pilot", profile_type="pilot", pilot_id=pilot.id)
    session.add(user)
    session.flush()
    position = LivePosition(
        user_id=user.id,
        pilot_id=None,
        lat=39.09632,
        lon=-75.89077,
        timestamp=datetime.now(UTC),
        source="app",
    )
    tracking = TrackingSession(user_id=user.id, pilot_id=None, position_count=1)
    session.add_all([position, tracking])
    session.commit()

    changed = backfill_user_subject_pilot_links(session, user)
    session.commit()

    assert changed == 2
    session.refresh(position)
    session.refresh(tracking)
    assert position.pilot_id == pilot.id
    assert tracking.pilot_id == pilot.id


def test_register_links_existing_pilot_by_email() -> None:
    session = _session()
    pilot = Pilot(first_name="Casey", last_name="Flyer", email="casey@example.com", competition_number="42")
    session.add(pilot)
    session.commit()

    with patch("app.routers.auth.hash_password", return_value="hashed-password"):
        response = register(
            _request(),
            RegisterRequest(
                first_name="Casey",
                last_name="Flyer",
                email="casey@example.com",
                password="secret123",
            ),
            session,
        )

    user = session.query(User).filter(User.username == "casey@example.com").one()
    assert response.user.username == "casey@example.com"
    assert response.user.pilot_id == pilot.id
    assert user.pilot_id == pilot.id


def test_register_links_existing_pilot_by_competition_number_without_creating_duplicate() -> None:
    session = _session()
    event = Event(name="HC 2026", location="Myles", starts_on=date(2026, 5, 29), ends_on=date(2026, 6, 6), timezone="UTC")
    pilot = Pilot(first_name="Leonardo", last_name="Ortiz", email=None, competition_number="28")
    session.add_all([event, pilot])
    session.flush()
    session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
    session.commit()

    with patch("app.routers.auth.hash_password", return_value="hashed-password"):
        response = register(
            _request(),
            RegisterRequest(
                first_name="Leonardo",
                last_name="Ortiz",
                email="leo@example.com",
                password="secret123",
                competition_number="28",
            ),
            session,
        )

    user = session.query(User).filter(User.username == "leo@example.com").one()
    session.refresh(pilot)
    assert response.user.pilot_id == pilot.id
    assert user.pilot_id == pilot.id
    assert pilot.email == "leo@example.com"
    assert session.query(Pilot).count() == 1


def test_register_organizer_creates_user_without_pilot() -> None:
    session = _session()

    with patch("app.routers.auth.hash_password", return_value="hashed-password"):
        response = register(
            _request(),
            RegisterRequest(
                first_name="Olivia",
                last_name="Meet",
                email="organizer@example.com",
                password="secret123",
                account_role="organizer",
            ),
            session,
        )

    user = session.query(User).filter(User.username == "organizer@example.com").one()
    assert response.user.role == "organizer"
    assert response.user.pilot_id is None
    assert user.profile_type == "driver"


def test_assign_existing_pilot_adds_them_to_event() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Robin", last_name="Wing", email="robin@example.com")
    event = Event(name="Spring Open", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    session.add_all([admin, pilot, event])
    session.commit()

    response = assign_existing_pilot(event.id, pilot.id, admin, session)

    assert response.id == pilot.id
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == pilot.id)) is not None


def test_pilot_class_is_event_specific_and_rescores_existing_tasks() -> None:
    session = _session()
    admin = User(username="admin-class@example.com", full_name="Admin", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Class", last_name="Pilot")
    first_event = Event(name="Mixed", location="Ridge", starts_on=date(2026, 7, 1), ends_on=date(2026, 7, 2), timezone="UTC")
    second_event = Event(name="Open", location="Ridge", starts_on=date(2026, 7, 3), ends_on=date(2026, 7, 4), timezone="UTC")
    session.add_all([admin, pilot, first_event, second_event])
    session.flush()
    session.add_all([
        EventPilot(event_id=first_event.id, pilot_id=pilot.id),
        EventPilot(event_id=second_event.id, pilot_id=pilot.id),
    ])
    session.commit()

    with patch("app.routers.pilots.rescore_scored_event_tasks", return_value=2) as rescore:
        response = update_event_pilot_class(first_event.id, pilot.id, PilotClassUpdate(pilot_class="single_surface"), admin, session)

    assert response.pilot_class == "single_surface"
    assert session.scalar(select(EventPilot.pilot_class).where(EventPilot.event_id == first_event.id, EventPilot.pilot_id == pilot.id)) == "single_surface"
    assert session.scalar(select(EventPilot.pilot_class).where(EventPilot.event_id == second_event.id, EventPilot.pilot_id == pilot.id)) == "modern_topless"
    rescore.assert_called_once_with(session, first_event.id)


def test_mixed_class_normalize_setting_rescores_existing_tasks() -> None:
    session = _session()
    admin = User(username="admin-normalize@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Mixed",
        location="Ridge",
        starts_on=date(2026, 7, 1),
        ends_on=date(2026, 7, 2),
        timezone="UTC",
        normalize_1000_before_day_quality=False,
        penalties_json={
            "handicap": {
                "enabled": True,
                "multipliers": {
                    "modern_topless": 1,
                    "high_performance_kingpost": 1,
                    "intermediate_kingpost": 1,
                    "single_surface": 1,
                },
            }
        },
    )
    session.add_all([admin, event])
    session.commit()
    payload = EventCreate(
        name=event.name,
        location=event.location,
        starts_on=event.starts_on,
        ends_on=event.ends_on,
        timezone=event.timezone,
        normalize_1000_before_day_quality=True,
        penalties_json=event.penalties_json,
    )

    with patch("app.routers.events.rescore_scored_event_tasks", return_value=3) as rescore:
        update_event(event.id, payload, admin, session)

    rescore.assert_called_once_with(session, event.id)


def test_create_pilot_with_email_creates_email_login_user() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    event = Event(name="Spring Open", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    session.add_all([admin, event])
    session.commit()

    response = create_pilot(
        event.id,
        PilotUpsert(
            first_name="New",
            last_name="Pilot",
            email="New.Pilot@Example.com",
            nation="US",
            competition_number="12",
            civl_id=None,
        ),
        admin,
        session,
    )

    user = session.scalar(select(User).where(User.username == "new.pilot@example.com"))
    assert response.email == "new.pilot@example.com"
    assert response.portal_username == "new.pilot@example.com"
    assert user is not None
    assert user.pilot_id == response.id
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == response.id)) is not None


def test_update_portal_only_pilot_to_email_renames_login() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Alex", last_name="Pilot", email=None)
    session.add_all([admin, pilot])
    session.flush()
    portal_user = User(username="alex-pilot", full_name="Alex Pilot", role="pilot", pilot_id=pilot.id, password_hash="hash")
    session.add(portal_user)
    session.commit()

    response = update_pilot(
        pilot.id,
        PilotUpsert(
            first_name="Alex",
            last_name="Pilot",
                email="Alex@Example.com",
            nation=None,
            competition_number=None,
            civl_id=None,
        ),
        admin,
        session,
    )

    session.refresh(portal_user)
    assert response.id == pilot.id
    assert response.email == "alex@example.com"
    assert response.portal_username == "alex@example.com"
    assert portal_user.username == "alex@example.com"
    assert portal_user.pilot_id == pilot.id
    assert portal_user.is_active is True


def test_assign_existing_pilot_links_matching_email_user() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Alex", last_name="Pilot", email="alex@example.com")
    generated_user = User(username="alex-pilot", full_name="Alex Pilot", role="pilot", pilot_id=None, password_hash="hash")
    email_user = User(username="alex@example.com", full_name="Alex Pilot", role="pilot", pilot_id=None, password_hash="hash")
    event = Event(name="HC 2025 - myles", location="Myles", starts_on=date(2026, 5, 7), ends_on=date(2026, 5, 9), timezone="UTC")
    session.add_all([admin, pilot, generated_user, email_user, event])
    session.flush()
    generated_user.pilot_id = pilot.id
    session.commit()

    response = assign_existing_pilot(event.id, pilot.id, admin, session)

    session.refresh(email_user)
    session.refresh(generated_user)
    assert response.portal_username == "alex@example.com"
    assert email_user.pilot_id == pilot.id
    assert generated_user.pilot_id is None
    assert generated_user.is_active is False
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == pilot.id)) is not None


def test_people_directory_uses_active_users_as_source_of_truth() -> None:
    session = _session()
    staff = User(username="staff@example.com", full_name="Staff User", role="admin", password_hash="hash")
    canonical = Pilot(first_name="Knut", last_name="Pilot", email="knut@example.com", nation="NO", competition_number="77", civl_id="CIVL-KNUT")
    admin_profile = Pilot(first_name="Ada", last_name="Admin", email="ada@example.com")
    organizer_profile = Pilot(first_name="Olivia", last_name="Organizer", email="olivia@example.com")
    duplicate = Pilot(first_name="Knut", last_name="Pilot", email="knut@example.com", nation="NO", competition_number="88")
    unregistered = Pilot(first_name="Knut", last_name="Historical", email="old-knut@example.com", nation="NO", competition_number="99")
    inactive_profile = Pilot(first_name="Ina", last_name="Inactive", email="ina@example.com")
    event = Event(name="Spring Open", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    session.add_all([staff, canonical, admin_profile, organizer_profile, duplicate, unregistered, inactive_profile, event])
    session.flush()
    session.add_all(
        [
            User(username="knut@example.com", full_name="Knut Pilot", role="pilot", pilot_id=canonical.id, password_hash="hash"),
            User(username="ada@example.com", full_name="Ada Admin", role="admin", pilot_id=admin_profile.id, password_hash="hash"),
            User(username="olivia@example.com", full_name="Olivia Organizer", role="organizer", pilot_id=organizer_profile.id, password_hash="hash"),
            User(username="ina@example.com", full_name="Ina Inactive", role="pilot", pilot_id=inactive_profile.id, is_active=False, password_hash="hash"),
        ]
    )
    session.commit()

    all_results = list_people(admin=staff, session=session)
    search_results = list_people(search="knut", admin=staff, session=session)
    admin_results = list_people(search="ada", admin=staff, session=session)
    organizer_results = list_people(search="olivia", admin=staff, session=session)
    inactive_results = list_people(search="ina", admin=staff, session=session)
    civl_results = list_people(search="civl-knut", admin=staff, session=session)
    nation_results = list_people(search="no", admin=staff, session=session)
    assigned = assign_existing_pilot(event.id, admin_profile.id, staff, session)

    assert [pilot.id for pilot in all_results] == [admin_profile.id, organizer_profile.id, canonical.id]
    assert [pilot.id for pilot in search_results] == [canonical.id]
    assert [pilot.id for pilot in admin_results] == [admin_profile.id]
    assert [pilot.id for pilot in organizer_results] == [organizer_profile.id]
    assert inactive_results == []
    assert [pilot.id for pilot in civl_results] == [canonical.id]
    assert [pilot.id for pilot in nation_results] == [canonical.id]
    assert assigned.id == admin_profile.id
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == admin_profile.id)) is not None


def test_deleted_user_disappears_from_people_directory_but_event_roster_remains() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Knut", last_name="Pilot", email="knut@example.com", competition_number="77")
    event = Event(name="Spring Open", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    session.add_all([admin, pilot, event])
    session.flush()
    user = User(username="knut@example.com", full_name="Knut Pilot", role="pilot", pilot_id=pilot.id, password_hash="hash")
    session.add_all([user, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.commit()

    assert [entry.id for entry in list_people(search="knut", admin=admin, session=session)] == [pilot.id]

    delete_user_account(user.id, admin, session)

    assert list_people(search="knut", admin=admin, session=session) == []
    assert [entry.id for entry in list_pilots(event.id, admin, session)] == [pilot.id]
    assert session.get(Pilot, pilot.id) is not None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == pilot.id)) is not None


def test_assign_existing_pilot_uses_canonical_directory_id_for_already_assigned_state() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Knut", last_name="Pilot", email="knut@example.com", competition_number="77")
    event = Event(name="Spring Open", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    session.add_all([admin, pilot, event])
    session.flush()
    session.add(User(username="knut@example.com", full_name="Knut Pilot", role="pilot", pilot_id=pilot.id, password_hash="hash"))
    session.commit()

    assigned = assign_existing_pilot(event.id, pilot.id, admin, session)
    directory = list_people(search="knut", admin=admin, session=session)
    roster = list_pilots(event.id, admin, session)

    assert assigned.id == pilot.id
    assert [entry.id for entry in directory] == [pilot.id]
    assert [entry.id for entry in roster] == [pilot.id]


def test_startup_repair_moves_duplicate_event_membership_to_email_identity() -> None:
    session = _session()
    email_pilot = Pilot(first_name="Alex", last_name="Pilot", email="alex@example.com")
    roster_pilot = Pilot(first_name="Alex", last_name="Pilot", email="alex@example.com")
    event = Event(
        name="HC 2025 - myles",
        location="Myles",
        starts_on=date(2026, 5, 7),
        ends_on=date(2026, 5, 9),
        timezone="UTC",
        visibility="participants",
    )
    session.add_all([email_pilot, roster_pilot, event])
    session.flush()
    email_pilot_id = email_pilot.id
    roster_pilot_id = roster_pilot.id
    email_user = User(username="alex@example.com", full_name="Alex Pilot", role="pilot", pilot_id=email_pilot.id, password_hash="hash")
    generated_user = User(username="alex-pilot", full_name="Alex Pilot", role="pilot", pilot_id=roster_pilot.id, password_hash="hash")
    session.add_all([email_user, generated_user, EventPilot(event_id=event.id, pilot_id=roster_pilot.id)])
    session.commit()

    repair_pilot_email_identities(session)
    session.commit()

    session.refresh(email_user)
    session.refresh(generated_user)
    assert email_user.pilot_id == email_pilot_id
    assert generated_user.pilot_id is None
    assert generated_user.is_active is False
    assert session.get(Pilot, roster_pilot_id) is None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == email_pilot_id)) is not None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == roster_pilot_id)) is None
    assert {event.name for event in list_events(user=email_user, session=session)} == {"HC 2025 - myles"}


def test_merge_pilots_moves_live_identity_to_event_roster_pilot() -> None:
    session = _session()
    roster_pilot = Pilot(first_name="Jeff", last_name="Chipman", email=None)
    duplicate_pilot = Pilot(first_name="Jeff", last_name="Chipman", email="jeff@example.com")
    event = Event(name="HC 2026", location="Myles", starts_on=date(2026, 5, 29), ends_on=date(2026, 6, 6), timezone="UTC")
    session.add_all([roster_pilot, duplicate_pilot, event])
    session.flush()
    user = User(username="jeff@example.com", full_name="Jeff Chipman", role="pilot", pilot_id=duplicate_pilot.id, password_hash="hash")
    task = Task(event_id=event.id, name="Practice Day", status="published", task_date=date(2026, 5, 29))
    session.add_all([user, task])
    session.flush()
    session.add_all(
        [
            EventPilot(event_id=event.id, pilot_id=roster_pilot.id),
            EventPilot(event_id=event.id, pilot_id=duplicate_pilot.id),
            LivePosition(pilot_id=duplicate_pilot.id, user_id=user.id, lat=40.0, lon=-75.0, timestamp=datetime(2026, 5, 28, 12, 0, tzinfo=UTC)),
            TrackingSession(pilot_id=duplicate_pilot.id, user_id=user.id, task_id=None),
        ]
    )
    session.flush()
    session.add_all(
        [
            TaskScoringInput(task_id=task.id, pilot_id=roster_pilot.id),
            TaskScoringInput(task_id=task.id, pilot_id=duplicate_pilot.id),
            ScoreResult(task_id=task.id, pilot_id=roster_pilot.id, score_points=100),
            ScoreResult(task_id=task.id, pilot_id=duplicate_pilot.id, score_points=90),
        ]
    )
    session.commit()
    duplicate_id = duplicate_pilot.id
    roster_id = roster_pilot.id

    result = merge_pilots(session, source_pilot_id=duplicate_id, target_pilot_id=roster_id)
    session.commit()

    session.refresh(user)
    assert user.pilot_id == roster_id
    assert session.get(Pilot, duplicate_id) is None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == duplicate_id)) is None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == roster_id)) is not None
    assert session.scalar(select(LivePosition).where(LivePosition.pilot_id == roster_id)) is not None
    assert session.scalar(select(TrackingSession).where(TrackingSession.pilot_id == roster_id)) is not None
    assert session.scalar(select(TaskScoringInput).where(TaskScoringInput.task_id == task.id, TaskScoringInput.pilot_id == duplicate_id)) is None
    assert session.scalar(select(ScoreResult).where(ScoreResult.task_id == task.id, ScoreResult.pilot_id == duplicate_id)) is None
    assert result.deleted_conflicts["event_pilots"] == 1
    assert result.deleted_conflicts["task_scoring_inputs"] == 1
    assert result.deleted_conflicts["score_results"] == 1


def test_claim_pilot_merges_existing_duplicate_user_pilot() -> None:
    session = _session()
    roster_pilot = Pilot(first_name="Mick", last_name="Howard", competition_number="42")
    duplicate_pilot = Pilot(first_name="Mick", last_name="Howard", email="mick@example.com")
    event = Event(name="HC 2026", location="Myles", starts_on=date(2026, 5, 29), ends_on=date(2026, 6, 6), timezone="UTC")
    session.add_all([roster_pilot, duplicate_pilot, event])
    session.flush()
    user = User(username="mick@example.com", full_name="Mick Howard", role="pilot", pilot_id=duplicate_pilot.id, password_hash="hash")
    session.add_all(
        [
            user,
            EventPilot(event_id=event.id, pilot_id=roster_pilot.id),
            LivePosition(pilot_id=duplicate_pilot.id, user_id=user.id, lat=40.0, lon=-75.0, timestamp=datetime(2026, 5, 28, 12, 0, tzinfo=UTC)),
        ]
    )
    session.commit()
    roster_id = roster_pilot.id
    duplicate_id = duplicate_pilot.id

    response = claim_pilot(PilotClaimRequest(pilot_id=roster_id, competition_number="42"), user, session)

    assert response.pilot_id == roster_id
    session.refresh(user)
    assert user.pilot_id == roster_id
    assert session.get(Pilot, duplicate_id) is None
    assert session.scalar(select(LivePosition).where(LivePosition.pilot_id == roster_id)) is not None


def test_additional_email_login_and_merges_matching_imported_pilot() -> None:
    session = _session()
    roster_pilot = Pilot(first_name="James", last_name="Messina", email="james@example.com")
    user_pilot = Pilot(first_name="Jim", last_name="Messina", email="jim@example.com")
    event = Event(name="HC 2026", location="Myles", starts_on=date(2026, 5, 29), ends_on=date(2026, 6, 6), timezone="UTC")
    session.add_all([roster_pilot, user_pilot, event])
    session.flush()
    user = User(username="jim@example.com", full_name="Jim Messina", role="pilot", pilot_id=user_pilot.id, password_hash="hashed")
    session.add_all(
        [
            user,
            EventPilot(event_id=event.id, pilot_id=roster_pilot.id),
            LivePosition(pilot_id=roster_pilot.id, user_id=None, lat=40.0, lon=-75.0, timestamp=datetime(2026, 5, 28, 12, 0, tzinfo=UTC)),
        ]
    )
    session.commit()

    add_email(UserEmailCreate(email="James@Example.com"), user, session)

    session.refresh(user)
    assert user.pilot_id == user_pilot.id
    assert session.get(Pilot, roster_pilot.id) is None
    assert session.scalar(select(UserEmail).where(UserEmail.user_id == user.id, UserEmail.email == "james@example.com")) is not None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == user_pilot.id)) is not None
    assert session.scalar(select(LivePosition).where(LivePosition.pilot_id == user_pilot.id)) is not None

    with patch("app.routers.auth.verify_password", return_value=True):
        response = login(_request(), LoginRequest(username="james@example.com", password="secret123"), session)

    assert response.user.id == user.id


def test_startup_repair_merges_jim_and_james_messina_user_records() -> None:
    session = _session()
    jim_pilot = Pilot(first_name="Jim", last_name="Messina", email="jim@example.com")
    james_pilot = Pilot(first_name="James", last_name="Messina", email="james@example.com")
    event = Event(name="HC 2026", location="Myles", starts_on=date(2026, 5, 29), ends_on=date(2026, 6, 6), timezone="UTC", is_public_tracking=True)
    session.add_all([jim_pilot, james_pilot, event])
    session.flush()
    jim_user = User(username="jim@example.com", full_name="Jim Messina", role="pilot", pilot_id=jim_pilot.id, password_hash="hash")
    james_user = User(username="james@example.com", full_name="James Messina", role="pilot", pilot_id=james_pilot.id, password_hash="hash")
    session.add_all([jim_user, james_user])
    session.flush()
    session.add_all(
        [
            EventPilot(event_id=event.id, pilot_id=jim_pilot.id),
            EventPilot(event_id=event.id, pilot_id=james_pilot.id),
            LivePosition(pilot_id=james_pilot.id, user_id=james_user.id, lat=40.0, lon=-75.0, timestamp=datetime(2026, 5, 28, 12, 0, tzinfo=UTC)),
            TrackingSession(pilot_id=james_pilot.id, user_id=james_user.id),
        ]
    )
    session.commit()
    jim_id = jim_pilot.id
    james_id = james_pilot.id

    changed = repair_pilot_email_identities(session)
    session.commit()

    session.refresh(jim_user)
    session.refresh(james_user)
    assert changed > 0
    assert jim_user.is_active is True
    assert jim_user.pilot_id == jim_id
    assert jim_user.full_name == "Jim Messina"
    assert james_user.is_active is False
    assert james_user.pilot_id is None
    assert session.get(Pilot, james_id) is None
    assert session.scalar(select(UserEmail).where(UserEmail.user_id == jim_user.id, UserEmail.email == "james@example.com")) is not None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == jim_id)) is not None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == james_id)) is None
    assert session.scalar(select(LivePosition).where(LivePosition.pilot_id == jim_id, LivePosition.user_id == jim_user.id)) is not None
    assert session.scalar(select(TrackingSession).where(TrackingSession.pilot_id == jim_id, TrackingSession.user_id == jim_user.id)) is not None


def test_startup_repair_moves_mesh_device_pointer_without_unique_violation() -> None:
    session = _session()
    jim_pilot = Pilot(first_name="Jim", last_name="Messina", email="jim@example.com")
    james_pilot = Pilot(first_name="James", last_name="Messina", email="james@example.com")
    session.add_all([jim_pilot, james_pilot])
    session.flush()
    jim_user = User(username="jim@example.com", full_name="Jim Messina", role="pilot", pilot_id=jim_pilot.id, password_hash="hash")
    james_user = User(username="james@example.com", full_name="James Messina", role="pilot", pilot_id=james_pilot.id, password_hash="hash", mesh_device_id="!4671f393")
    session.add_all([jim_user, james_user])
    session.flush()
    session.add(MeshDevice(owner_user_id=james_user.id, device_id="!tracker", label="Messina tracker", purpose="tracking"))
    session.commit()

    changed = repair_pilot_email_identities(session)
    session.commit()

    session.refresh(jim_user)
    session.refresh(james_user)
    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!tracker"))
    assert changed > 0
    assert jim_user.mesh_device_id == "!4671f393"
    assert james_user.is_active is False
    assert device is not None
    assert device.owner_user_id == jim_user.id


def test_update_settings_updates_pilot_profile_and_username_email() -> None:
    session = _session()
    pilot = Pilot(first_name="Robin", last_name="Wing", email="robin@example.com", nation="US")
    previous_profile_type_updated_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    user = User(
        username="robin@example.com",
        full_name="Robin Wing",
        role="pilot",
        password_hash="hash",
        pilot_id=None,
        profile_type_updated_at=previous_profile_type_updated_at,
    )
    session.add_all([pilot, user])
    session.commit()
    user.pilot_id = pilot.id
    session.commit()

    response = update_settings(
        AccountSettingsUpdate(
            username="pilot@example.com",
            full_name="Robin Wing",
            profile_type="driver",
            email="pilot@example.com",
            first_name="Robin",
            last_name="Wing",
            nation="usa",
            competition_number="77",
            civl_id="CIVL-77",
        ),
        user,
        session,
    )

    session.refresh(user)
    session.refresh(pilot)
    assert response.username == "pilot@example.com"
    assert response.profile_type == "driver"
    assert _utc(response.profile_type_updated_at) > previous_profile_type_updated_at
    assert user.username == "pilot@example.com"
    assert user.profile_type == "driver"
    assert _utc(user.profile_type_updated_at) > previous_profile_type_updated_at
    assert pilot.email == "pilot@example.com"
    assert pilot.nation == "USA"
    assert pilot.competition_number == "77"


def test_update_settings_preserves_legacy_admin_username_without_email() -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin User", role="admin", password_hash="hash", profile_type="driver")
    session.add(admin)
    session.commit()

    response = update_settings(
        AccountSettingsUpdate(
            username="admin",
            full_name="Admin User",
            profile_type="driver",
            email=None,
        ),
        admin,
        session,
    )

    session.refresh(admin)
    assert response.username == "admin"
    assert admin.username == "admin"


def test_mesh_device_auto_registration_creates_tracking_inventory() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    response = register_mesh_device(MeshDeviceRegister(mesh_device_id="!ABCDEF12"), user, session)

    session.refresh(user)
    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!abcdef12"))
    assert response["mesh_device_id"] == "!abcdef12"
    assert user.mesh_device_id == "!abcdef12"
    assert device is not None
    assert device.owner_user_id == user.id
    assert device.purpose == "tracking"


def test_mesh_device_registration_normalizes_bare_hex_node_id() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    response = register_mesh_device(MeshDeviceRegister(mesh_device_id="435A8B00"), user, session)

    session.refresh(user)
    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!435a8b00"))
    assert response["mesh_device_id"] == "!435a8b00"
    assert user.mesh_device_id == "!435a8b00"
    assert device is not None


def test_nontracking_mesh_device_does_not_replace_tracking_mirror() -> None:
    session = _session()
    user = User(username="driver@example.com", full_name="Driver User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    register_mesh_device(MeshDeviceRegister(mesh_device_id="!tracker"), user, session)
    create_mesh_device(
        MeshDeviceCreate(device_id="!driverwifi", label="Driver Gateway", purpose="driver_wifi"),
        user,
        session,
    )

    session.refresh(user)
    driver_device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!driverwifi"))
    assert user.mesh_device_id == "!tracker"
    assert driver_device is not None
    assert driver_device.purpose == "driver_wifi"


def test_mesh_device_update_can_rename_tracking_device_and_mirror() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    register_mesh_device(MeshDeviceRegister(mesh_device_id="!tracker"), user, session)

    response = update_mesh_device(
        "!tracker",
        MeshDeviceUpdate(device_id="!NEWTRACK", label="Primary tracker", purpose="tracking"),
        user,
        session,
    )

    session.refresh(user)
    old_device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!tracker"))
    new_device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!newtrack"))
    assert response.device_id == "!newtrack"
    assert user.mesh_device_id == "!newtrack"
    assert old_device is None
    assert new_device is not None
    assert new_device.label == "Primary tracker"
    assert new_device.purpose == "tracking"


def test_mesh_device_update_rejects_duplicate_device_id() -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner User", role="pilot", password_hash="hash")
    other = User(username="other@example.com", full_name="Other User", role="pilot", password_hash="hash")
    session.add_all([owner, other])
    session.commit()

    create_mesh_device(MeshDeviceCreate(device_id="!mine", label="Mine", purpose="driver_mesh"), owner, session)
    create_mesh_device(MeshDeviceCreate(device_id="!taken", label="Taken", purpose="driver_mesh"), other, session)

    try:
        update_mesh_device("!mine", MeshDeviceUpdate(device_id="!taken"), owner, session)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
    else:
        raise AssertionError("Expected duplicate device ID update to be rejected")


def test_admin_user_payload_includes_owned_mesh_devices() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id="!tracker")
    session.add_all([admin, user])
    session.flush()
    session.add_all(
        [
            MeshDevice(owner_user_id=user.id, device_id="!tracker", label="Tracker", purpose="tracking"),
            MeshDevice(owner_user_id=user.id, device_id="!relay", label="Relay", purpose="relay"),
        ]
    )
    session.commit()

    response = list_users(admin, session)
    pilot_payload = next(item for item in response if item.id == user.id)

    assert pilot_payload.mesh_device_id == "!tracker"
    assert [device.device_id for device in pilot_payload.mesh_devices] == ["!relay", "!tracker"]
    assert {device.device_id: device.is_pilot_tracker for device in pilot_payload.mesh_devices} == {
        "!relay": False,
        "!tracker": True,
    }


def test_settings_mesh_device_update_is_reflected_in_admin_user_payload() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id="!tahoe")
    session.add_all([admin, user])
    session.flush()
    session.add(MeshDevice(owner_user_id=user.id, device_id="!tahoe", label="Tahoe Supreme", purpose="tracking"))
    session.commit()

    update_mesh_device(
        "!tahoe",
        MeshDeviceUpdate(device_id="!tahoe", label="Tahoe Supreme", purpose="driver_wifi"),
        user,
        session,
    )

    settings_device = list_mesh_devices(user, session)[0]
    admin_payload = next(item for item in list_users(admin, session) if item.id == user.id)
    admin_device = admin_payload.mesh_devices[0]

    assert settings_device.id == admin_device.id
    assert settings_device.device_id == admin_device.device_id == "!tahoe"
    assert settings_device.label == admin_device.label == "Tahoe Supreme"
    assert settings_device.purpose == admin_device.purpose == "driver_wifi"
    assert settings_device.is_pilot_tracker is False
    assert admin_device.is_pilot_tracker is False
    assert admin_payload.mesh_device_id is None


def test_admin_can_select_switch_and_clear_user_pilot_tracker() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id="!tracker")
    session.add_all([admin, user])
    session.flush()
    session.add_all(
        [
            MeshDevice(owner_user_id=user.id, device_id="!tracker", label="Tracker", purpose="tracking"),
            MeshDevice(owner_user_id=user.id, device_id="!backup", label="Backup", purpose="relay"),
        ]
    )
    session.commit()

    selected = admin_set_user_tracking_mesh_device(
        user.id,
        MeshDeviceRegister(mesh_device_id="!backup"),
        admin,
        session,
    )

    session.refresh(user)
    old_tracker = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!tracker"))
    backup = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!backup"))
    assert selected.mesh_device_id == "!backup"
    assert user.mesh_device_id == "!backup"
    assert old_tracker is not None and old_tracker.purpose == "tracking"
    assert backup is not None and backup.purpose == "tracking"
    assert {device.device_id: device.is_pilot_tracker for device in selected.mesh_devices} == {
        "!backup": True,
        "!tracker": False,
    }

    cleared = admin_set_user_tracking_mesh_device(
        user.id,
        MeshDeviceRegister(mesh_device_id=None),
        admin,
        session,
    )

    session.refresh(user)
    session.refresh(backup)
    assert cleared.mesh_device_id is None
    assert user.mesh_device_id is None
    assert {device.device_id: device.is_pilot_tracker for device in cleared.mesh_devices} == {
        "!backup": False,
        "!tracker": False,
    }


def test_admin_can_delete_user_pilot_tracker_from_profile() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id="!tracker")
    session.add_all([admin, user])
    session.flush()
    session.add_all(
        [
            MeshDevice(owner_user_id=user.id, device_id="!tracker", label="Tracker", purpose="tracking"),
            MeshDevice(owner_user_id=user.id, device_id="!relay", label="Relay", purpose="relay"),
        ]
    )
    session.commit()

    response = admin_delete_user_mesh_device(user.id, "!tracker", admin, session)

    session.refresh(user)
    deleted_tracker = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!tracker"))
    remaining_relay = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!relay"))
    assert response.mesh_device_id is None
    assert user.mesh_device_id is None
    assert deleted_tracker is None
    assert remaining_relay is not None
    assert [device.device_id for device in response.mesh_devices] == ["!relay"]


def test_admin_can_edit_user_mesh_device_fields() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add_all([admin, user])
    session.flush()
    session.add(MeshDevice(owner_user_id=user.id, device_id="!relay", label="Relay", purpose="relay"))
    session.commit()

    response = admin_update_user_mesh_device(
        user.id,
        "!relay",
        MeshDeviceUpdate(device_id="!newrelay", label="Roof Relay", purpose="base_station"),
        admin,
        session,
    )

    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!newrelay"))
    assert device is not None
    assert device.label == "Roof Relay"
    assert device.purpose == "base_station"
    assert response.mesh_devices[0].device_id == "!newrelay"
    assert response.mesh_devices[0].is_pilot_tracker is False


def test_owned_tracking_mesh_device_resolves_even_when_legacy_pointer_is_missing() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id=None)
    session.add(user)
    session.flush()
    session.add(MeshDevice(owner_user_id=user.id, device_id="!tracker", label="Tracker", purpose="tracking"))
    session.commit()

    resolved_user, resolved_device = resolve_mesh_device_assignment(session, "!tracker")

    assert resolved_user is user
    assert resolved_device is not None
    assert resolved_device.device_id == "!tracker"


def test_change_password_requires_current_password() -> None:
    session = _session()
    user = User(username="admin", full_name="Admin User", role="admin", password_hash="old-hash")
    session.add(user)
    session.commit()

    with patch("app.routers.auth.verify_password", return_value=False):
        try:
            change_password(PasswordChangeRequest(current_password="wrong", new_password="new-secret-1"), user, session)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 401
        else:
            raise AssertionError("Expected password change to reject an invalid current password")


def test_admin_can_update_user_role_and_profile_type() -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin User", role="admin", profile_type="pilot", password_hash="hash")
    previous_profile_type_updated_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    target = User(
        username="pilot@example.com",
        full_name="Pilot User",
        role="pilot",
        profile_type="pilot",
        password_hash="hash",
        profile_type_updated_at=previous_profile_type_updated_at,
    )
    session.add_all([admin, target])
    session.commit()

    response = update_user_account(
        target.id,
        AdminUserUpdate(role="organizer", profile_type="driver", is_active=True),
        admin,
        session,
    )

    session.refresh(target)
    assert response.role == "organizer"
    assert target.role == "organizer"
    assert target.profile_type == "driver"
    assert _utc(target.profile_type_updated_at) > previous_profile_type_updated_at
    assert _utc(response.profile_type_updated_at) > previous_profile_type_updated_at
