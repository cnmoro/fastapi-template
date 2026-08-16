from datetime import datetime, timedelta, timezone
from typing import Optional
from bson import ObjectId
import bcrypt
import anyio
import jwt
import os

from services.db import get_database

from basemodels.authentication import PasswordUpdate, TokenData, \
    TokenResponse, UserCreate, UserResponse

# Configuration
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 120)
)

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not set")

class AuthenticationError(Exception):
    pass

def _hash_password_sync(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def _verify_password_sync(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# bcrypt burns ~150ms of CPU per call, which would block the whole event loop.
# It releases the GIL, so a worker thread gives real parallelism.
async def _hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return await anyio.to_thread.run_sync(_hash_password_sync, password)

async def _verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return await anyio.to_thread.run_sync(_verify_password_sync, password, hashed_password)

def _create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

async def verify_token(token: str, token_type: str = "access") -> TokenData:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        if payload.get("type") != token_type:
            raise AuthenticationError("Invalid token type")
        
        email: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        
        if email is None or user_id is None:
            raise AuthenticationError("Invalid token payload")
        
        return TokenData(email=email, user_id=user_id)
        
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid token")

async def create_user(user_data: UserCreate) -> UserResponse:
    """Create a new user."""
    # Check if user already exists
    users_collection = get_database()['USERS']
    email = user_data.email.lower()

    existing_user = await users_collection.find_one({"email": email})
    if existing_user:
        raise AuthenticationError("User with this email already exists")

    # Hash the password
    hashed_password = await _hash_password(user_data.password)

    # Create user document
    user_doc = {
        "email": email,
        "password": hashed_password,
        "full_name": user_data.full_name,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }

    # Insert user into database
    result = await users_collection.insert_one(user_doc)
    
    # Fetch the created user
    created_user = await users_collection.find_one({"_id": result.inserted_id})
    
    return UserResponse(
        id=str(created_user["_id"]),
        email=created_user["email"],
        full_name=created_user.get("full_name"),
        created_at=created_user["created_at"]
    )

async def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Authenticate a user with email and password."""
    users_collection = get_database()['USERS']
    
    user = await users_collection.find_one({"email": email.lower()})

    if not user:
        return None
    
    if not await _verify_password(password, user["password"]):
        return None
    
    return user

async def login(username, password) -> TokenResponse:
    """Login a user and return JWT tokens."""
    user = await authenticate_user(username, password)
    
    if not user:
        raise AuthenticationError("Invalid email or password")

    # Create token data
    token_data = {
        "sub": user["email"],
        "user_id": str(user["_id"])
    }

    # Create tokens
    access_token = _create_access_token(token_data)

    return TokenResponse(
        access_token=access_token
    )

async def get_current_user(token_data: TokenData) -> UserResponse:
    """Get current user from token data."""
    users_collection = get_database()['USERS']
    
    user = await users_collection.find_one({
        "_id": ObjectId(token_data.user_id),
    })
    
    if not user:
        raise AuthenticationError("User not found")

    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name"),
        created_at=user["created_at"]
    )

async def update_password(user_id: str, password_data: PasswordUpdate) -> bool:
    """Update user password."""
    users_collection = get_database()['USERS']
    
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise AuthenticationError("User not found")

    # Verify current password
    if not await _verify_password(password_data.current_password, user["password"]):
        raise AuthenticationError("Current password is incorrect")

    # Hash new password
    new_hashed_password = await _hash_password(password_data.new_password)

    # Update password in database
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "password": new_hashed_password,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    return result.modified_count > 0
