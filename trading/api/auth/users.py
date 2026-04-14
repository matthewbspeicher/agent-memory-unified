from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr

from trading.api.identity.store import IdentityStore
from trading.models.user import User

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


def create_access_token(
    data: dict, secret_key: str, expires_delta: Optional[timedelta] = None
):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm="HS256")
    return encoded_jwt


async def get_identity_store(request: Request) -> IdentityStore:
    # In this app, the pool is usually at request.app.state.db
    return IdentityStore(request.app.state.db)


@router.post("/signup", response_model=User)
async def signup(
    user_data: UserCreate, store: IdentityStore = Depends(get_identity_store)
):
    existing_user = await store.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )
    user = await store.create_user(user_data.email, user_data.password)
    return user


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    user_data: UserLogin,
    store: IdentityStore = Depends(get_identity_store),
):
    user = await store.get_user_by_email(user_data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not bcrypt.checkpw(
        user_data.password.encode("utf-8"), user.hashed_password.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    settings = request.app.state.config
    secret_key = settings.api_key or "secret"

    access_token = create_access_token(
        data={"sub": user.email},
        secret_key=secret_key,
        expires_delta=timedelta(hours=24),
    )
    return {"access_token": access_token, "token_type": "bearer"}


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    store: IdentityStore = Depends(get_identity_store),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = request.app.state.config
    secret_key = settings.api_key or "secret"

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await store.get_user_by_email(email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
