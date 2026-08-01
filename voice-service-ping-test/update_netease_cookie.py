#!/usr/bin/env python3
"""
更换网易云 Cookie。

用法：
  python3 update_netease_cookie.py

脚本会提示输入 MUSIC_U，然后发送到后端 /admin/cookie 接口。
"""

import json
import urllib.request
import urllib.error

# --- 在这里填入你的信息 ---
BACKEND_URL = "http://127.0.0.1:8009"
# 如果 tsbot.env 中配置了 TSBOT_ADMIN_TOKEN，在下面填入（留空则不传）
ADMIN_TOKEN = ""
# --------------------------


def main():
    music_u = input("请输入 MUSIC_U 值（直接回车可取消）: ").strip()
    if not music_u:
        print("已取消。")
        return

    # 组装最小 Cookie（只需 MUSIC_U）
    cookie = f"MUSIC_U={music_u}"

    payload = json.dumps({"cookie": cookie}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if ADMIN_TOKEN:
        headers["x-admin-token"] = ADMIN_TOKEN

    req = urllib.request.Request(
        f"{BACKEND_URL}/admin/cookie",
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            print(f"成功：{result}")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            detail = json.loads(body).get("detail", body.decode())
        except Exception:
            detail = body.decode()
        print(f"请求失败 [{e.code}]：{detail}")
    except Exception as e:
        print(f"网络错误：{e}")


if __name__ == "__main__":
    main()
