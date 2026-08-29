import os


ASSISTANT_MODE = os.getenv("ASSISTANT_MODE", "realtime").strip().lower()

# Reachy Mini
REACHY_CONNECTION_MODE = "network"

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-v4-flash"

# Whisper
WHISPER_MODEL = "small"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

# 语音录制
RECORD_SECONDS = 3.0

# Reachy Mini 主持人式讲话动作（仅头部与天线）
HOST_HEAD_YAW_DEGREES = 12.0
HOST_HEAD_PITCH_DEGREES = 7.0
HOST_ANTENNA_RADIANS = 0.60
HOST_MOTION_STEP_SECONDS = 0.45

# 对话设置
SYSTEM_PROMPT = (
    "你是 Reachy Mini 机器人助手。"
    "请使用自然、友好、适合口头朗读的中文回答。"
    "除非用户明确要求详细解释，否则回答控制在三句话以内。"
    "不要使用复杂的 Markdown 格式。"
)
