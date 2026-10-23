"""Conversation graph enforcing correction-before-continuation."""

from __future__ import annotations

import re
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from language_island.curriculum.models import CEFRLevel, CurriculumBundle
from language_island.progress import MetricKind
from language_island.storage import LearningStore
from language_island.storage.models import ConversationSession
from language_island.tutor.models import (
    DialogueLine,
    PendingCorrection,
    SkillEvidence,
    TutorAssessment,
    TutorLanguageModel,
    TutorMode,
    TutorModelInput,
    TutorReply,
)


class TurnGraphState(TypedDict, total=False):
    request: TutorModelInput
    pending: PendingCorrection | None
    assessment: TutorAssessment
    reply: TutorReply


class TutorTurnGraph:
    def __init__(self, model: TutorLanguageModel) -> None:
        self.model = model
        builder = StateGraph(TurnGraphState)
        builder.add_node("assess", self._assess)
        builder.add_node("continue_after_retry", self._continue_after_retry)
        builder.add_node("repeat_correction", self._repeat_correction)
        builder.add_node("format_assessment", self._format_assessment)
        builder.add_conditional_edges(
            START,
            self._route,
            {
                "assess": "assess",
                "continue_after_retry": "continue_after_retry",
                "repeat_correction": "repeat_correction",
            },
        )
        builder.add_edge("assess", "format_assessment")
        builder.add_edge("continue_after_retry", "format_assessment")
        builder.add_edge("repeat_correction", END)
        builder.add_edge("format_assessment", END)
        self.graph = builder.compile()

    def _route(self, state: TurnGraphState) -> str:
        pending = state.get("pending")
        if pending is None:
            return "assess"
        if _normalise(state["request"].learner_text) == _normalise(pending.retry_text):
            return "continue_after_retry"
        return "repeat_correction"

    async def _assess(self, state: TurnGraphState) -> TurnGraphState:
        return {"assessment": await self.model.generate(state["request"])}

    async def _continue_after_retry(self, state: TurnGraphState) -> TurnGraphState:
        request = state["request"].model_copy(update={"mode": "continue_after_retry"})
        return {"assessment": await self.model.generate(request)}

    def _repeat_correction(self, state: TurnGraphState) -> TurnGraphState:
        pending = cast(PendingCorrection, state["pending"])
        return {
            "reply": TutorReply(
                status="retry",
                corrected_german=pending.corrected_german,
                corrected_english=pending.corrected_english,
                correction_explanation=pending.explanation,
                required_retry=pending.retry_text,
            )
        }

    def _format_assessment(self, state: TurnGraphState) -> TurnGraphState:
        assessment = state["assessment"]
        if assessment.is_correct:
            reply = TutorReply(
                status="continue",
                learner_english=assessment.learner_english,
                tutor_german=assessment.tutor_german,
                tutor_english=assessment.tutor_english,
                vocabulary_evidence=assessment.vocabulary_evidence,
                grammar_evidence=assessment.grammar_evidence,
            )
        else:
            reply = TutorReply(
                status="retry",
                learner_english=assessment.learner_english,
                corrected_german=assessment.corrected_german,
                corrected_english=assessment.corrected_english,
                correction_explanation=assessment.correction_explanation,
                required_retry=assessment.retry_text,
                vocabulary_evidence=assessment.vocabulary_evidence,
                grammar_evidence=assessment.grammar_evidence,
            )
        return {"reply": reply}

    async def invoke(
        self, request: TutorModelInput, pending: PendingCorrection | None
    ) -> TutorReply:
        result = await self.graph.ainvoke({"request": request, "pending": pending})
        return TutorReply.model_validate(result["reply"])


class TutorEngine:
    def __init__(
        self,
        *,
        model: TutorLanguageModel,
        curriculum: CurriculumBundle,
        store: LearningStore,
    ) -> None:
        self.model = model
        self.curriculum = curriculum
        self.store = store
        self.turn_graph = TutorTurnGraph(model)

    async def opening(self, session_id: str) -> TutorReply:
        conversation = await self._active_session(session_id)
        request = await self._build_request(conversation, mode="opening")
        assessment = await self.model.generate(request)
        if not assessment.is_correct:
            raise ValueError("Tutor model returned a correction for an opening turn")
        reply = TutorReply(
            status="continue",
            tutor_german=assessment.tutor_german,
            tutor_english=assessment.tutor_english,
        )
        await self.store.append_turn(
            session_id=session_id,
            speaker="tutor",
            german_text=cast(str, reply.tutor_german),
            english_translation=reply.tutor_english,
        )
        return reply

    async def handle_turn(self, session_id: str, learner_text: str) -> TutorReply:
        if not learner_text.strip():
            raise ValueError("Learner text cannot be empty")
        conversation = await self._active_session(session_id)
        runtime_state = await self.store.get_tutor_state(session_id)
        pending_data = runtime_state.get("pending_correction")
        pending = PendingCorrection.model_validate(pending_data) if pending_data else None
        request = await self._build_request(
            conversation, mode="assess", learner_text=learner_text
        )
        reply = await self.turn_graph.invoke(request, pending)

        await self.store.append_turn(
            session_id=session_id,
            speaker="learner",
            german_text=learner_text,
            english_translation=reply.learner_english,
        )
        await self._persist_reply(session_id, reply)
        await self._record_evidence(
            session_id,
            conversation.level,
            reply,
            repaired=pending is not None,
        )
        return reply

    async def _active_session(self, session_id: str) -> ConversationSession:
        conversation = await self.store.get_session(session_id)
        if conversation is None:
            raise ValueError(f"Unknown session: {session_id}")
        if conversation.status != "active":
            raise ValueError(f"Session is not active: {session_id}")
        return conversation

    async def _build_request(
        self,
        conversation: ConversationSession,
        *,
        mode: TutorMode,
        learner_text: str = "",
    ) -> TutorModelInput:
        level = CEFRLevel(conversation.level)
        plan = self.curriculum.island.levels[level]
        scenario = next(
            (item for item in plan.scenarios if item.id == conversation.scenario_id), None
        )
        if scenario is None:
            raise ValueError(f"Unknown scenario: {conversation.scenario_id}")
        personality = self.curriculum.personalities.by_id().get(
            conversation.personality_id
        )
        if personality is None:
            raise ValueError(f"Unknown personality: {conversation.personality_id}")
        vocabulary_catalog = self.curriculum.vocabulary.by_id()
        grammar_catalog = self.curriculum.grammar.by_id()
        transcript = await self.store.get_transcript(conversation.id)
        history = [
            DialogueLine(
                speaker=turn.speaker,
                german=turn.german_text,
                english=turn.english_translation,
            )
            for turn in transcript[-12:]
        ]
        return TutorModelInput(
            mode=mode,
            level=level.value,
            scenario_title=scenario.title,
            scenario_situation=scenario.situation,
            success_criteria=scenario.success_criteria,
            personality_name=personality.display_name,
            personality_prompt=personality.role_prompt,
            personality_tone=personality.tone,
            conversational_register=personality.conversational_register,
            explanation_language=cast(
                Literal["en", "de"],
                self.curriculum.island.feedback.explanation_language[level],
            ),
            vocabulary={
                item_id: vocabulary_catalog[item_id].lemma for item_id in plan.vocabulary_ids
            },
            grammar={item_id: grammar_catalog[item_id].title for item_id in plan.grammar_ids},
            history=history,
            learner_text=learner_text,
        )

    async def _persist_reply(self, session_id: str, reply: TutorReply) -> None:
        if reply.status == "retry":
            pending = PendingCorrection(
                corrected_german=cast(str, reply.corrected_german),
                corrected_english=cast(str, reply.corrected_english),
                explanation=cast(str, reply.correction_explanation),
                retry_text=cast(str, reply.required_retry),
            )
            await self.store.set_tutor_state(
                session_id, {"pending_correction": pending.model_dump(mode="json")}
            )
            await self.store.append_turn(
                session_id=session_id,
                speaker="correction",
                german_text=pending.corrected_german,
                english_translation=pending.corrected_english,
            )
            return

        await self.store.set_tutor_state(session_id, {})
        await self.store.append_turn(
            session_id=session_id,
            speaker="tutor",
            german_text=cast(str, reply.tutor_german),
            english_translation=reply.tutor_english,
        )

    async def _record_evidence(
        self,
        session_id: str,
        level: str,
        reply: TutorReply,
        *,
        repaired: bool,
    ) -> None:
        plan = self.curriculum.island.levels[CEFRLevel(level)]
        await self._record_evidence_kind(
            session_id,
            MetricKind.VOCABULARY,
            reply.vocabulary_evidence,
            set(plan.vocabulary_ids),
            repaired,
        )
        await self._record_evidence_kind(
            session_id,
            MetricKind.GRAMMAR,
            reply.grammar_evidence,
            set(plan.grammar_ids),
            repaired,
        )

    async def _record_evidence_kind(
        self,
        session_id: str,
        kind: MetricKind,
        evidence: list[SkillEvidence],
        allowed_ids: set[str],
        repaired: bool,
    ) -> None:
        for item in evidence:
            if item.item_id not in allowed_ids:
                continue
            await self.store.record_event(
                session_id=session_id,
                kind=kind,
                item_id=item.item_id,
                successful=item.successful,
                independent=item.independent and not repaired,
            )


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))
