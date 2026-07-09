from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, RefreshTokenRequest, UserOut
from app.services.auth_service import register_user, login_user, refresh_access_token
from app.core.deps import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_REQUEST_BODY_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["email", "password"],
                    "properties": {
                        "email": {
                            "type": "string",
                            "format": "email",
                            "example": "user@example.com",
                        },
                        "password": {
                            "type": "string",
                            "format": "password",
                            "example": "securepass123",
                        },
                    },
                }
            },
            "application/x-www-form-urlencoded": {
                "schema": {
                    "type": "object",
                    "required": ["username", "password"],
                    "properties": {
                        "username": {
                            "type": "string",
                            "format": "email",
                            "description": "User email address.",
                            "example": "user@example.com",
                        },
                        "password": {
                            "type": "string",
                            "format": "password",
                            "example": "securepass123",
                        },
                    },
                }
            },
        },
    }
}


async def get_login_data(request: Request) -> UserLogin:
    """
    Accept frontend JSON login and OAuth2 password-form login.

    OAuth2PasswordBearer still uses this endpoint as its tokenUrl, so Swagger and
    OAuth2 clients can post form fields: username=<email>, password=<password>.
    """
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            payload = await request.json()
            return UserLogin.model_validate(payload)
        except (ValueError, ValidationError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Request body must include a valid email and password.",
            )

    form = await request.form()
    email = form.get("username") or form.get("email")
    password = form.get("password")

    if not isinstance(email, str) or not isinstance(password, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Form body must include username/email and password.",
        )

    try:
        return UserLogin(email=email, password=password)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Form body must include a valid email and password.",
        )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Create a new user account and return access + refresh tokens.
    """
    return await register_user(db, data)


@router.post(
    "/login",
    response_model=TokenResponse,
    openapi_extra=LOGIN_REQUEST_BODY_OPENAPI,
)
async def login(
    login_data: UserLogin = Depends(get_login_data),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email + password and return JWT tokens.
    Accepts JSON {"email", "password"} or OAuth2 form username=<email>.
    """
    return await login_user(db, login_data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new token pair.
    Call this when the access token expires (30 min by default).
    """
    return await refresh_access_token(db, data.refresh_token)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """
    Return the currently authenticated user's profile.
    Requires a valid Bearer token in the Authorization header.
    """
    return current_user
