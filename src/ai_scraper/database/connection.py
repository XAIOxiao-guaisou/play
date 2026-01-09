import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from .models import Base
from ..utils.logging import logger

class DatabaseManager:
    def __init__(self, db_url: str = "sqlite:///data/ai_prompts.db"):
        self.db_url = db_url
        self._ensure_data_dir()
        self.engine = create_engine(self.db_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _ensure_data_dir(self):
        if "sqlite" in self.db_url:
             path = self.db_url.replace("sqlite:///", "")
             directory = os.path.dirname(path)
             if directory and not os.path.exists(directory):
                 os.makedirs(directory)

    def init_db(self):
        """Initialize database schema."""
        logger.info(f"Initializing database at {self.db_url}")
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Session:
        """Provide a transactional scope around a series of operations."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

# Global instance
db_manager = DatabaseManager()
