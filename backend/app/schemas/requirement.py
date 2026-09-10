from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequirementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    value: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=100)
    is_mandatory: bool = True


class RequirementUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    value: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=100)
    is_mandatory: bool | None = None


class RequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    procurement_id: UUID
    name: str
    description: str | None
    category: str | None
    value: str | None
    unit: str | None
    is_mandatory: bool
    created_at: datetime
