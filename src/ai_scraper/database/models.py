from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class PromptItem(Base):
    __tablename__ = 'prompt_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_platform: Mapped[str] = mapped_column(String)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<PromptItem(id={self.id}, source='{self.source_platform}', prompt='{self.prompt[:20]}...')>"
