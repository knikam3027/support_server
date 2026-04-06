from pydantic import BaseModel, Field
from typing import Optional, List


class SolutionCreate(BaseModel):
    incidentId: str
    recommendedSteps: List[str] = []
    generatedScript: Optional[str] = None


class SolutionOut(BaseModel):
    id: str = Field(alias="_id")
    incidentId: str
    recommendedSteps: List[str] = []
    generatedScript: Optional[str] = None

    class Config:
        populate_by_name = True


class FeedbackCreate(BaseModel):
    incidentId: str
    accepted: bool
    scriptWorked: Optional[bool] = None
    rating: Optional[int] = None
    comments: Optional[str] = None
