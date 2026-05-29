import json
import uuid

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)

from fastapi.responses import (
    StreamingResponse,
)

from sqlalchemy.orm import Session

from app.auth.security import (
    get_current_user,
)

from app.database.session import (
    get_db,
)

from app.models.models import (
    ChatHistory,
    User,
)

from app.rag.rag_service import (
    RAGService,
)

from app.schemas.schemas import (
    AskRequest,
    AskResponse,
)

from app.services.audit_service import (
    audit,
)

router = APIRouter(tags=["RAG"])


def new_conversation_id() -> str:
    return str(uuid.uuid4())


def conversation_title(question: str) -> str:
    text = (question or "").strip()
    if not text:
        return "New conversation"
    return text[:80] + ("..." if len(text) > 80 else "")


# =========================================================
# LOAD CONVERSATION HISTORY (structured turns for LLM memory)
# =========================================================

def load_conversation_history(
    db: Session,
    user_id: int,
    conversation_id: str,
    limit: int = 6,
) -> list[dict[str, str]]:
    """Return prior turns as structured role/content pairs (excludes current question)."""

    rows = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.user_id == user_id,
            ChatHistory.conversation_id == conversation_id,
        )
        .order_by(ChatHistory.created_at.asc())
        .all()
    )

    if len(rows) > limit:
        rows = rows[-limit:]

    history: list[dict[str, str]] = []

    for row in rows:
        question = (row.question or "").strip()
        answer = (row.answer or "").strip()

        if not question or not answer:
            continue

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})

    return history


# =========================================================
# NORMAL ASK ENDPOINT
# =========================================================

@router.post(
    "/ask",
    response_model=AskResponse,
)
async def ask(

    payload: AskRequest,

    request: Request,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),

):

    question = (
        payload.question or ""
    ).strip()

    if not question:

        return AskResponse(

            answer=(
                "Please enter a valid question."
            ),

            sources=[],

            confidence=0.0,

        )

    conversation_id = (
        (payload.conversation_id or "").strip()
        or new_conversation_id()
    )

    # Prior turns for LLM memory; current question stays separate for retrieval.
    conversation_history = load_conversation_history(
        db=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        limit=6,
    )

    result = await RAGService().answer(
        db=db,
        user=current_user,
        question=question,
        conversation_history=conversation_history,
        model=payload.model,
        top_k=payload.top_k,
    )

    # =====================================================
    # STORE HISTORY
    # =====================================================

    chat_entry = ChatHistory(

        user_id=current_user.id,

        conversation_id=conversation_id,

        question=question,

        answer=(
            result["answer"]
            or "No response generated."
        ),

        sources_json=json.dumps(
            result["sources"]
        ),

        confidence=result["confidence"],

    )

    db.add(chat_entry)

    db.commit()

    db.refresh(chat_entry)

    # =====================================================
    # AUDIT
    # =====================================================

    audit(

        db,

        "ASK_QUESTION",

        question[:250],

        current_user,

        (
            request.client.host
            if request.client
            else None
        ),

    )

    return AskResponse(

        answer=result["answer"],

        sources=result["sources"],

        confidence=result["confidence"],

        id=chat_entry.id,

        conversation_id=conversation_id,

    )


# =========================================================
# STREAMING ASK ENDPOINT
# =========================================================

@router.post("/ask-stream")
async def ask_stream(

    payload: AskRequest,

    request: Request,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),

):

    question = (
        payload.question or ""
    ).strip()

    if not question:

        async def empty_stream():

            yield (
                "data: Please enter a valid question.\n\n"
            )

        return StreamingResponse(

            empty_stream(),

            media_type="text/event-stream",

        )

    conversation_id = (
        (payload.conversation_id or "").strip()
        or new_conversation_id()
    )

    conversation_history = load_conversation_history(
        db=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        limit=6,
    )

    async def event_generator():

        full_response = ""

        try:

            async for chunk in (
                RAGService().stream_answer(
                    question=question,
                    conversation_history=conversation_history,
                    model=payload.model,
                    top_k=payload.top_k,
                )
            ):

                if not chunk:
                    continue

                full_response += chunk

                safe_chunk = chunk.replace(
                    "\n",
                    " "
                )

                yield (
                    f"data: {safe_chunk}\n\n"
                )

            # =============================================
            # SAVE FINAL CHAT HISTORY
            # =============================================

            chat_entry = ChatHistory(

                user_id=current_user.id,

                conversation_id=conversation_id,

                question=question,

                answer=(

                    full_response.strip()

                    or "No response generated."

                ),

                sources_json="[]",

                confidence=0.85,

            )

            db.add(chat_entry)

            db.commit()

            db.refresh(chat_entry)

            yield (
                f"data: [META]{json.dumps({'id': chat_entry.id, 'conversation_id': conversation_id})}\n\n"
            )

            # =============================================
            # AUDIT
            # =============================================

            audit(

                db,

                "STREAM_QUESTION",

                question[:250],

                current_user,

                (
                    request.client.host
                    if request.client
                    else None
                ),

            )

            yield "data: [DONE]\n\n"

        except Exception:

            yield (
                "data: An error occurred while "
                "generating the response.\n\n"
            )

    return StreamingResponse(

        event_generator(),

        media_type="text/event-stream",

        headers={

            "Cache-Control": "no-cache",

            "Connection": "keep-alive",

            "X-Accel-Buffering": "no",

        },

    )


# =========================================================
# GET CHAT HISTORY
# =========================================================

@router.get("/history")
async def history(

    q: str = "",

    conversation_id: str | None = Query(None),

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),

):

    query = db.query(ChatHistory).filter(

        ChatHistory.user_id
        == current_user.id

    )

    if conversation_id:

        query = query.filter(
            ChatHistory.conversation_id == conversation_id
        )

    if q:

        query = query.filter(

            ChatHistory.question.ilike(
                f"%{q}%"
            )

        )

    order = (
        ChatHistory.created_at.asc()
        if conversation_id
        else ChatHistory.created_at.desc()
    )

    rows = (

        query.order_by(order)

        .limit(500 if conversation_id else 200)

        .all()

    )

    response = []

    for row in rows:

        try:

            sources = json.loads(
                row.sources_json or "[]"
            )

        except Exception:

            sources = []

        response.append({

            "id": row.id,

            "conversation_id": row.conversation_id,

            "question": row.question,

            "answer": row.answer,

            "sources": sources,

            "confidence": row.confidence,

            "created_at": row.created_at,

        })

    return response


@router.get("/history/conversations")
async def list_conversations(

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),

):

    rows = (

        db.query(ChatHistory)

        .filter(
            ChatHistory.user_id == current_user.id
        )

        .order_by(
            ChatHistory.created_at.asc()
        )

        .all()

    )

    threads: dict[str, dict] = {}

    for row in rows:

        cid = row.conversation_id or "default"

        if cid not in threads:

            threads[cid] = {

                "conversation_id": cid,

                "title": conversation_title(
                    row.question or ""
                ),

                "created_at": row.created_at,

                "updated_at": row.created_at,

                "message_count": 0,

            }

        thread = threads[cid]

        thread["message_count"] += 1

        if row.created_at and row.created_at < thread["created_at"]:
            thread["created_at"] = row.created_at
            thread["title"] = conversation_title(
                row.question or ""
            )

        if row.created_at and row.created_at > thread["updated_at"]:
            thread["updated_at"] = row.created_at

    return sorted(

        threads.values(),

        key=lambda item: item["updated_at"],

        reverse=True,

    )


# =========================================================
# DELETE CONVERSATION THREAD
# =========================================================

@router.delete("/history/conversation/{conversation_id}")
async def delete_conversation(

    conversation_id: str,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),

):

    rows = (

        db.query(ChatHistory)

        .filter(

            ChatHistory.user_id == current_user.id,

            ChatHistory.conversation_id == conversation_id,

        )

        .all()

    )

    if not rows:

        return {
            "message": "Conversation not found.",
            "deleted_count": 0,
        }

    deleted_count = len(rows)

    for row in rows:
        db.delete(row)

    db.commit()

    audit(

        db,

        "DELETE_CONVERSATION",

        f"Deleted conversation {conversation_id}",

        current_user,

    )

    return {

        "message": "Conversation deleted successfully.",

        "deleted_count": deleted_count,

    }


# =========================================================
# DELETE SINGLE HISTORY
# =========================================================

@router.delete(
    "/history/{history_id}"
)
async def delete_history(

    history_id: int,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),

):

    row = (

        db.query(ChatHistory)

        .filter(

            ChatHistory.id == history_id,

            ChatHistory.user_id
            == current_user.id,

        )

        .first()

    )

    if not row:

        return {

            "message":
            "History item not found."

        }

    db.delete(row)

    db.commit()

    audit(

        db,

        "DELETE_CHAT_HISTORY",

        (
            f"Deleted history "
            f"item {history_id}"
        ),

        current_user,

    )

    return {

        "message":
        "History deleted successfully."

    }


# =========================================================
# CLEAR HISTORY
# =========================================================

@router.delete("/history")
async def clear_history(

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),

):

    rows = (

        db.query(ChatHistory)

        .filter(
            ChatHistory.user_id
            == current_user.id
        )

        .all()

    )

    deleted_count = len(rows)

    for row in rows:

        db.delete(row)

    db.commit()

    audit(

        db,

        "CLEAR_CHAT_HISTORY",

        (
            f"Cleared {deleted_count} "
            f"chat history items"
        ),

        current_user,

    )

    return {

        "message":
        f"Deleted {deleted_count} "
        f"history items."

    }