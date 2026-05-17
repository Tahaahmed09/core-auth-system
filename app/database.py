from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime
import datetime
import os

from dotenv import load_dotenv

load_dotenv()

db_user = os.getenv("PG_USER", "postgres")
db_pass = os.getenv("PG_PASS", "postgres")
db_host = os.getenv("PG_HOST", "localhost")
db_name = os.getenv("PG_NAME", "auth_db")

DATABASE_URL = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:5432/{db_name}"

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
