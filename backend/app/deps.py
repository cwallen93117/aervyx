from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_session
from app.models import User

security = HTTPBearer(auto_error=False)


def token_subject_for_user(user: User) -> str:
    return f"user:{user.id}"


def resolve_user_from_token_subject(session: Session, subject: str) -> User | None:
    if subject.startswith("user:"):
        try:
            user_id = int(subject.removeprefix("user:"))
        except ValueError:
            return None
        return session.get(User, user_id)
    return session.scalar(select(User).where(User.username == subject, User.is_active.is_(True)))


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = resolve_user_from_token_subject(session, subject)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in {"admin", "organizer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organizer access required")
    return user
