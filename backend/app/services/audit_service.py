import logging

from sqlalchemy.orm import Session

from app.models.models import (
    SecurityLog,
    User,
)

logger = logging.getLogger(__name__)


def audit(

    db: Session,

    action: str,

    detail: str = "",

    user: User | None = None,

    ip_address: str | None = None,

) -> None:

    try:

        log = SecurityLog(

            user_id=(
                user.id
                if user
                else None
            ),

            username=(
                user.username
                if user
                else "system"
            ),

            action=action,

            detail=detail,

            ip_address=ip_address,

        )

        db.add(log)

        db.commit()

    except Exception as e:

        db.rollback()

        logger.exception(

            f"Audit logging failed: {str(e)}"

        )