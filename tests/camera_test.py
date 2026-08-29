import time

from reachy_mini import ReachyMini


print("开始连接……")

with ReachyMini(connection_mode="network") as mini:
    print("连接成功！")
    print("等待摄像头媒体流初始化……")

    frame = None

    for attempt in range(20):
        frame = mini.media.get_frame()

        if frame is not None:
            break

        print(f"暂未收到画面，正在重试：{attempt + 1}/20")
        time.sleep(0.5)

    if frame is None:
        print("摄像头取帧失败：媒体流没有返回图像。")
    else:
        print(f"图像类型：{type(frame)}")
        print(f"图像尺寸：{frame.shape}")
        print("摄像头测试成功！")