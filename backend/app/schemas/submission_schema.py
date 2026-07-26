from pydantic import BaseModel, Field


class SubmissionSignoffRequest(BaseModel):
    status: str = Field(default="ready", examples=["ready", "ready_with_notes", "blocked"])
    reviewerName: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2500)
    includedArtifacts: list[str] = Field(default_factory=list)
