from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError
from database import get_db, User, engine, Base
from schemas import UserCreate, UserRegistrationResponse, TokenExchangeResponse, StandardActionResponse
from auth_utils import hash_password, verify_password, create_token, decode_token
from redis_client import init_redis, close_redis, blacklist_token, is_token_blacklisted

app = FastAPI(title="Advanced Async Auth System")

# Security
security = HTTPBearer()

# ================== LIFESPAN EVENTS ==================
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_redis()

@app.on_event("shutdown")
async def shutdown():
    await close_redis()


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserRegistrationResponse, status_code=201)
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    query = select(User).where(User.email == user_data.email)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password)
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/login", response_model=TokenExchangeResponse)
async def login(user_credentials: UserCreate, db: AsyncSession = Depends(get_db)):
    query = select(User).where(User.email == user_credentials.email)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_token(
        data={"sub": user.email}, 
        expires_delta=timedelta(minutes=15), 
        token_type="access"
    )
    refresh_token = create_token(
        data={"sub": user.email}, 
        expires_delta=timedelta(days=7), 
        token_type="refresh"
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# Get Current User with Blacklist Check
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    token = credentials.credentials
    if await is_token_blacklisted(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    try:
        payload = decode_token(token, token_type="access")
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# Protected Route Example
@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout", response_model=StandardActionResponse)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    # Blacklist for remaining time (15 min = 900 seconds)
    await blacklist_token(token, 900)
    return {"detail": "Successfully logged out"}


# Token Refresh Endpoint


@router.post("/refresh", response_model=TokenExchangeResponse)
async def refresh_token(refresh_data: dict = Body(...)):
    refresh_token_str = refresh_data.get("refresh_token")
    
    if not refresh_token_str:
        raise HTTPException(status_code=400, detail="Refresh token is required")

    try:
        payload = decode_token(refresh_token_str, token_type="refresh")
        email: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    except:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Naya Access Token generate karo
    new_access_token = create_token(
        data={"sub": email},
        expires_delta=timedelta(minutes=15),
        token_type="access"
    )

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token_str,   # Same refresh token (Document compliant)
        "token_type": "bearer"
    }

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Advanced Async Auth System is Running"}