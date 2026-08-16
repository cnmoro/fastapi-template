from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, \
    OAuth2PasswordRequestForm
from basemodels.authentication import PasswordUpdate, RolesUpdate, TokenData, \
    TokenResponse, UserCreate, UserResponse
from services.rbac import Role, require_roles
from services.authentication import (
    AuthenticationError,
    RateLimitedError,
    verify_token,
    refresh_token,
    get_current_user,
    create_user,
    login,
    set_user_roles,
    update_password
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    scheme_name="JWT"
)

def _client_ip(request: Request) -> str:
    """Client address for lockout accounting.

    Only trust X-Forwarded-For if a proxy you control sets it - otherwise a
    caller can spoof the header and sidestep the per-ip lockout.
    """
    return request.client.host if request.client else "unknown"

async def get_current_user_token_data(
    response: Response,
    token: str = Depends(oauth2_scheme)
) -> TokenData:
    """Token-only check: no database round-trip, so roles are as of token issue.

    Doubles as the sliding-session hook - using the API keeps the token alive,
    and a renewed one comes back in the X-Refreshed-Token response header.
    """
    try:
        token_data = await verify_token(token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    renewed = refresh_token(token_data)
    if renewed:
        response.headers["X-Refreshed-Token"] = renewed

    return token_data

@auth_router.get("/me", response_model=UserResponse)
async def get_current_user_ep(
    token_data: TokenData = Depends(get_current_user_token_data)
) -> UserResponse:
    """Get the current authenticated user."""
    try:
        return await get_current_user(token_data)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

@auth_router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
async def register_user(
    user_data: UserCreate
):
    """Register a new user."""
    try:
        return await create_user(user_data)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@auth_router.post("/login", response_model=TokenResponse)
async def login_user(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Login a user and return JWT tokens."""
    try:
        return await login(
            form_data.username.lower(),
            form_data.password,
            client_ip=_client_ip(request)
        )
    except RateLimitedError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

@auth_router.put("/password")
async def update_password_ep(
    password_data: PasswordUpdate,
    token_data: TokenData = Depends(get_current_user_token_data)
):
    """Update user password. Signs out every other session."""
    try:
        success = await update_password(
            token_data.user_id,
            password_data
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update password"
        )

    return {"message": "Password updated successfully"}

@auth_router.get("/check_access")
async def check_access(
    token_data: TokenData = Depends(get_current_user_token_data)
):
    return {
        "message": "You are authenticated successfully with your JWT token."
    }

@auth_router.put(
    "/users/{user_id}/roles",
    response_model=UserResponse,
    dependencies=[Depends(require_roles(Role.ADMIN))]
)
async def set_user_roles_ep(
    user_id: str,
    roles_data: RolesUpdate
):
    """Replace a user's roles. Admin only."""
    try:
        return await set_user_roles(user_id, roles_data.roles)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
