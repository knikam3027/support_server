from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class IncidentCreate(BaseModel):
    title: str
    description: str
    category: Optional[str] = "General"
    system: Optional[str] = "Unknown"
    source: Optional[str] = "Manual"


class IncidentOut(BaseModel):
    id: str = Field(alias="_id")
    title: str
    description: str
    category: Optional[str] = "General"
    system: Optional[str] = "Unknown"
    severity: Optional[str] = None
    status: str = "Open"
    source: Optional[str] = "Manual"
    createdAt: str
    predictedRootCause: Optional[str] = None
    confidence: Optional[float] = None
    summary: Optional[str] = None

    class Config:
        populate_by_name = True


class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    predictedRootCause: Optional[str] = None
    confidence: Optional[float] = None
    summary: Optional[str] = None
