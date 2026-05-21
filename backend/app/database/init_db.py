from app.auth.security import get_password_hash
from app.database.session import Base, SessionLocal, engine
from app.models.models import User


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        defaults = [
            ("admin", "admin123", "admin"),
            ("user", "user123", "user"),
        ]
        for username, password, role in defaults:
            existing = db.query(User).filter(User.username == username).first()
            if not existing:
                db.add(User(username=username, hashed_password=get_password_hash(password), role=role))
        db.commit()
    finally:
        db.close()