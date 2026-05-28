from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal
from app.models import EventPilot, Pilot, User
from app.services.pilot_identity import merge_pilots


def _name_key(first_name: str | None, last_name: str | None) -> str:
    return " ".join(part.strip().lower() for part in (first_name, last_name) if part and part.strip())


def _full_name(pilot: Pilot) -> str:
    return f"{pilot.first_name or ''} {pilot.last_name or ''}".strip() or f"Pilot {pilot.id}"


def _parse_manual_merge(raw: str) -> tuple[int, int]:
    source, sep, target = raw.partition(":")
    if sep != ":":
        raise argparse.ArgumentTypeError("manual merges must be SOURCE_ID:TARGET_ID")
    return int(source), int(target)


def proposed_event_name_merges(session, event_id: int) -> list[tuple[int, int, str]]:
    roster_pilots = session.scalars(
        select(Pilot)
        .join(EventPilot, EventPilot.pilot_id == Pilot.id)
        .where(EventPilot.event_id == event_id)
        .order_by(Pilot.id.asc())
    ).all()

    roster_by_name: dict[str, list[Pilot]] = defaultdict(list)
    for pilot in roster_pilots:
        key = _name_key(pilot.first_name, pilot.last_name)
        if key:
            roster_by_name[key].append(pilot)

    active_users = session.scalars(
        select(User)
        .where(User.pilot_id.is_not(None), User.is_active.is_(True))
        .order_by(User.id.asc())
    ).all()
    users_by_name: dict[str, list[User]] = defaultdict(list)
    for user in active_users:
        pilot = session.get(Pilot, user.pilot_id)
        key = _name_key(pilot.first_name, pilot.last_name) if pilot is not None else ""
        if key:
            users_by_name[key].append(user)

    proposals: list[tuple[int, int, str]] = []
    for key, roster_matches in roster_by_name.items():
        users = users_by_name.get(key, [])
        if len(roster_matches) != 1 or len(users) != 1:
            continue
        target = roster_matches[0]
        source_id = users[0].pilot_id
        if source_id is not None and source_id != target.id:
            proposals.append((source_id, target.id, _full_name(target)))
    return proposals


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair duplicate Pilot IDs by merging them into canonical roster pilots.")
    parser.add_argument("--event-id", type=int, required=True, help="Event whose roster should be used as canonical for exact-name proposals.")
    parser.add_argument("--apply", action="store_true", help="Apply proposed/manual merges. Without this flag the script is dry-run only.")
    parser.add_argument(
        "--merge",
        type=_parse_manual_merge,
        action="append",
        default=[],
        metavar="SOURCE_ID:TARGET_ID",
        help="Explicit duplicate source pilot and canonical target pilot to merge.",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        proposals = list(args.merge) or [
            (source_id, target_id)
            for source_id, target_id, _name in proposed_event_name_merges(session, args.event_id)
        ]
        named_proposals = {
            (source_id, target_id): name
            for source_id, target_id, name in proposed_event_name_merges(session, args.event_id)
        }

        if not proposals:
            print(f"No unambiguous duplicate pilots proposed for event {args.event_id}.")
            return 0

        print(f"{'Applying' if args.apply else 'Dry run for'} {len(proposals)} pilot merge(s):")
        for source_id, target_id in proposals:
            source = session.get(Pilot, source_id)
            target = session.get(Pilot, target_id)
            source_name = _full_name(source) if source is not None else f"Pilot {source_id}"
            target_name = _full_name(target) if target is not None else f"Pilot {target_id}"
            label = named_proposals.get((source_id, target_id), target_name)
            print(f"  {source_id} ({source_name}) -> {target_id} ({label or target_name})")

        if not args.apply:
            print("No changes made. Re-run with --apply to merge.")
            return 0

        for source_id, target_id in proposals:
            merge_pilots(session, source_pilot_id=source_id, target_pilot_id=target_id)
        session.commit()
        print("Pilot merges applied.")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
