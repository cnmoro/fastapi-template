from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

Password = Field(min_length=8, max_length=128)

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Password
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    roles: list[str] = []
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None
    roles: list[str] = []
    token_version: int = 0
    session_start: Optional[datetime] = None
    expires_at: Optional[datetime] = None

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Password

class RolesUpdate(BaseModel):
    roles: list[str]
