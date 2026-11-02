"""Shapes of the JSON the API accepts, with their validation rules.

Pydantic checks every incoming body against these classes before our route
code runs. If anything is wrong, FastAPI raises a RequestValidationError,
which main.py turns into a 422 response with one message per field.

The API contract uses camelCase (clientName); Python uses snake_case
(client_name). `alias_generator=to_camel` maps between the two, so the JSON
says clientName while the Python code says client_name.
"""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",          # unknown fields (e.g. "id" or "userId") are dropped, never stored
        allow_inf_nan=False,     # reject NaN / Infinity, which Python's JSON parser would accept
    )


# --- Auth -----------------------------------------------------------------

# Deliberately loose: "something@something.something". Real validation of an
# email address is only possible by sending mail to it.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(CamelModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address")
        return value


class LoginIn(CamelModel):
    # No strength rules on login: just check what was sent.
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        return value.strip().lower()


# --- Sites ----------------------------------------------------------------

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SiteIn(CamelModel):
    """Body of POST /api/sites and PUT /api/sites/{id}."""

    client_name: Annotated[NonEmptyText, StringConstraints(max_length=200)]
    address: Annotated[NonEmptyText, StringConstraints(max_length=500)]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # Optional in the contract (roofAreaM2?). If sent, it must be positive.
    roof_area_m2: float | None = Field(default=None, gt=0, le=100_000)
    # Upper bound is a sanity check: 1000 kWp is far beyond any home roof.
    peak_kwp: float = Field(gt=0, le=1000)
