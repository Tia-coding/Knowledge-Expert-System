from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

print(">>> PUBLIC CHAT ROUTE LOADED <<<")

from app.database.session import get_db
from app.models.models import User
from app.rag.rag_service import RAGService
from app.schemas.schemas import (
    AskRequest,
    AskResponse,
)

router = APIRouter()

print(">>> ROUTER CREATED <<<")

rag_service = RAGService()


@router.post(
    "/public/ask",
    response_model=AskResponse,
)
async def public_ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
):
    print(">>> PUBLIC ASK FUNCTION REGISTERED <<<")
    guest_user = User(
        id=0,
        username="public_widget",
        hashed_password="",
        role="guest",
    )

    result = await rag_service.answer(
        db=db,
        user=guest_user,
        question=payload.question,
        conversation_history=[],
        model=payload.model,
        top_k=payload.top_k,
    )

    return AskResponse(
    answer=result["answer"],
    sources=result["sources"],
    confidence=result["confidence"],
    id=0,
    conversation_id="public",
)
print(router.routes)