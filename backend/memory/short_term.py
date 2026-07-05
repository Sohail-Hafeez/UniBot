"""
Short-term memory: in-process buffer of recent messages per session,
plus rolling summarisation of older turns so long conversations don't
blow past the model's context window.
"""

from typing import Awaitable, Callable

from memory.episodic import EpisodicMemory

WINDOW_SIZE = 15

Summarizer = Callable[[list[dict]], Awaitable[str]]


class ShortTermMemory:
    """Keeps the last WINDOW_SIZE messages per session in memory."""

    def __init__(self):
        self._buffer: dict[str, list[dict]] = {}

    async def get_context(
        self, session_id: str, episodic: EpisodicMemory
    ) -> tuple[str | None, list[dict]]:
        if session_id not in self._buffer:
            self._buffer[session_id] = await episodic.get_recent_messages(
                session_id, WINDOW_SIZE
            )
        summary = await episodic.get_summary(session_id)
        return summary, self._buffer[session_id]

    async def add_exchange(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        episodic: EpisodicMemory,
        summarize: Summarizer,
    ) -> None:
        await episodic.save_message(session_id, "user", user_msg)
        await episodic.save_message(session_id, "assistant", assistant_msg)
        self._buffer[session_id] = await episodic.get_recent_messages(
            session_id, WINDOW_SIZE
        )
        total = await episodic.get_message_count(session_id)
        if total > WINDOW_SIZE:
            old_msgs = await episodic.get_old_messages(session_id, exclude_last=WINDOW_SIZE)
            if old_msgs:
                summary = await summarize(old_msgs)
                await episodic.update_summary(session_id, summary)

    def clear_session(self, session_id: str) -> None:
        self._buffer.pop(session_id, None)
