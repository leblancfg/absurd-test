from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class AgentJob(Base):
    """Tracks agent jobs submitted through the app."""

    __tablename__ = "agent_jobs"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    tag = Column(String(100), nullable=True, index=True)
    result = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Webhook(Base):
    """Registered webhooks for task completion callbacks."""

    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True)
    tag = Column(String(100), nullable=False, index=True)
    url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
