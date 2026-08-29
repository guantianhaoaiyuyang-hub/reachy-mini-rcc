from robot.brain import DeepSeekBrain


def main() -> None:
    print("正在初始化 DeepSeek 大脑……")

    brain = DeepSeekBrain()

    first_answer = brain.chat("你好，你是谁？")

    print("\n第一次回答：")
    print(first_answer)

    second_answer = brain.chat("我刚才问了你什么？")

    print("\n第二次回答：")
    print(second_answer)


if __name__ == "__main__":
    main()