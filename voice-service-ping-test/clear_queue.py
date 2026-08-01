#!/usr/bin/env python3
"""
清空当前播放队列。

用法：
  python3 clear_queue.py
"""

import json
import urllib.request
import urllib.error

BACKEND_URL = "http://127.0.0.1:8009"
ADMIN_TOKEN = ""  # 如需认证则填入


def main():
    headers = {}
    if ADMIN_TOKEN:
        headers["x-admin-token"] = ADMIN_TOKEN

    req = urllib.request.Request(
        f"{BACKEND_URL}/queue",
        headers=headers,
        method="DELETE",
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
