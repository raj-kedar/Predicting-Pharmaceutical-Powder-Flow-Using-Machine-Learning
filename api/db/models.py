"""
Database schema, compatible with the original flowtool.db.

A result must be defensible months later: every prediction records its engine,
model version and author, and nothing is hard-deleted. This follows the shape
of ALCOA+ and 21 CFR Part 11 audit trails, although the system itself is not GMP-validated.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (JSON, Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint, event)
from sqlalchemy.orm import Session, declarative_base, relationship
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite drops timezones; always store UTC and always return an aware datetime."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime rejected; use an aware UTC datetime.")
        return value.astimezone(dt.timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)


class Role(str, enum.Enum):
    analyst = "analyst"
    reviewer = "reviewer"
    admin = "admin"
    superadmin = "superadmin"   # admin powers plus website content; only superadmins manage superadmins


STAFF = (Role.reviewer, Role.admin, Role.superadmin)
ADMINS = (Role.admin, Role.superadmin)


class EnginePath(str, enum.Enum):
    rule = "rule"
    ml = "ml"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.analyst)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)
    last_login_at = Column(UTCDateTime)

    samples = relationship("Sample", back_populates="operator")
    predictions = relationship("Prediction", back_populates="user",
                               foreign_keys="Prediction.user_id")


class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    material_type = Column(String(64))
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    samples = relationship("Sample", back_populates="material")


class Sample(Base):
    """One physical measurement event. Replicates are separate rows."""
    __tablename__ = "samples"
    __table_args__ = (UniqueConstraint("material_id", "batch_no", "replicate_no",
                                       name="uq_sample_identity"),)
    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    batch_no = Column(String(64), nullable=False)
    replicate_no = Column(Integer, nullable=False, default=1)
    measured_at = Column(UTCDateTime, nullable=False, default=utcnow)
    sample_weight_g = Column(Float)
    bulk_density = Column(Float, nullable=False)
    tapped_density = Column(Float)
    angle_of_repose = Column(Float)
    particle_size_um = Column(Float)
    moisture_percent = Column(Float)
    flow_rate_g_s = Column(Float)
    method_ref = Column(String(255))
    notes = Column(Text)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)
    is_voided = Column(Boolean, nullable=False, default=False)
    void_reason = Column(Text)

    material = relationship("Material", back_populates="samples")
    operator = relationship("User", back_populates="samples")
    predictions = relationship("Prediction", back_populates="sample")


class Prediction(Base):
    """A classification result, frozen when produced. Only review fields change, once."""
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True)
    sample_id = Column(Integer, ForeignKey("samples.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    path = Column(Enum(EnginePath), nullable=False)
    model_version = Column(String(32))
    predicted_class = Column(String(64), nullable=False)
    acceptable = Column(Boolean)
    confidence = Column(Float)
    carr_index = Column(Float)
    hausner = Column(Float)
    hausner_class = Column(String(64))
    criteria_agree = Column(Boolean)
    inputs = Column(JSON, nullable=False)
    caveats = Column(JSON)
    basis = Column(Text)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(UTCDateTime)
    review_comment = Column(Text)

    sample = relationship("Sample", back_populates="predictions")
    user = relationship("User", foreign_keys=[user_id], back_populates="predictions")


class AuditLog(Base):
    """Append-only, enforced by the ORM guard below and by database triggers."""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    at = Column(UTCDateTime, nullable=False, default=utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    actor_email = Column(String(255))
    action = Column(String(64), nullable=False)
    entity = Column(String(64))
    entity_id = Column(Integer)
    detail = Column(JSON)
    ip_address = Column(String(64))


class Subscription(Base):
    """A user's paid plan. No row, or an expired one, means the Free plan."""
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    plan = Column(String(16), nullable=False)
    current_period_end = Column(UTCDateTime, nullable=False)
    source = Column(String(16), nullable=False)          # razorpay / admin
    updated_at = Column(UTCDateTime, nullable=False, default=utcnow)


class Payment(Base):
    """One Razorpay order. Amounts come from the server's plan table, never the client."""
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan = Column(String(16), nullable=False)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    period_days = Column(Integer, nullable=False)
    mode = Column(String(8), nullable=False)             # test / live
    razorpay_order_id = Column(String(64), nullable=False, unique=True)
    razorpay_payment_id = Column(String(64), unique=True)
    status = Column(String(16), nullable=False, default="created")   # created / paid
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)
    paid_at = Column(UTCDateTime)


class StoredImage(Base):
    """An uploaded image after re-encoding. The original upload is never kept."""
    __tablename__ = "images"
    id = Column(String(32), primary_key=True)            # random hex, also the storage name
    kind = Column(String(16), nullable=False)            # profile / site
    storage_key = Column(String(128), nullable=False, unique=True)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)


class UserProfile(Base):
    """Profile photo and its privacy lock. Locked photos are visible to the owner and admins only."""
    __tablename__ = "user_profiles"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    photo_id = Column(String(32), ForeignKey("images.id"))
    photo_locked = Column(Boolean, nullable=False, default=True)
    updated_at = Column(UTCDateTime, nullable=False, default=utcnow)


class SiteContent(Base):
    """Editable public website content, managed by superadmins."""
    __tablename__ = "site_content"
    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(UTCDateTime, nullable=False, default=utcnow)
    updated_by_id = Column(Integer, ForeignKey("users.id"))


class PasswordChangeRequired(Base):
    """The user signed in with a temporary password and must set their own before anything else."""
    __tablename__ = "password_change_required"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)


class LoginThrottle(Base):
    """Failed-login counter per (email, client address)."""
    __tablename__ = "login_throttle"
    key = Column(String(330), primary_key=True)
    failures = Column(Integer, nullable=False, default=0)
    locked_until = Column(UTCDateTime)
    updated_at = Column(UTCDateTime, nullable=False, default=utcnow, index=True)


@event.listens_for(Session, "before_flush")
def _protect_records(session, _context, _instances):
    for obj in session.dirty:
        if isinstance(obj, AuditLog) and session.is_modified(obj):
            raise ValueError("The audit log is append-only.")
    for obj in session.deleted:
        if isinstance(obj, (AuditLog, Prediction, Sample, Payment)):
            raise ValueError(f"{type(obj).__name__} records are never hard-deleted.")
