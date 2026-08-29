from reachy_mini import ReachyMini


class ReachyRobot:

    def __init__(self):

        self.robot = None

    def connect(self):

        print("正在连接 Reachy Mini...")

        self.robot = ReachyMini(connection_mode="network")

        self.robot.__enter__()

        print("连接成功。")

        return self.robot

    def disconnect(self):

        if self.robot:

            self.robot.__exit__(None, None, None)

            print("已断开连接。")