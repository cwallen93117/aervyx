import json
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("APP_SECRET_KEY", "map-overlay-config-test-secret-key")

from app.db import Base
from app.models import MapOverlayConfig, User
from app.routers.map_overlay_config import get_map_overlay_config, get_public_map_overlay_config, update_map_overlay_config
from app.schemas import MapOverlayConfigUpdate


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _admin() -> User:
    return User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")


def test_default_grouped_config_includes_legacy_contexts() -> None:
    session = _session()

    response = get_map_overlay_config(_admin(), session)

    assert response.config["schema_version"] == 2
    assert response.config["groups"]["task_builder"]["tasks"] is True
    assert response.config["groups"]["scoring"]["airspace"] is False
    assert response.config["task_builder"]["turnpoints"] is True
    assert response.config["airspace_explorer"]["tfrs"] is True
    assert response.config["groups"]["public_live"]["airspace"] is True
    assert response.config["groups"]["public_live"]["high_floor_airspace"] is False
    assert response.config["public_live"]["faa_airspace"] is True
    assert response.config["public_live"]["high_floor_airspace"] is False


def test_flat_config_is_migrated_to_grouped_config() -> None:
    session = _session()
    session.add(
        MapOverlayConfig(
            id=1,
            config=json.dumps(
                {
                    "task_builder": {
                        "turnpoints": False,
                        "task_route": False,
                        "task_cylinders": False,
                        "optimized_route": False,
                        "leg_labels": False,
                        "distance_summary": False,
                        "click_to_add_turnpoint": False,
                        "fullscreen_editor_panel": False,
                    },
                    "public_live": {"live_positions": False, "live_labels": False},
                }
            ),
        )
    )
    session.commit()

    response = get_map_overlay_config(_admin(), session)

    assert response.config["schema_version"] == 2
    assert response.config["groups"]["task_builder"]["tasks"] is False
    assert response.config["task_builder"]["turnpoints"] is False
    assert response.config["task_builder"]["optimized_route"] is False
    assert response.config["groups"]["public_live"]["live_tracking"] is False
    assert response.config["public_live"]["live_positions"] is False
    assert response.config["groups"]["public_live"]["airspace"] is True
    assert response.config["groups"]["public_live"]["high_floor_airspace"] is False
    assert response.config["public_live"]["faa_airspace"] is True


def test_grouped_patch_expands_to_legacy_booleans() -> None:
    session = _session()

    response = update_map_overlay_config(
        MapOverlayConfigUpdate(
            config={
                "schema_version": 2,
                "groups": {
                    "task_builder": {"tasks": False, "map_controls": True},
                    "airspace_explorer": {"airspace": False},
                    "public_live": {"high_floor_airspace": True},
                },
            }
        ),
        _admin(),
        session,
    )

    assert response.config["groups"]["task_builder"]["tasks"] is False
    assert response.config["task_builder"]["turnpoints"] is False
    assert response.config["task_builder"]["task_route"] is False
    assert response.config["task_builder"]["fullscreen_toggle"] is True
    assert response.config["groups"]["airspace_explorer"]["airspace"] is False
    assert response.config["airspace_explorer"]["airspace_regions"] is False
    assert response.config["airspace_explorer"]["tfrs"] is False
    assert response.config["airspace_explorer"]["legend"] is False
    assert response.config["groups"]["public_live"]["high_floor_airspace"] is True
    assert response.config["public_live"]["high_floor_airspace"] is True


def test_public_endpoint_only_returns_public_live_slice() -> None:
    session = _session()
    update_map_overlay_config(
        MapOverlayConfigUpdate(config={"groups": {"public_live": {"live_tracking": False}}}),
        _admin(),
        session,
    )

    response = get_public_map_overlay_config(session)

    assert response.config["schema_version"] == 2
    assert set(response.config) == {"schema_version", "groups", "public_live"}
    assert set(response.config["groups"]) == {"public_live"}
    assert response.config["groups"]["public_live"]["live_tracking"] is False
    assert response.config["groups"]["public_live"]["high_floor_airspace"] is False
    assert response.config["public_live"]["live_positions"] is False
    assert response.config["public_live"]["high_floor_airspace"] is False
