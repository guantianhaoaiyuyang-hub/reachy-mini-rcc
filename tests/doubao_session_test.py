import asyncio

from doubao.client import DoubaoClient


async def main() -> None:
    client = DoubaoClient()

    try:
        await client.connect()
        await client.start_session()

        print()
        print("=" * 50)
        print("豆包实时语音会话创建成功")
        print("Connect ID:", client.connect_id)
        print("Session ID:", client.session_id)
        print("=" * 50)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())