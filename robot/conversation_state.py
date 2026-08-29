from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from threading import RLock


class ConversationStatus(str, Enum):
    CONNECTING = "connecting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"


class StateTransitionError(RuntimeError):
    """请求了不合法的实时对话状态转换。"""


_LIVE_STATES = set(ConversationStatus) - {
    ConversationStatus.STOPPED
}
_ALLOWED: dict[ConversationStatus, set[ConversationStatus]] = {
    ConversationStatus.CONNECTING: {
        ConversationStatus.LISTENING,
    },
    ConversationStatus.LISTENING: {
        ConversationStatus.THINKING,
        ConversationStatus.SPEAKING,
    },
    ConversationStatus.THINKING: {
        ConversationStatus.LISTENING,
        ConversationStatus.SPEAKING,
        ConversationStatus.INTERRUPTED,
    },
    ConversationStatus.SPEAKING: {
        ConversationStatus.LISTENING,
        ConversationStatus.INTERRUPTED,
    },
    ConversationStatus.INTERRUPTED: {
        ConversationStatus.LISTENING,
        ConversationStatus.THINKING,
    },
    ConversationStatus.RECONNECTING: {
        ConversationStatus.CONNECTING,
        ConversationStatus.LISTENING,
    },
    ConversationStatus.STOPPED: set(),
}


class ConversationState:
    def __init__(
        self,
        initial: ConversationStatus = ConversationStatus.CONNECTING,
    ) -> None:
        self._status = initial
        self._lock = RLock()
        self._subscribers: list[
            Callable[[ConversationStatus, ConversationStatus], None]
        ] = []

    @property
    def status(self) -> ConversationStatus:
        with self._lock:
            return self._status

    def subscribe(
        self,
        callback: Callable[
            [ConversationStatus, ConversationStatus],
            None,
        ],
    ) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def transition(self, new_status: ConversationStatus) -> None:
        with self._lock:
            old_status = self._status
            if new_status is old_status:
                return
            globally_allowed = (
                old_status in _LIVE_STATES
                and new_status
                in {
                    ConversationStatus.RECONNECTING,
                    ConversationStatus.STOPPED,
                }
            )
            if (
                not globally_allowed
                and new_status not in _ALLOWED[old_status]
            ):
                raise StateTransitionError(
                    f"不允许从 {old_status.value} 转换到 "
                    f"{new_status.value}。"
                )
            self._status = new_status
            subscribers = tuple(self._subscribers)

        for callback in subscribers:
            callback(old_status, new_status)
