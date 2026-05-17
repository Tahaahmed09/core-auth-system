import os
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import Base, get_db
from app.redis_client import in_memory_blacklist

db_user = os.getenv("PG_USER", "postgres")
db_pass = os.getenv("PG_PASS", "postgres")
db_host = os.getenv("PG_HOST", "localhost")
db_name = os.getenv("PG_NAME", "auth_db")

TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:5432/{db_name}"
)

# NullPool: har operation ke baad connection band — koi sharing nahi
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool,
)

TestSessionFactory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(setup_db):
    in_memory_blacklist.clear()

    async def override_get_db():
        async with TestSessionFactory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()