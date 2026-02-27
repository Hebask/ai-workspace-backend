from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr
from pydantic import field_validator
from app.core.security import decode_token
from app.services.auth_service import AuthService
from app.repositories.users_repo import UsersRepo

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthResponse(BaseModel):
    user: dict
    access_token: str
    refresh_token: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password too long (bcrypt max is 72 bytes). Use <= 72 bytes.")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password too long (bcrypt max is 72 bytes). Use <= 72 bytes.")
        return v


async def get_current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await UsersRepo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    return await AuthService.register(req.email, req.password)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    return await AuthService.login(req.email, req.password)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"_id": user["_id"], "email": user["email"], "plan": user.get("plan", "free"), "created_at": user["created_at"]}

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh")
async def refresh(req: RefreshRequest):
    token = req.refresh_token.strip()
    if token.startswith("Bearer "):
        token = token.split(" ", 1)[1].strip()

    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return {"access_token": create_access_token(user_id, email)}