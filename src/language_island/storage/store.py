"""High-level operations for sessions, transcripts, and progress evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select

from language_island.progress import (
    MetricKind,
    MetricSummary,
    ProgressSnapshot,
    VocabularyItemProgress,
)
from language_island.storage.database import Database
from language_island.storage.models import (
    ConversationSession,
    ConversationTurn,
    Learner,
    LearningEvent,
    TutorRuntimeState,
    utc_now,
)


class LearningStore:
    """Persist learning evidence without coupling it to the voice or LLM layers."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_learner(
        self, display_name: str = "Learner", learner_id: str | None = None
    ) -> Learner:
        learner = Learner(display_name=display_name)
        if learner_id is not None:
            learner.id = learner_id
        async with self.database.session() as session, session.begin():
            session.add(learner)
        return learner

    async def get_learner(self, learner_id: str) -> Learner | None:
        async with self.database.session() as session:
            return await session.get(Learner, learner_id)

    async def get_session(self, session_id: str) -> ConversationSession | None:
        async with self.database.session() as session:
            return await session.get(ConversationSession, session_id)

    async def start_session(
        self,
        *,
        learner_id: str,
        island_id: str,
        level: str,
        scenario_id: str,
        personality_id: str,
    ) -> ConversationSession:
        conversation = ConversationSession(
            learner_id=learner_id,
            island_id=island_id,
            level=level,
            scenario_id=scenario_id,
            personality_id=personality_id,
        )
        async with self.database.session() as session, session.begin():
            if await session.get(Learner, learner_id) is None:
                raise ValueError(f"Unknown learner: {learner_id}")
            session.add(conversation)
        return conversation

    async def finish_session(self, session_id: str) -> ConversationSession:
        async with self.database.session() as session, session.begin():
            conversation = await session.get(ConversationSession, session_id)
            if conversation is None:
                raise ValueError(f"Unknown session: {session_id}")
            conversation.status = "completed"
            conversation.ended_at = utc_now()
        return conversation

    async def append_turn(
        self,
        *,
        session_id: str,
        speaker: str,
        german_text: str,
        english_translation: str | None = None,
    ) -> ConversationTurn:
        if speaker not in {"learner", "tutor", "correction"}:
            raise ValueError(f"Unsupported speaker: {speaker}")
        async with self.database.session() as session, session.begin():
            if await session.get(ConversationSession, session_id) is None:
                raise ValueError(f"Unknown session: {session_id}")
            latest = await session.scalar(
                select(func.max(ConversationTurn.sequence)).where(
                    ConversationTurn.session_id == session_id
                )
            )
            turn = ConversationTurn(
                session_id=session_id,
                sequence=(latest or 0) + 1,
                speaker=speaker,
                german_text=german_text,
                english_translation=english_translation,
            )
            session.add(turn)
        return turn

    async def get_transcript(self, session_id: str) -> list[ConversationTurn]:
        async with self.database.session() as session:
            result = await session.scalars(
                select(ConversationTurn)
                .where(ConversationTurn.session_id == session_id)
                .order_by(ConversationTurn.sequence)
            )
            return list(result)

    async def get_tutor_state(self, session_id: str) -> dict[str, Any]:
        async with self.database.session() as session:
            state = await session.get(TutorRuntimeState, session_id)
            return dict(state.state) if state is not None else {}

    async def set_tutor_state(self, session_id: str, state: dict[str, Any]) -> None:
        async with self.database.session() as session, session.begin():
            if await session.get(ConversationSession, session_id) is None:
                raise ValueError(f"Unknown session: {session_id}")
            record = await session.get(TutorRuntimeState, session_id)
            if record is None:
                session.add(TutorRuntimeState(session_id=session_id, state=state))
            else:
                record.state = state

    async def record_event(
        self,
        *,
        session_id: str,
        kind: MetricKind,
        item_id: str,
        successful: bool,
        independent: bool = True,
        delayed: bool = False,
        score: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> LearningEvent:
        numeric_score = float(successful) if score is None else score
        if not 0 <= numeric_score <= 1:
            raise ValueError("score must be between 0 and 1")
        event = LearningEvent(
            session_id=session_id,
            kind=kind.value,
            item_id=item_id,
            successful=successful,
            independent=independent,
            delayed=delayed,
            score=numeric_score,
            details=details or {},
        )
        async with self.database.session() as session, session.begin():
            if await session.get(ConversationSession, session_id) is None:
                raise ValueError(f"Unknown session: {session_id}")
            session.add(event)
        return event

    async def progress_snapshot(
        self,
        *,
        learner_id: str,
        island_id: str,
        level: str,
        objective_ids: set[str],
    ) -> ProgressSnapshot:
        async with self.database.session() as session:
            conversations = list(
                await session.scalars(
                    select(ConversationSession).where(
                        ConversationSession.learner_id == learner_id,
                        ConversationSession.island_id == island_id,
                        ConversationSession.level == level,
                    )
                )
            )
            session_ids = [conversation.id for conversation in conversations]
            events: list[LearningEvent] = []
            if session_ids:
                events = list(
                    await session.scalars(
                        select(LearningEvent).where(LearningEvent.session_id.in_(session_ids))
                    )
                )

        successful_objectives = {
            event.item_id
            for event in events
            if event.kind == MetricKind.OBJECTIVE and event.successful
        }
        vocabulary_results: dict[str, list[bool]] = defaultdict(list)
        for event in events:
            if event.kind == MetricKind.VOCABULARY and event.delayed:
                vocabulary_results[event.item_id].append(event.successful)

        vocabulary = []
        for item_id, results in sorted(vocabulary_results.items()):
            successes = sum(results)
            rate = successes / len(results)
            vocabulary.append(
                VocabularyItemProgress(
                    item_id=item_id,
                    delayed_checks=len(results),
                    delayed_successes=successes,
                    recall_rate=rate,
                    mastered=len(results) >= 3 and rate >= 0.8,
                )
            )

        return ProgressSnapshot(
            learner_id=learner_id,
            island_id=island_id,
            level=level,
            completed_sessions=sum(item.status == "completed" for item in conversations),
            distinct_scenarios=len(
                {item.scenario_id for item in conversations if item.status == "completed"}
            ),
            grammar=_event_summary(events, MetricKind.GRAMMAR, independent_only=True),
            tasks=_event_summary(events, MetricKind.TASK),
            delayed_vocabulary=_event_summary(events, MetricKind.VOCABULARY, delayed_only=True),
            listening=_event_summary(events, MetricKind.LISTENING),
            transfer=_event_summary(events, MetricKind.TRANSFER),
            objective_coverage=(
                len(successful_objectives & objective_ids) / len(objective_ids)
                if objective_ids
                else 0.0
            ),
            vocabulary=vocabulary,
        )


def _event_summary(
    events: list[LearningEvent],
    kind: MetricKind,
    *,
    independent_only: bool = False,
    delayed_only: bool = False,
) -> MetricSummary:
    results = [
        event.successful
        for event in events
        if event.kind == kind
        and (event.independent or not independent_only)
        and (event.delayed or not delayed_only)
    ]
    return MetricSummary.from_results(results)
