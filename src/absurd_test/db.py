from contextlib import asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from absurd_test.config import get_settings

# Global engines and session makers (reused across requests)
_sync_engine = None
_async_engine = None
_async_session_maker = None


def get_engine():
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        url = settings.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        _sync_engine = create_engine(url)
    return _sync_engine


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        settings = get_settings()
        url = settings.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        _async_engine = create_async_engine(
            url,
            echo=False,
            pool_size=20,
            max_overflow=40,
        )
    return _async_engine


def get_async_session_maker():
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_async_engine()
        _async_session_maker = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_maker


@asynccontextmanager
async def get_async_session():
    maker = get_async_session_maker()
    async with maker() as session:
        yield session
