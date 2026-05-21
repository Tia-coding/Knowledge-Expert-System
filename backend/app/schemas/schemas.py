from datetime import datetime
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class AskRequest(BaseModel):
    question: str
    model: str | None = None
    top_k: int | None = None
    conversation_id: str | None = None


class Source(BaseModel):
    file: str
    page: str | int | None = None
    confidence: float | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    confidence: float
    id: int | None = None
    conversation_id: str | None = None


class DocumentOut(BaseModel):
    id: int
    filename: str
    document_type: str
    size_bytes: int
    status: str
    chunk_count: int
    table_count: int
    page_count: int
    error_message: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    documents: int
    indexed_documents: int
    vector_db: str
    ollama: str