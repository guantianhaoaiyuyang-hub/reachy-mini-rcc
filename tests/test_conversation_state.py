from __future__ import annotations

import pytest

from robot.conversation_state import (
    ConversationState,
    ConversationStatus,
    StateTransitionError,
)


@pytest.mark.parametrize(
    "states",
    [
        [
            ConversationStatus.CONNECTING,
            ConversationStatus.LISTENING,
            ConversationStatus.THINKING,
            ConversationStatus.SPEAKING,
            ConversationStatus.INTERRUPTED,
            ConversationStatus.LISTENING,
        ],
        [
            ConversationStatus.CONNECTING,
            ConversationStatus.RECONNECTING,
            ConversationStatus.LISTENING,
        ],
        [
            ConversationStatus.CONNECTING,
            ConversationStatus.STOPPED,
        ],
    ],
)
def test_legal_state_sequences(states: list[ConversationStatus]) -> None:
    machine = ConversationState(initial=states[0])

    for state in states[1:]:
        machine.transition(state)

    assert machine.status is states[-1]


def test_any_live_state_can_reconnect_or_stop() -> None:
    live_states = [
        ConversationStatus.CONNECTING,
        ConversationStatus.LISTENING,
        ConversationStatus.THINKING,
        ConversationStatus.SPEAKING,
        ConversationStatus.INTERRUPTED,
        ConversationStatus.RECONNECTING,
    ]

    for state in live_states:
        reconnecting = ConversationState(initial=state)
        reconnecting.transition(ConversationStatus.RECONNECTING)
        assert reconnecting.status is ConversationStatus.RECONNECTING

        stopped = ConversationState(initial=state)
        stopped.transition(ConversationStatus.STOPPED)
        assert stopped.status is ConversationStatus.STOPPED


def test_stopped_state_cannot_resume_speaking() -> None:
    machine = ConversationState(initial=ConversationStatus.STOPPED)

    with pytest.raises(StateTransitionError):
        machine.transition(ConversationStatus.SPEAKING)


def test_subscriber_receives_completed_transition() -> None:
    events: list[tuple[ConversationStatus, ConversationStatus]] = []
    machine = ConversationState()
    machine.subscribe(lambda old, new: events.append((old, new)))

    machine.transition(ConversationStatus.LISTENING)

    assert events == [
        (
            ConversationStatus.CONNECTING,
            ConversationStatus.LISTENING,
        )
    ]


def test_repeating_same_state_is_idempotent() -> None:
    events: list[object] = []
    machine = ConversationState()
    machine.subscribe(lambda old, new: events.append((old, new)))

    machine.transition(ConversationStatus.CONNECTING)

    assert events == []
