from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str = Field(..., alias="_id")
    email: EmailStr
    plan: str = "free"
    created_at: datetime


class UserInDB(BaseModel):
    id: str = Field(..., alias="_id")
    email: EmailStr
    password_hash: str
    plan: str = "free"
    created_at: datetime