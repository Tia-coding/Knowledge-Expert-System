from pathlib import Path
from fastapi.responses import JSONResponse

from app.database.session import get_db
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.security import require_admin, get_current_user
from app.models.models import Document, SecurityLog, User
from app.rag.ollama_client import OllamaClient
from app.rag.vector_store import get_vector_store
from app.schemas.schemas import HealthResponse




router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
async def health(db: Session = Depends(get_db)):
    documents = db.query(Document).count()
    indexed = db.query(Document).filter(Document.status == "Indexed").count()

    try:
        vector_db = "healthy" if get_vector_store().count() >= 0 else "unavailable"
    except Exception:
        vector_db = "unavailable"

    ollama = "online" if await OllamaClient().is_available() else "offline"

    return HealthResponse(
        status="ok",
        documents=documents,
        indexed_documents=indexed,
        vector_db=vector_db,
        ollama=ollama,
    )

# added 
@router.get("/public-metrics")
async def public_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total_documents = db.query(Document).count()

    return {
        "total_documents": total_documents,
    }



@router.get("/metrics")
async def metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    total = db.query(Document).count()
    indexed = db.query(Document).filter(Document.status == "Indexed").count()
    failed = db.query(Document).filter(Document.status == "Failed").count()

    try:
        vector_chunks = get_vector_store().count()
    except Exception:
        vector_chunks = 0

    return {
        "total_documents": total,
        "indexed_documents": indexed,
        "failed_documents": failed,
        "vector_chunks": vector_chunks,
        "system_status": "Operational" if failed == 0 else "Needs Attention",
        "security_status": "JWT Enabled",
    }


@router.get("/security-logs")
async def security_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rows = db.query(SecurityLog).order_by(SecurityLog.created_at.desc()).limit(30).all()

    return [
        {
            "id": row.id,
            "username": row.username,
            "action": row.action,
            "detail": row.detail,
            "ip_address": row.ip_address,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.delete("/security-logs")
async def clear_security_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db.query(SecurityLog).delete()
    db.commit()

    db.add(
        SecurityLog(
            user_id=current_user.id,
            username=current_user.username,
            action="CLEAR_SECURITY_LOGS",
            detail="Cleared security activity logs",
            ip_address=request.client.host if request.client else None,
        )
    )

    db.commit()

    return {"message": "Security logs cleared"}


@router.get("/logs")
async def get_logs(
    current_user: User = Depends(require_admin),
):

    log_file = Path("backend/logs/app.log")

    if not log_file.exists():

        return JSONResponse(

            status_code=404,

            content={
                "message": "Log file not found"
            },

        )

    try:

        with open(
            log_file,
            "r",
            encoding="utf-8"
        ) as file:

            logs = file.readlines()

        return {

            "logs": logs[-100:]

        }

    except Exception as e:

        return JSONResponse(

            status_code=500,

            content={
                "message": str(e)
            },

        )