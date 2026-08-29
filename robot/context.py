class RobotContext:
    def __init__(self):
        self.reachy = None
        self.chat_history = []
        self.last_image = None
        self.last_audio = None
        self.memory = {}