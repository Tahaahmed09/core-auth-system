from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
import os

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# JWT settings - in production load these from environment variables
ACCESS_SECRET_KEY = os.getenv("ACCESS_SECRET_KEY", "super_secret_access_key_change_in_production")
REFRESH_SECRET_KEY = os.getenv("REFRESH_SECRET_KEY", "different_secret_refresh_key_change_in_production")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "type": token_type})

    secret = ACCESS_SECRET_KEY if token_type == "access" else REFRESH_SECRET_KEY
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def decode_token(token: str, token_type: str) -> dict:
    secret = ACCESS_SECRET_KEY if token_type == "access" else REFRESH_SECRET_KEY
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    return payload
