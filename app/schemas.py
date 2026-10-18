"""Validated request and response schemas."""
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PositionAnalysisRequest(StrictModel):
    fen: str = Field(min_length=8, max_length=200)
    depth: int = Field(default=12, ge=4, le=20)
    time_limit: float = Field(default=0.25, gt=0.0, le=3.0, description="Maximum search time in seconds; paired with the depth limit")
    multipv: int = Field(default=1, ge=1, le=3, description="Number of candidate lines")


class GameAnalysisRequest(StrictModel):
    pgn: str = Field(min_length=10, max_length=150_000)
    depth: int = Field(default=12, ge=4, le=18)
    time_limit: float = Field(default=0.2, gt=0.0, le=1.5, description="Search time per position in seconds; paired with the depth limit")
    max_plies: int = Field(default=100, ge=1, le=160, description="Maximum half-moves allowed in a review")
