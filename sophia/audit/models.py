"""SQLAlchemy ORM models for the audit database.

Tables are append-only. Records cannot be modified or deleted through the API.
Separate from the memory system (ADR-016).
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Decision(Base):
    """Top-level audit record for one pipeline run."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    hat_name: Mapped[str] = mapped_column(String(100))
    input_message: Mapped[str] = mapped_column(Text)
    intent: Mapped[dict] = mapped_column(JSON)
    risk_tier: Mapped[str] = mapped_column(String(10))
    action_taken: Mapped[str] = mapped_column(String(200))
    response: Mapped[str] = mapped_column(Text)
    bypassed: Mapped[bool] = mapped_column(default=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    proposals: Mapped[list["DecisionProposal"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )
    trees: Mapped[list["DecisionTree"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["DecisionEvaluation"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )
    outcome: Mapped["DecisionOutcome | None"] = relationship(
        back_populates="decision", uselist=False
    )
    feedback_entries: Mapped[list["Feedback"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )
    hat_config_snapshot: Mapped["HatConfigSnapshot | None"] = relationship(
        back_populates="decision", uselist=False, cascade="all, delete-orphan"
    )


class DecisionProposal(Base):
    """Candidate action proposed during a pipeline run."""

    __tablename__ = "decision_proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"))
    rank: Mapped[int] = mapped_column(default=0)
    tool_name: Mapped[str] = mapped_column(String(200))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    expected_outcome: Mapped[str] = mapped_column(Text, default="")

    decision: Mapped["Decision"] = relationship(back_populates="proposals")


class DecisionTree(Base):
    """Serialized consequence tree for a candidate action."""

    __tablename__ = "decision_trees"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"))
    candidate_tool_name: Mapped[str] = mapped_column(String(200))
    tree_data: Mapped[dict] = mapped_column(JSON)
    total_nodes: Mapped[int] = mapped_column(default=0)
    worst_harm: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_benefit: Mapped[float | None] = mapped_column(Float, nullable=True)

    decision: Mapped["Decision"] = relationship(back_populates="trees")


class DecisionEvaluation(Base):
    """Per-evaluator result from a pipeline run."""

    __tablename__ = "decision_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"))
    evaluator_name: Mapped[str] = mapped_column(String(50))
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    key_concerns: Mapped[list] = mapped_column(JSON, default=list)

    decision: Mapped["Decision"] = relationship(back_populates="evaluations")


class DecisionOutcome(Base):
    """Reported actual outcome after execution."""

    __tablename__ = "decision_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"), unique=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    actual_outcome: Mapped[str] = mapped_column(Text)
    outcome_matches_prediction: Mapped[bool | None] = mapped_column(nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    decision: Mapped["Decision"] = relationship(back_populates="outcome")


class Feedback(Base):
    """Human corrections and overrides on YELLOW/ORANGE tier decisions."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    feedback_type: Mapped[str] = mapped_column(String(50))  # "override", "correction", "note"
    original_tier: Mapped[str] = mapped_column(String(10))
    override_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")

    decision: Mapped["Decision"] = relationship(back_populates="feedback_entries")


class HatConfigSnapshot(Base):
    """Versioned hat configuration at the time of a decision."""

    __tablename__ = "hat_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"), unique=True)
    hat_name: Mapped[str] = mapped_column(String(100))
    hat_version: Mapped[str] = mapped_column(String(20))
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    stakeholders: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluator_config: Mapped[dict] = mapped_column(JSON, default=dict)

    decision: Mapped["Decision"] = relationship(back_populates="hat_config_snapshot")
