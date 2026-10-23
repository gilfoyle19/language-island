"""HTTP request and response models for text conversations."""

from __future__ import annotations

from pydantic import BaseModel, Field

from language_island.curriculum.models import CEFRLevel
from language_island.tutor.models import TutorReply


class StartConversationRequest(BaseModel):
    learner_id: str | None = None
    display_name: str = Field(default="Learner", min_length=1, max_length=100)
    level: CEFRLevel = CEFRLevel.A1
    scenario_id: str | None = None
    personality_id: str | None = None


class StartConversationResponse(BaseModel):
    learner_id: str
    session_id: str
    island_id: str
    level: CEFRLevel
    scenario_id: str
    personality_id: str
    opening: TutorReply


class LearnerTurnRequest(BaseModel):
    text: str = Field(min_length=1)
