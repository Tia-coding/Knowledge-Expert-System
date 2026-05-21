"""
Authentication routes for NRSC system.
Handles user login with secure JWT token generation and role-based access control.
"""

from datetime import timedelta
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)

from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    verify_user_credentials,
)

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

from app.schemas.schemas import (
    LoginRequest,
    TokenResponse,
)

from app.services.audit_service import (
    audit,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Authentication"]
)

settings = get_settings()


# =========================================================
# LOGIN
# =========================================================

@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(

    payload: LoginRequest,

    request: Request,

    db: Session = Depends(get_db),

):
    """
    Authenticate user and return JWT token.
    """

    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    try:

        # =====================================================
        # VALIDATE INPUTS
        # =====================================================

        username = validate_username(
            payload.username
        )

        password = validate_password(
            payload.password
        )

        role = getattr(
            payload,
            "role",
            None,
        )

        if role is not None:

            role = validate_role(role)

    except ValidationError as e:

        logger.warning(

            f"Login validation error "
            f"from {client_ip}: {str(e)}"

        )

        audit(

            db,

            "LOGIN_FAILED",

            f"Invalid input format: {str(e)}",

            ip_address=client_ip,

        )

        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail=f"Invalid input: {str(e)}",

        )

    # =========================================================
    # VERIFY CREDENTIALS
    # =========================================================

    user = verify_user_credentials(

        username,

        password,

        role,

        db,

    )

    if not user:

        logger.warning(

            f"Login failed for {username} "
            f"from {client_ip}"

        )

        audit(

            db,

            "LOGIN_FAILED",

            f"Invalid credentials for {username}",

            ip_address=client_ip,

        )

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Invalid username or password",

        )

    # =========================================================
    # GENERATE TOKEN
    # =========================================================

    try:

        token = create_access_token(

            {

                "sub": user.username,

                "role": user.role,

            },

            expires_delta=timedelta(

                minutes=settings.access_token_expire_minutes

            ),

        )

    except Exception as e:

        logger.exception(

            f"Token generation failed: {str(e)}"

        )

        raise HTTPException(

            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail="Failed to generate authentication token",

        )

    # =========================================================
    # AUDIT SUCCESSFUL LOGIN
    # =========================================================

    audit(

        db,

        "LOGIN_SUCCESS",

        (
            f"{user.role} user "
            f"'{username}' logged in successfully"
        ),

        user,

        client_ip,

    )

    logger.info(

        f"Successful login for {username} "

        f"({user.role}) from {client_ip}"

    )

    # =========================================================
    # RESPONSE
    # =========================================================

    return TokenResponse(

        access_token=token,

        token_type="bearer",

        role=user.role,

        username=user.username,

    )