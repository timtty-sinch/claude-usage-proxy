from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ApiRequest(Base):
    __tablename__ = "api_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    anthropic_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    is_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    system_prompt_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_user_message_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    complexity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(4), nullable=True)

    usage: Mapped["ApiUsage | None"] = relationship(
        "ApiUsage", back_populates="request", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        Index("ix_api_requests_requested_at", "requested_at"),
        Index("ix_api_requests_model", "model"),
    )


class ApiToolUse(Base):
    __tablename__ = "api_tool_uses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("api_requests.id", ondelete="CASCADE"))
    tool_use_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (Index("ix_api_tool_uses_request_id", "request_id"),)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("api_requests.id", ondelete="CASCADE"), unique=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cache_read_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cache_creation_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    request: Mapped["ApiRequest"] = relationship("ApiRequest", back_populates="usage")

    __table_args__ = (Index("ix_api_usage_total_cost_usd", "total_cost_usd"),)
