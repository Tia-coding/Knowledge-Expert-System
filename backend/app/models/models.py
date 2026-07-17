from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


INDIA_TZ = ZoneInfo("Asia/Kolkata")


def indian_time():
    return datetime.now(INDIA_TZ)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(
        String(80),
        unique=True,
        index=True,
        nullable=False,
    )

    hashed_password = Column(
        String(255),
        nullable=False,
    )

    role = Column(
        String(30),
        nullable=False,
        default="user",
    )

    created_at = Column(
        DateTime(timezone=True),
        default=indian_time,
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(
        String(255),
        nullable=False,
    )

    stored_filename = Column(
        String(255),
        nullable=False,
    )

    content_hash = Column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    document_type = Column(
        String(30),
        nullable=False,
    )

    size_bytes = Column(
        Integer,
        nullable=False,
        default=0,
    )

    status = Column(
        String(30),
        nullable=False,
        default="Uploaded",
    )

    chunk_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    table_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    page_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    error_message = Column(
        Text,
        nullable=True,
    )

    uploaded_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=indian_time,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=indian_time,
        onupdate=indian_time,
    )
    #Added processed time
    processed_at = Column(
    DateTime(timezone=True),
    nullable=True,
)
    #Added storage_path
    storage_path = Column(
    String(500),
    nullable=True,
)
    

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    # =====================================================
    # CHATGPT-LIKE CONVERSATION THREAD SUPPORT
    # =====================================================

    conversation_id = Column(
        String(120),
        index=True,
        nullable=False,
        default="default",
    )

    question = Column(
        Text,
        nullable=False,
    )

    answer = Column(
        Text,
        nullable=False,
    )

    sources_json = Column(
        Text,
        nullable=False,
        default="[]",
    )

    confidence = Column(
        Float,
        default=0.0,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=indian_time,
    )

    user = relationship("User")


class SecurityLog(Base):
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    username = Column(
        String(80),
        nullable=True,
    )

    action = Column(
        String(80),
        nullable=False,
    )

    detail = Column(
        Text,
        nullable=True,
    )

    ip_address = Column(
        String(80),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=indian_time,
    )