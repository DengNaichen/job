"""
Source schemas for API request/response handling.

Contains:
- SourceCreate: Schema for creating a new source
- SourceUpdate: Schema for updating a source (partial update)
- SourceRead: Schema for reading a source
- Response schemas for API responses
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.source import PlatformType


class SourceCreate(BaseModel):
    """Schema for creating a new source."""
    name: str = Field(..., min_length=1, max_length=255, description="Company name")
    platform: PlatformType = Field(..., description="Platform type")
    identifier: str = Field(..., min_length=1, max_length=255, description="Platform identifier")
    enabled: bool = Field(default=True, description="Enabled status")
    notes: str | None = Field(default=None, max_length=1000, description="Notes")

    @field_validator("name", "identifier")
    @classmethod
    def strip_and_validate_non_empty(cls, v: str) -> str:
        """Strip whitespace and validate non-empty."""
        value = v.strip()
        if not value:
            raise ValueError("Field cannot be empty or contain only whitespace")
        return value


class SourceUpdate(BaseModel):
    """Schema for updating a source (partial update)."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    platform: PlatformType | None = Field(default=None)
    identifier: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = Field(default=None)
    notes: str | None = Field(default=None)

    @field_validator("name", "identifier")
    @classmethod
    def strip_and_validate_non_empty(cls, v: str | None) -> str | None:
        """Strip whitespace and validate non-empty if provided."""
        if v is None:
            return None
        value = v.strip()
        if not value:
            raise ValueError("Field cannot be empty or contain only whitespace")
        return value


class SourceRead(BaseModel):
    """Schema for reading a source."""
    id: str
    name: str
    platform: PlatformType
    identifier: str
    enabled: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ErrorDetail(BaseModel):
    """Error detail structure."""
    code: str
    message: str


class SourceResponse(BaseModel):
    """Single source response wrapper."""
    success: bool = True
    data: SourceRead
    message: str = "操作成功"


class SourceListResponse(BaseModel):
    """Source list response wrapper."""
    success: bool = True
    data: list[SourceRead]
    total: int


class SourceSlugListResponse(BaseModel):
    """Slug list response wrapper."""
    success: bool = True
    platform: PlatformType
    data: list[str]
    total: int


class ErrorResponse(BaseModel):
    """Error response wrapper."""
    success: bool = False
    error: ErrorDetail


class DeleteResponse(BaseModel):
    """Delete response wrapper."""
    success: bool = True
    message: str = "数据源已删除"
