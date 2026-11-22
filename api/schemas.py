"""Request and response models. Input models reject unknown fields, so a typo cannot
silently turn an exact classification into an ML estimate."""
from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Optional

from pydantic import (BaseModel, BeforeValidator, ConfigDict, Field, field_validator,
                      model_validator)

from api.db.models import Role
from api.deps import MAX_INT
from api.security import MAX_PASSWORD, MIN_PASSWORD

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _no_bool(value):
    if isinstance(value, bool):
        raise ValueError("Expected a number, not true/false.")
    return value


def _check_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 255 or not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address.")
    return value


def _check_encodable(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Text contains invalid characters.") from exc
    return value


Number = Annotated[float, BeforeValidator(_no_bool)]
Password = Annotated[str, Field(min_length=MIN_PASSWORD, max_length=MAX_PASSWORD),
                     BeforeValidator(lambda v: _check_encodable(v) if isinstance(v, str) else v)]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(_Input):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD)

    _email = field_validator("email")(_check_email)
    _password = field_validator("password")(_check_encodable)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    must_change_password: bool = False


class RegisterIn(_Input):
    email: str = Field(max_length=320)
    full_name: str = Field(min_length=2, max_length=255)
    password: Password

    _email = field_validator("email")(_check_email)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(_check_encodable(value).split())
        if len(value) < 2:
            raise ValueError("Full name is too short.")
        return value


class ChangePasswordIn(_Input):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD)
    new_password: Password

    _current = field_validator("current_password")(_check_encodable)


class UserIn(_Input):
    email: str = Field(max_length=320)
    full_name: str = Field(min_length=2, max_length=255)
    password: Password
    role: Role = Role.analyst

    _email = field_validator("email")(_check_email)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(_check_encodable(value).split())
        if len(value) < 2:
            raise ValueError("Full name is too short.")
        return value


class UserUpdate(_Input):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    password: Optional[Password] = None

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(_check_encodable(value).split())
        if len(value) < 2:
            raise ValueError("Full name is too short.")
        return value

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Supply at least one field to change.")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    must_change_password: bool = False


class _Measurements(_Input):
    bulk_density: Number = Field(gt=0, le=5, allow_inf_nan=False, description="g/mL")
    tapped_density: Optional[Number] = Field(
        None, gt=0, le=5, allow_inf_nan=False,
        description="g/mL. Supplying this gives an EXACT class.")
    angle_of_repose: Optional[Number] = Field(None, ge=0, le=90, allow_inf_nan=False)
    particle_size_um: Optional[Number] = Field(None, gt=0, le=100_000, allow_inf_nan=False)
    moisture_percent: Optional[Number] = Field(None, ge=0, le=100, allow_inf_nan=False)
    flow_rate_g_s: Optional[Number] = Field(None, ge=0, le=10_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def _tapped_not_below_bulk(self):
        if self.tapped_density is not None and self.tapped_density < self.bulk_density:
            raise ValueError("Tapped density cannot be below bulk density.")
        return self


class ClassifyIn(_Measurements):
    sample_id: Optional[int] = Field(None, ge=1, le=MAX_INT)


class SampleIn(_Measurements):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    material_name: str = Field(min_length=1, max_length=255)
    material_type: Optional[str] = Field(None, max_length=64)
    batch_no: str = Field(min_length=1, max_length=64)
    replicate_no: int = Field(1, ge=1, le=1000)
    sample_weight_g: Optional[Number] = Field(None, gt=0, le=1_000_000, allow_inf_nan=False)
    method_ref: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=5000)

    @field_validator("material_name")
    @classmethod
    def _material(cls, value: str) -> str:
        return " ".join(_check_encodable(value).split())

    @field_validator("material_type", "batch_no", "method_ref", "notes")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return _check_encodable(value) if value is not None else None


class SampleOut(BaseModel):
    id: int
    material_id: int
    material_name: str
    operator_id: int
    batch_no: str
    replicate_no: int
    measured_at: dt.datetime
    sample_weight_g: Optional[float]
    bulk_density: float
    tapped_density: Optional[float]
    angle_of_repose: Optional[float]
    particle_size_um: Optional[float]
    moisture_percent: Optional[float]
    flow_rate_g_s: Optional[float]
    method_ref: Optional[str]
    notes: Optional[str]
    is_voided: bool
    void_reason: Optional[str]


class VoidIn(_Input):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        value = _check_encodable(value).strip()
        if len(value) < 3:
            raise ValueError("Give a reason of at least 3 characters.")
        return value


class ReviewIn(_Input):
    comment: str = Field("", max_length=2000)

    _comment = field_validator("comment")(_check_encodable)


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    material_type: Optional[str]
