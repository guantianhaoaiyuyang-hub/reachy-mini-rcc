from openai import OpenAI

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    LLM_MODEL,
    SYSTEM_PROMPT,
)


class DeepSeekBrain:
    """负责调用 DeepSeek，并维护短期对话历史。"""

    def __init__(self) -> None:
        if not DEEPSEEK_API_KEY:
            raise RuntimeError(
                "没有读取到 DEEPSEEK_API_KEY，"
                "请检查 Windows 环境变量。"
            )

        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
        )

        self.messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

    def chat(self, user_text: str) -> str:
        """将用户输入发送给 DeepSeek，并返回回答。"""

        cleaned_text = user_text.strip()

        if not cleaned_text:
            raise ValueError("用户输入不能为空。")

        self.messages.append(
            {
                "role": "user",
                "content": cleaned_text,
            }
        )

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=self.messages,
                stream=False,
            )
        except Exception:
            # 请求失败时撤销本次用户消息，避免污染上下文。
            self.messages.pop()
            raise

        answer = response.choices[0].message.content

        if not answer:
            self.messages.pop()
            raise RuntimeError("DeepSeek 没有返回有效内容。")

        answer = answer.strip()

        self.messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        return answer

    def clear_history(self) -> None:
        """清空对话历史，但保留系统提示词。"""

        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]