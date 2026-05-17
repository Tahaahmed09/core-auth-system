from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError

from app.database import get_db, User, engine, Base
from app.schemas import (
    UserCreate,
    UserRegistrationResponse,
    TokenExchangeResponse,
    StandardActionResponse,
)
from app.auth_utils import (
    hash_password,
    verify_password,
    create_token,
    decode_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.redis_client import init_redis, close_redis, blacklist_token, is_token_blacklisted


# ── Lifespan (replaces deprecated on_event) ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_redis()
    yield
    # Shutdown
    await close_redis()


app = FastAPI(title="Advanced Async Auth System", lifespan=lifespan)

security = HTTPBearer()
router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Dependency: get current authenticated user ────────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials

    if await is_token_blacklisted(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    try:
        payload = decode_token(token, token_type="access")
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/register", response_model=UserRegistrationResponse, status_code=201)
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/login", response_model=TokenExchangeResponse)
async def login(
    user_credentials: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == user_credentials.email))
    user = result.scalars().first()

    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )
    refresh_token = create_token(
        data={"sub": user.email},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserRegistrationResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh", response_model=TokenExchangeResponse)
async def refresh_token(refresh_data: dict = Body(...)):
    refresh_token_str = refresh_data.get("refresh_token")
    if not refresh_token_str:
        raise HTTPException(status_code=400, detail="Refresh token is required")

    try:
        payload = decode_token(refresh_token_str, token_type="refresh")
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc

    new_access_token = create_token(
        data={"sub": email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token_str,
        "token_type": "bearer",
    }


@router.post("/logout", response_model=StandardActionResponse)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    await blacklist_token(token, ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return {"detail": "Successfully logged out"}


app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Advanced Async Auth System is Running"}
