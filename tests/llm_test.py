import os

from openai import OpenAI


def main() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        print("错误：没有读取到 DEEPSEEK_API_KEY。")
        return

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    print("正在连接 DeepSeek……")

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 Reachy Mini 机器人助手。"
                        "请使用简洁、自然、适合机器人口头表达的中文回答。"
                        "回答尽量控制在三句话以内。"
                    ),
                },
                {
                    "role": "user",
                    "content": "你好，你是谁？",
                },
            ],
            stream=False,
        )
    except Exception as exc:
        print(f"模型调用失败：{type(exc).__name__}: {exc}")
        return

    answer = response.choices[0].message.content

    if not answer:
        print("模型没有返回有效内容。")
        return

    print("\nReachy 的回答：")
    print(answer.strip())


if __name__ == "__main__":
    main()