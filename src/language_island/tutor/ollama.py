"""Ollama implementation of the structured tutor model boundary."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from language_island.tutor.models import (
    TutorAssessment,
    TutorEvaluation,
    TutorModelInput,
    TutorUtterance,
)

SYSTEM_PROMPT = """You are a German conversation tutor inside one language island.
Stay in the assigned scenario and personality. Evaluate only meaningful German errors; do not
interrupt for harmless stylistic variation. Keep tutor turns short enough for spoken dialogue.
Evidence item_id values must come from the supplied vocabulary and grammar dictionaries. Mark
evidence successful only when the learner used the item correctly. Never reveal private chain of
thought. Return only the requested structured result."""

ASSESS_PROMPT = """Evaluate the learner utterance. If it has a meaningful vocabulary or grammar
error, set is_correct=false, fill every correction field, and leave both tutor fields empty. The
retry_text must be the exact German repair the learner must repeat. If it is correct, set
is_correct=true, fill both tutor fields with one natural follow-up, and leave every correction
field empty. Write correction_explanation in the requested explanation_language. Whenever the
utterance demonstrates or violates a supplied vocabulary or grammar item, include evidence for
that item; do not invent item IDs."""

OPENING_PROMPT = """Begin the role-play as the assigned character with one short German turn that
invites the learner to act in the supplied situation, normally with a question, plus an English
translation. learner_english must be empty. Do not correct or evaluate anything."""

CONTINUE_PROMPT = """The learner has just repeated the required correction successfully.
Translate that learner utterance, acknowledge it naturally, and continue the role-play with one
short follow-up question. Record any skill evidence as not independent."""


class OllamaTutorModel:
    def __init__(self, *, model: str, base_url: str) -> None:
        chat = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0.3,
            reasoning=False,
            num_ctx=8192,
        )
        self.evaluation_model = chat.with_structured_output(
            TutorEvaluation, method="json_schema"
        )
        self.utterance_model = chat.with_structured_output(
            TutorUtterance, method="json_schema"
        )

    async def generate(self, request: TutorModelInput) -> TutorAssessment:
        payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        if request.mode == "assess":
            result: Any = await self.evaluation_model.ainvoke(
                [
                    SystemMessage(content=f"{SYSTEM_PROMPT}\n\n{ASSESS_PROMPT}"),
                    HumanMessage(content=payload),
                ]
            )
            evaluation = (
                result
                if isinstance(result, TutorEvaluation)
                else TutorEvaluation.model_validate(result)
            )
            return evaluation.to_assessment()

        mode_prompt = OPENING_PROMPT if request.mode == "opening" else CONTINUE_PROMPT
        result = await self.utterance_model.ainvoke(
            [
                SystemMessage(content=f"{SYSTEM_PROMPT}\n\n{mode_prompt}"),
                HumanMessage(content=payload),
            ]
        )
        utterance = (
            result
            if isinstance(result, TutorUtterance)
            else TutorUtterance.model_validate(result)
        )
        return utterance.to_assessment()
