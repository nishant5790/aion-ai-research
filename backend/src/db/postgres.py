import os
from sqlalchemy import create_engine, Column, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional
from contextlib import contextmanager

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    google_id = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=True)
    name = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    last_login = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

class Database:
    def __init__(self):
        # database_url = os.getenv("DATABASE_URL")
        database_url = "postgresql://postgres:Gate@2026@3@db.urjlnpjvrqbfylrwxlfc.supabase.co:5432/postgres"
        if not database_url:
            # For testing or when database is not configured
            self.engine = None
            self.SessionLocal = None
            return

        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self):
        """Create all tables defined in the models."""
        if self.engine:
            Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Session:
        """Context manager for database sessions."""
        if not self.engine:
            # For testing, return a mock session
            from unittest.mock import MagicMock
            mock_session = MagicMock()
            yield mock_session
            return

        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_or_create_user(self, google_id: str, email: Optional[str] = None,
                          name: Optional[str] = None) -> User:
        """Get existing user or create new one, updating last_login."""
        if not self.engine:
            # For testing, return a mock user
            from unittest.mock import MagicMock
            mock_user = MagicMock()
            mock_user.google_id = google_id
            mock_user.email = email
            mock_user.name = name
            return mock_user

        with self.get_session() as session:
            user = session.query(User).filter(User.google_id == google_id).first()
            if user:
                # Update user info and last login
                user.email = email or user.email
                user.name = name or user.name
                user.last_login = func.now()
            else:
                # Create new user
                user = User(
                    google_id=google_id,
                    email=email,
                    name=name
                )
                session.add(user)
            session.commit()
            session.refresh(user)
            return user

# Global database instance
db = Database()</content>
<parameter name="filePath">/workspaces/aion-ai-research/backend/src/db/postgres.py