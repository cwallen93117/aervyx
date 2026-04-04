from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user
from app.models import BuddyGroup, BuddyGroupMember, Pilot, User

router = APIRouter(prefix="/api/buddies", tags=["buddies"])


# --- Schemas ---


class GroupCreate(BaseModel):
    name: str
    visibility: str = "private"


class GroupRename(BaseModel):
    name: str | None = None
    visibility: str | None = None


class MemberAdd(BaseModel):
    pilot_id: int


class MemberResponse(BaseModel):
    pilot_id: int
    first_name: str
    last_name: str
    nation: str | None = None
    competition_number: str | None = None


class GroupResponse(BaseModel):
    id: int
    name: str
    visibility: str
    members: list[MemberResponse]
    created_at: str


class PilotSearchResult(BaseModel):
    pilot_id: int
    first_name: str
    last_name: str
    nation: str | None = None
    competition_number: str | None = None
    email: str | None = None


# --- Helpers ---


def _load_group_with_members(session: Session, group: BuddyGroup) -> GroupResponse:
    members = session.execute(
        select(BuddyGroupMember, Pilot)
        .join(Pilot, BuddyGroupMember.pilot_id == Pilot.id)
        .where(BuddyGroupMember.group_id == group.id)
        .order_by(Pilot.first_name, Pilot.last_name)
    ).all()
    return GroupResponse(
        id=group.id,
        name=group.name,
        visibility=group.visibility or "private",
        members=[
            MemberResponse(
                pilot_id=pilot.id,
                first_name=pilot.first_name,
                last_name=pilot.last_name,
                nation=pilot.nation,
                competition_number=pilot.competition_number,
            )
            for _member, pilot in members
        ],
        created_at=group.created_at.isoformat() if group.created_at else "",
    )


def _get_own_group(session: Session, user: User, group_id: int) -> BuddyGroup:
    group = session.get(BuddyGroup, group_id)
    if not group or group.user_id != user.id:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


# --- Endpoints ---


@router.get("/groups", response_model=list[GroupResponse])
def list_groups(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    groups = session.execute(
        select(BuddyGroup).where(BuddyGroup.user_id == user.id).order_by(BuddyGroup.name)
    ).scalars().all()
    return [_load_group_with_members(session, g) for g in groups]


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Group name is required")
    existing = session.execute(
        select(BuddyGroup).where(BuddyGroup.user_id == user.id, BuddyGroup.name == name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A group with that name already exists")
    visibility = payload.visibility if payload.visibility in {"public", "users", "buddies", "private"} else "private"
    group = BuddyGroup(user_id=user.id, name=name, visibility=visibility)
    session.add(group)
    session.commit()
    session.refresh(group)
    return _load_group_with_members(session, group)


@router.patch("/groups/{group_id}", response_model=GroupResponse)
def rename_group(group_id: int, payload: GroupRename, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    group = _get_own_group(session, user, group_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Group name is required")
        duplicate = session.execute(
            select(BuddyGroup).where(BuddyGroup.user_id == user.id, BuddyGroup.name == name, BuddyGroup.id != group_id)
        ).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status_code=409, detail="A group with that name already exists")
        group.name = name
    if payload.visibility is not None:
        if payload.visibility not in {"public", "users", "buddies", "private"}:
            raise HTTPException(status_code=422, detail="Invalid visibility value")
        group.visibility = payload.visibility
    session.commit()
    session.refresh(group)
    return _load_group_with_members(session, group)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    group = _get_own_group(session, user, group_id)
    session.delete(group)
    session.commit()


@router.post("/groups/{group_id}/members", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def add_member(group_id: int, payload: MemberAdd, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    group = _get_own_group(session, user, group_id)
    pilot = session.get(Pilot, payload.pilot_id)
    if not pilot:
        raise HTTPException(status_code=404, detail="Pilot not found")
    existing = session.execute(
        select(BuddyGroupMember).where(BuddyGroupMember.group_id == group_id, BuddyGroupMember.pilot_id == payload.pilot_id)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Pilot is already in this group")
    member = BuddyGroupMember(group_id=group_id, pilot_id=payload.pilot_id)
    session.add(member)
    session.commit()
    session.refresh(group)
    return _load_group_with_members(session, group)


@router.delete("/groups/{group_id}/members/{pilot_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(group_id: int, pilot_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    group = _get_own_group(session, user, group_id)
    member = session.execute(
        select(BuddyGroupMember).where(BuddyGroupMember.group_id == group.id, BuddyGroupMember.pilot_id == pilot_id)
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in group")
    session.delete(member)
    session.commit()


@router.get("/search-pilots", response_model=list[PilotSearchResult])
def search_pilots(q: str = Query(..., min_length=1), user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    term = f"%{q.strip().lower()}%"
    pilots = session.execute(
        select(Pilot).where(
            (Pilot.first_name + " " + Pilot.last_name).ilike(term)
            | Pilot.email.ilike(term)
            | Pilot.competition_number.ilike(term)
        ).order_by(Pilot.first_name, Pilot.last_name).limit(50)
    ).scalars().all()
    return [
        PilotSearchResult(
            pilot_id=p.id,
            first_name=p.first_name,
            last_name=p.last_name,
            nation=p.nation,
            competition_number=p.competition_number,
            email=p.email,
        )
        for p in pilots
    ]
