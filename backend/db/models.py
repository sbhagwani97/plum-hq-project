"""
backend/db/models.py
SQLAlchemy models for claims persistence.
"""
from sqlalchemy import Column, String, Float, DateTime, JSON
from datetime import datetime
from backend.db.database import Base

class ClaimRecord(Base):
    __tablename__ = "claims"

    claim_id = Column(String, primary_key=True, index=True)
    member_id = Column(String, index=True)
    claim_category = Column(String)
    claimed_amount = Column(Float)
    approved_amount = Column(Float, nullable=True)
    decision = Column(String, nullable=True)
    status = Column(String)
    treatment_date = Column(String)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Store JSON strings for flexible nested data
    reasons = Column(JSON, nullable=True)
    adjustments = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)
    trace = Column(JSON, nullable=True)
