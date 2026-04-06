from pydantic import BaseModel, Field
from typing import Optional, List


class LogCreate(BaseModel):
    incidentId: str
    fileName: str
    content: str


class LogOut(BaseModel):
    id: str = Field(alias="_id")
    incidentId: str
    fileName: str
    content: str
    parsedErrors: List[str] = []

    class Config:
        populate_by_name = True
