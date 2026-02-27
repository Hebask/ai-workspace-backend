from __future__ import annotations

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
)
from app.repositories.users_repo import UsersRepo

class AuthService:
    @staticmethod
    async def register(email: str, password: str) -> dict:
        try:
            existing = await UsersRepo.get_by_email(email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")
            user = await UsersRepo.create(email=email, password_hash=hash_password(password))
            return {
                "user": {
                    "_id": user["_id"],
                    "email": user["email"],
                    "plan": user["plan"],
                    "created_at": user["created_at"],
                },
                "access_token": create_access_token(user["_id"], user["email"]),
                "refresh_token": create_refresh_token(user["_id"], user["email"]),
            }
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="Email already registered")
        except HTTPException:
            raise
        except Exception as e:
            # show a meaningful error instead of generic 500
            raise HTTPException(status_code=500, detail=f"Register failed: {type(e).__name__}: {e}")

    @staticmethod
    async def login(email: str, password: str) -> dict:
        try:
            user = await UsersRepo.get_by_email(email)
            if not user or not verify_password(password, user["password_hash"]):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

            return {
                "user": {
                    "_id": user["_id"],
                    "email": user["email"],
                    "plan": user.get("plan", "free"),
                    "created_at": user["created_at"],
                },
                "access_token": create_access_token(user["_id"], user["email"]),
                "refresh_token": create_refresh_token(user["_id"], user["email"]),
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Login failed: {type(e).__name__}: {e}")