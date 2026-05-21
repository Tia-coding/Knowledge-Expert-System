from jose import jwt

from app.config.settings import get_settings
settings = get_settings()

from datetime import datetime, timedelta
from typing import Optional

import logging

from fastapi import (
    Depends,
    HTTPException,
    status,
)

from fastapi.security import (
    OAuth2PasswordBearer,
)

from jose import JWTError, jwt

from passlib.context import (
    CryptContext,
)

from sqlalchemy.orm import Session

from app.auth.validators import (
    ValidationError,
    validate_password,
    validate_role,
    validate_username,
)

from app.config.settings import (
    get_settings,
)

from app.database.session import (
    get_db,
)

from app.models.models import (
    User,
)

logger = logging.getLogger(__name__)

settings = get_settings()

# =========================================================
# PASSWORD HASHING
# =========================================================

pwd_context = CryptContext(

    schemes=["bcrypt"],

    deprecated="auto",

    bcrypt__rounds=12,

)

# =========================================================
# OAUTH2
# =========================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/login"
)

# =========================================================
# VERIFY PASSWORD
# =========================================================

def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify plain password against bcrypt hash.
    Uses constant-time comparison.
    """

    try:

        return pwd_context.verify(

            plain_password,

            hashed_password,

        )

    except Exception as e:

        logger.warning(
            f"Password verification error: {str(e)}"
        )

        return False


# =========================================================
# HASH PASSWORD
# =========================================================

def get_password_hash(
    password: str,
) -> str:
    """
    Hash plain password securely.
    """

    try:

        validate_password(password)

    except ValidationError as e:

        raise ValueError(str(e))

    return pwd_context.hash(password)


# =========================================================
# CREATE ACCESS TOKEN
# =========================================================

def create_access_token(

    data: dict,

    expires_delta: Optional[timedelta] = None,

) -> str:
    """
    Create signed JWT token.
    """

    to_encode = data.copy()

    expire = datetime.utcnow() + (

        expires_delta

        or timedelta(
            minutes=settings.access_token_expire_minutes
        )

    )

    to_encode.update({

        "exp": expire,

        "iat": datetime.utcnow(),

    })

    try:

        token = jwt.encode(

            to_encode,

            settings.secret_key,

            algorithm=settings.algorithm,

        )

        return token

    except Exception as e:

        logger.exception(
            f"Token creation failed: {str(e)}"
        )

        raise


# =========================================================
# GET CURRENT USER
# =========================================================

def get_current_user(

    token: str = Depends(oauth2_scheme),

    db: Session = Depends(get_db),

) -> User:
    """
    Validate JWT token and return user.
    """

    credentials_exception = HTTPException(

        status_code=status.HTTP_401_UNAUTHORIZED,

        detail="Invalid authentication credentials",

        headers={

            "WWW-Authenticate": "Bearer"

        },

    )

    try:

        payload = jwt.decode(

            token,

            settings.secret_key,

            algorithms=[settings.algorithm],

        )

        username: str | None = payload.get(
            "sub"
        )

        role: str | None = payload.get(
            "role"
        )

        if not username or not role:

            logger.warning(
                "Invalid token payload"
            )

            raise credentials_exception

    except JWTError as exc:

        logger.warning(
            f"JWT decode error: {str(exc)}"
        )

        raise credentials_exception from exc

    except Exception as e:

        logger.exception(
            f"Unexpected auth error: {str(e)}"
        )

        raise credentials_exception

    # =====================================================
    # FETCH USER
    # =====================================================

    user = (

        db.query(User)

        .filter(
            User.username == username
        )

        .first()

    )

    if user is None:

        logger.warning(
            f"User not found: {username}"
        )

        raise credentials_exception

    # =====================================================
    # VERIFY ROLE
    # =====================================================

    if user.role != role:

        logger.warning(

            f"Role mismatch for user "
            f"{username}: "
            f"token={role}, db={user.role}"

        )

        raise credentials_exception

    return user


# =========================================================
# REQUIRE ADMIN
# =========================================================

def require_admin(

    current_user: User = Depends(
        get_current_user
    )

) -> User:
    """
    Require administrator role.
    """

    if current_user.role != "admin":

        logger.warning(

            f"Admin access denied for user: "
            f"{current_user.username}"

        )

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail="Administrator access required",

        )

    return current_user


# =========================================================
# REQUIRE USER
# =========================================================

def require_user(

    current_user: User = Depends(
        get_current_user
    )

) -> User:
    """
    Require authenticated user role.
    """

    if current_user.role not in (

        "user",

        "admin",

    ):

        logger.warning(

            f"User access denied for role: "
            f"{current_user.role}"

        )

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail="User access required",

        )

    return current_user


# =========================================================
# VERIFY USER CREDENTIALS
# =========================================================

def verify_user_credentials(

    username: str,

    password: str,

    role: str | None,

    db: Session,

) -> Optional[User]:
    """
    Verify user credentials.
    Returns User if valid.
    """

    try:

        username = validate_username(
            username
        )

        validate_password(password)

        if role is not None:

            role = validate_role(role)

    except ValidationError as e:

        logger.warning(

            f"Invalid login validation: "
            f"{str(e)}"

        )

        return None

    # =====================================================
    # FIND USER
    # =====================================================

    user = (

        db.query(User)

        .filter(
            User.username == username
        )

        .first()

    )

    if not user:

        logger.warning(

            f"Login failed - user not found: "
            f"{username}"

        )

        return None

    # =====================================================
    # VERIFY PASSWORD
    # =====================================================

    if not verify_password(

        password,

        user.hashed_password,

    ):

        logger.warning(

            f"Login failed - invalid password "
            f"for user: {username}"

        )

        return None

    # =====================================================
    # VERIFY ROLE
    # =====================================================

    if (

        role is not None

        and user.role != role

    ):

        logger.warning(

            f"Login failed - role mismatch "
            f"for user {username}: "
            f"requested={role}, "
            f"actual={user.role}"

        )

        return None

    return user


def decode_access_token(token: str):

    try:

        payload = jwt.decode(

            token,

            settings.secret_key,

            algorithms=[settings.algorithm],

        )

        return payload

    except Exception:

        return None