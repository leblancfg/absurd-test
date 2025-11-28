from sqlalchemy import create_engine
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
