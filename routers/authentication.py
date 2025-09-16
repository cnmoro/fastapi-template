from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, \
    OAuth2PasswordRequestForm
from basemodels.authentication import PasswordUpdate, TokenData, \
    TokenResponse, UserCreate, UserResponse
from services.authentication import (
    AuthenticationError,
    verify_token,
    get_current_user,
    create_user,
    login,
    update_password
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    scheme_name="JWT"
)

async def get_current_user_token_data(
    token: str = Depends(oauth2_scheme)
) -> TokenData:
    try:
        return await verify_token(token, token_type="access")
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Login a user and return JWT tokens."""
    try:
        form_username = form_data.username
        form_username = form_username.lower()

        return await login(form_username, form_data.password)
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
    """Update user password."""
    try:
        success = await update_password(
            token_data.user_id,
            password_data
        )
        if success:
            return {"message": "Password updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update password"
            )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@auth_router.get("/check_access")
async def check_access(
    token_data: TokenData = Depends(get_current_user_token_data)
):
    return {
        "message": "You are authenticated successfully with your JWT token."
    }
