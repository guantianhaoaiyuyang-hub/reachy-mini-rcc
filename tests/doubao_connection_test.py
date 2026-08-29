import asyncio
import os
import struct
import uuid

from dotenv import load_dotenv
import websockets


load_dotenv()

WS_URL = os.environ["DOUBAO_WS_URL"]
APP_ID = os.environ["DOUBAO_APP_ID"]
ACCESS_TOKEN = os.environ["DOUBAO_ACCESS_TOKEN"]
RESOURCE_ID = os.environ["DOUBAO_RESOURCE_ID"]
APP_KEY = os.environ["DOUBAO_APP_KEY"]


def build_start_connection_packet() -> bytes:
    """
    构造 StartConnection 事件。

    4 字节 Header:
    - version = 1
    - header size = 1（4字节）
    - message type = 1（Full-client request）
    - flags = 4（携带 event）
    - serialization = 1（JSON）
    - compression = 0
    """
    header = bytes([
        0x11,  # version=1, header size=1
        0x14,  # full-client request, event flag
        0x10,  # JSON, no compression
        0x00,
    ])

    event_id = struct.pack(">I", 1)  # StartConnection
    payload = b"{}"
    payload_size = struct.pack(">I", len(payload))

    return header + event_id + payload_size + payload


async def main() -> None:
    connect_id = str(uuid.uuid4())

    headers = {
        "X-Api-App-ID": APP_ID,
        "X-Api-Access-Key": ACCESS_TOKEN,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-App-Key": APP_KEY,
        "X-Api-Connect-Id": connect_id,
    }

    print("准备连接豆包实时语音服务")
    print("WebSocket:", WS_URL)
    print("Connect ID:", connect_id)
    print("Access Token 已加载:", bool(ACCESS_TOKEN))

    try:
        async with websockets.connect(
            WS_URL,
            additional_headers=headers,
            open_timeout=15,
            close_timeout=5,
            max_size=None,
        ) as websocket:
            print("WebSocket 握手成功")

            packet = build_start_connection_packet()
            await websocket.send(packet)
            print("StartConnection 已发送")

            response = await asyncio.wait_for(websocket.recv(), timeout=15)

            if isinstance(response, bytes):
                print("收到二进制响应")
                print("响应长度:", len(response), "字节")
                print("前16字节:", response[:16].hex(" "))
            else:
                print("收到文本响应:", response)

            print("连接测试完成")

    except Exception as exc:
        print("连接失败")
        print("错误类型:", type(exc).__name__)
        print("错误内容:", str(exc))
        raise


if __name__ == "__main__":
    asyncio.run(main())