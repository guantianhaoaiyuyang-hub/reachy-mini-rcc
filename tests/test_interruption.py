from __future__ import annotations

from queue import Queue

from robot.interruption import InterruptionController


def test_invalidation_makes_late_audio_stale_and_clears_queue() -> None:
    controller = InterruptionController()
    generation = controller.begin_response("resp-1")
    audio_queue: Queue[tuple[int, str, bytes]] = Queue()
    audio_queue.put((generation, "resp-1", b"old-1"))
    audio_queue.put((generation, "resp-1", b"old-2"))

    new_generation, removed = controller.interrupt(audio_queue)

    assert new_generation > generation
    assert removed == 2
    assert audio_queue.empty()
    assert not controller.is_current(generation, "resp-1")


def test_new_response_becomes_only_current_generation() -> None:
    controller = InterruptionController()
    first = controller.begin_response("resp-1")
    second = controller.begin_response("resp-2")

    assert not controller.is_current(first, "resp-1")
    assert controller.is_current(second, "resp-2")
    assert not controller.is_current(second, "resp-1")


def test_invalidate_current_is_idempotent_for_stale_audio() -> None:
    controller = InterruptionController()
    generation = controller.begin_response("resp-1")

    invalidated = controller.invalidate_current()

    assert invalidated > generation
    assert not controller.is_current(generation, "resp-1")
    assert not controller.is_current(invalidated, "resp-1")


def test_clear_queue_handles_empty_queue() -> None:
    controller = InterruptionController()
    audio_queue: Queue[object] = Queue()

    assert controller.clear_queue(audio_queue) == 0
