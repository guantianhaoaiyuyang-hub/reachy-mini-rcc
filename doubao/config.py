from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class DoubaoConfig:
    ws_url: str
    app_id: str
    access_token: str
    app_key: str
    resource_id: str
    model: str


def load_config() -> DoubaoConfig:
    required = {
        "DOUBAO_WS_URL": os.getenv("DOUBAO_WS_URL"),
        "DOUBAO_APP_ID": os.getenv("DOUBAO_APP_ID"),
        "DOUBAO_ACCESS_TOKEN": os.getenv("DOUBAO_ACCESS_TOKEN"),
        "DOUBAO_APP_KEY": os.getenv("DOUBAO_APP_KEY"),
        "DOUBAO_RESOURCE_ID": os.getenv("DOUBAO_RESOURCE_ID"),
        "DOUBAO_MODEL": os.getenv("DOUBAO_MODEL"),
    }

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("缺少环境变量：" + ", ".join(missing))

    return DoubaoConfig(
        ws_url=required["DOUBAO_WS_URL"],
        app_id=required["DOUBAO_APP_ID"],
        access_token=required["DOUBAO_ACCESS_TOKEN"],
        app_key=required["DOUBAO_APP_KEY"],
        resource_id=required["DOUBAO_RESOURCE_ID"],
        model=required["DOUBAO_MODEL"],
    )
