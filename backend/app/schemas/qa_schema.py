from pydantic import BaseModel, Field


class QaDemoRunRequest(BaseModel):
    result: str = Field(default="pass", examples=["pass", "warn", "fail"])
    notes: str = Field(default="", max_length=2000)
    reviewerName: str = Field(default="", max_length=120)
    checkedSteps: list[int] = Field(default_factory=list)
