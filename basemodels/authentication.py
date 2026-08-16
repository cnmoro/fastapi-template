from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

# bcrypt refuses passwords longer than 72 bytes
Password = Field(min_length=8, max_length=72)

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Password
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Password
