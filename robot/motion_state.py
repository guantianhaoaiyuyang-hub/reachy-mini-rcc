from enum import Enum


class MotionState(Enum):
    IDLE = "idle"

    LISTENING = "listening"

    THINKING = "thinking"

    GREETING = "greeting"

    SPEAKING = "speaking"

    ENDING = "ending"