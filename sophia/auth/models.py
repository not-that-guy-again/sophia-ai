from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String

from sophia.audit.models import Base


class APIKeyRecord(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_id = Column(String(24), unique=True, nullable=False, index=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    hat_name = Column(String(100), nullable=False)
    scopes = Column(JSON, nullable=False)
    rate_limit_rpm = Column(Integer, nullable=False, default=60)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
