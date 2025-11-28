from contextlib import asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from absurd_test.config import get_settings


def get_engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url)


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def get_async_engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, echo=False)


async_session_maker = None


def get_async_session_maker():
    global async_session_maker
    if async_session_maker is None:
        engine = get_async_engine()
        async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session_maker


@asynccontextmanager
async def get_async_session():
    maker = get_async_session_maker()
    async with maker() as session:
        yield session
