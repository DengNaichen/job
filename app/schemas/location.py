from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LocationBase(BaseModel):
    canonical_key: str
    display_name: str
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geonames_id: int | None = None


class LocationCreate(LocationBase):
    source_data: dict[str, Any] | None = None


class LocationRead(LocationBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobLocationRead(BaseModel):
    id: str
    job_id: str
    location_id: str
    is_primary: bool
    source_raw: str | None
    created_at: datetime

    # Optional nested location for API responses
    location: LocationRead | None = None

    model_config = {"from_attributes": True}
