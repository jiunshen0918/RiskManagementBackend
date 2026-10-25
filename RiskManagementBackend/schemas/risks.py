from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RiskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: Annotated[str, Field(min_length=3, max_length=200)]
    description: Annotated[str, Field(min_length=10, max_length=4000)]
    category: Annotated[str, Field(max_length=120)] | None = None
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    status: Literal["Open", "In Progress", "Closed"] = "Open"


class RiskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    sys_id: str | None = None
    number: str | None = None
    title: str
    description: str | None
    category: str | None = None
    score: str | None = None
    risk_score: int | None = None
    severity: str
    likelihood: int | None = None
    impact: int | None = None
    status: str
    source: Literal["Local", "ServiceNow"]
    created_at: str
    updated_at: str
