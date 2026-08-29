from __future__ import annotations

import time

from reachy_mini import ReachyMini

from robot.motion_controller import ReachyMotionController


def wait_for_user(message: str) -> None:
    input(f"\n{message}\n确认机器人周围没有障碍后，按 Enter 继续……")


def main() -> None:
    print("=" * 58)
    print("Reachy Mini 动作安全测试")
    print("=" * 58)
    print()
    print("本测试只使用小幅头部和天线动作。")
    print("请确保机器人四周至少留出30厘米空间。")
    print("测试期间不要用手强行阻挡头部或天线。")

    with ReachyMini(media_backend="no_media") as mini:
        print("\n机器人连接成功。")

        controller = ReachyMotionController(mini)

        wait_for_user("测试1：回到中立位")
        controller.neutral()
        print("中立位完成。")

        wait_for_user("测试2：打招呼动作")
        controller.greet()
        print("打招呼动作完成。")

        wait_for_user("测试3：轻微点头")
        controller.nod(count=2)
        print("点头动作完成。")

        wait_for_user("测试4：好奇歪头")
        controller.curious()
        print("好奇动作完成。")

        wait_for_user("测试5：小幅左右看")
        controller.look_left_right()
        print("左右看动作完成。")

        wait_for_user("测试6：轻微说话天线脉冲")
        for _ in range(3):
            controller.speaking_pulse()
            time.sleep(0.12)
        controller.neutral()
        print("说话脉冲完成。")

        print("\n全部动作测试完成，机器人已回到中立位。")


if __name__ == "__main__":
    main()
