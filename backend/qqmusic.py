from __future__ import annotations

from typing import Any
import base64
from http.cookies import SimpleCookie
import json
import time
import httpx


class QQMusicClient:
    def __init__(self) -> None:
        self._base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Content-Type": "application/json;charset=utf-8",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://y.qq.com/",
        }
        self._cookie = ""
        self._uin = ""

    def set_cookie(self, cookie: str | dict[str, str]) -> None:
        """设置 QQ 音乐 Cookie"""
        if isinstance(cookie, dict):
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookie.items()])
        else:
            cookie_str = cookie
        
        self._cookie = cookie_str

        jar = SimpleCookie()
        try:
            jar.load(cookie_str)
        except Exception:
            jar = SimpleCookie()

        self._uin = ""
        uin_val = ""
        for k in ("uin", "p_uin", "wxuin"):
            if k in jar and jar[k].value:
                uin_val = jar[k].value.strip()
                break

        if uin_val.startswith("o") and uin_val[1:].isdigit():
            uin_val = uin_val[1:]

        if uin_val.isdigit():
            self._uin = uin_val
            print(f"[DEBUG] Extracted UIN from cookie: {self._uin}")
        else:
            print(f"[DEBUG] No valid numeric UIN found in cookie: {cookie_str[:100]}...")
        
        # 检查 VIP 相关的 cookie 字段
        vip_indicators = ["vip", "musickey", "musicid", "qm_keyst", "qqmusic_key"]
        found_vip_cookies = []
        for part in cookie_str.split(";"):
            for indicator in vip_indicators:
                if indicator in part.lower():
                    found_vip_cookies.append(part.strip())
        
        if found_vip_cookies:
            print(f"[DEBUG] Found VIP-related cookies: {found_vip_cookies}")
        else:
            print(f"[DEBUG] No VIP-related cookies found in: {cookie_str[:200]}...")

    def get_cookie(self) -> str:
        """获取当前 Cookie"""
        return self._cookie

    def get_uin(self) -> str:
        """获取当前用户 UIN"""
        return self._uin

    async def _post(self, url: str, body: str, headers: dict[str, str] | None = None, use_cookie: bool = True) -> dict[str, Any]:
        """通用 POST 请求方法"""
        request_headers = self._base_headers.copy()
        if headers:
            request_headers.update(headers)
        
        # 添加 Cookie
        if use_cookie and self._cookie:
            request_headers["Cookie"] = self._cookie
        
        async with httpx.AsyncClient(timeout=20, headers=request_headers) as client:
            r = await client.post(url, content=body)
            r.raise_for_status()
            return r.json()

    async def _get(self, url: str, headers: dict[str, str] | None = None, use_cookie: bool = True) -> dict[str, Any]:
        """通用 GET 请求方法"""
        request_headers = self._base_headers.copy()
        if headers:
            request_headers.update(headers)
        
        # 添加 Cookie
        if use_cookie and self._cookie:
            request_headers["Cookie"] = self._cookie
        
        async with httpx.AsyncClient(timeout=20, headers=request_headers) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()

    async def get_music_url(self, songmid: str, quality: str = "320") -> dict[str, Any]:
        """
        获取音乐 URL
        
        Args:
            songmid: 歌曲 MID（字符串）
            quality: 歌曲品质（字符串），有 m4a、128、320（默认）可选
        """
        prefix = "C400" if quality.lower() == "m4a" else ("M500" if quality == "128" else "M800")
        suffix = "m4a" if quality.lower() == "m4a" else "mp3"
        
        # 使用真实的 uin，如果没有则使用 "0"
        uin = self._uin or "0"
        g_tk = self._get_gtk()
        
        body = {
            "req_1": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": {
                    "filename": [f"{prefix}{songmid}{songmid}.{suffix}"],
                    "guid": "10000",
                    "songmid": [songmid],
                    "songtype": [0],
                    "uin": uin,
                    "loginflag": 1,
                    "platform": "20"
                }
            },
            "loginUin": uin,
            "comm": {
                "uin": uin,
                "format": "json",
                "ct": 24,
                "cv": 0,
                "g_tk": g_tk
            }
        }
        
        print(f"[DEBUG] Using UIN: {uin}, g_tk: {g_tk}")
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/json;charset=UTF-8",
            "priority": "u=1, i",
            "sec-ch-ua-mobile": "?0",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "none",
            "sec-fetch-storage-access": "active",
        }
        
        return await self._post(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
            json.dumps(body),
            headers
        )

    async def get_song_list(self, category_id: str) -> dict[str, Any]:
        """
        获取歌单歌曲信息
        
        Args:
            category_id: 歌单 ID
        """
        url = f"https://i.y.qq.com/qzone-music/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg?type=1&json=1&utf8=1&onlysong=0&nosign=1&disstid={category_id}&g_tk=5381&loginUin=0&hostUin=0&format=json&inCharset=GB2312&outCharset=utf-8&notice=0&platform=yqq&needNewCode=0"
        return await self._get(url)

    async def get_song_list_name(self, category_id: str) -> dict[str, Any]:
        """
        获取歌单名称
        
        Args:
            category_id: 歌单 ID
        """
        return await self.get_song_list(category_id)

    async def search_with_keyword(
        self,
        keyword: str,
        search_type: int = 0,
        result_num: int = 50,
        page_num: int = 1
    ) -> dict[str, Any]:
        """
        用关键词搜索歌曲
        
        Args:
            keyword: 关键词（字符串）
            search_type: 搜索结果类型（默认为 0），0 为歌曲，2 为专辑，3 为歌单，4 为 MV，7 为歌词，8 为用户
            result_num: （每页）结果数量（默认为 50）
            page_num: 页面序号（不是页数，默认为 1）
        """
        body = {
            "comm": {
                "ct": "19",
                "cv": "1859",
                "uin": "0"
            },
            "req": {
                "method": "DoSearchForQQMusicDesktop",
                "module": "music.search.SearchCgiService",
                "param": {
                    "grp": 1,
                    "num_per_page": result_num,
                    "page_num": page_num,
                    "query": keyword,
                    "search_type": search_type
                }
            }
        }
        
        return await self._post(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
            json.dumps(body)
        )

    async def get_song_lyric(self, songmid: str) -> dict[str, Any]:
        """
        获取歌曲歌词
        
        Args:
            songmid: 歌曲 MID（字符串）
        """
        url = f"https://i.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?songmid={songmid}&g_tk=5381&format=json&inCharset=utf8&outCharset=utf-8&nobase64=1"
        return await self._get(url)

    async def get_album_song_list(self, albummid: str) -> dict[str, Any]:
        """
        获取专辑歌曲信息
        
        Args:
            albummid: 专辑的 MID
        """
        url = f"https://i.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg?platform=h5page&albummid={albummid}&g_tk=938407465&uin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=h5&needNewCode=1&_=1459961045571"
        return await self._get(url)

    async def get_album_name(self, albummid: str) -> dict[str, Any]:
        """
        获取专辑名称
        
        Args:
            albummid: 专辑的 MID
        """
        return await self.get_album_song_list(albummid)

    async def get_mv_info(self, vid: str) -> dict[str, Any]:
        """
        获取 MV 信息
        
        Args:
            vid: MV 的 VID
        """
        body = {
            "comm": {
                "ct": 6,
                "cv": 0,
                "g_tk": 1646675364,
                "uin": 0,
                "format": "json",
                "platform": "yqq"
            },
            "mvInfo": {
                "module": "music.video.VideoData",
                "method": "get_video_info_batch",
                "param": {
                    "vidlist": [vid],
                    "required": [
                        "vid", "type", "sid", "cover_pic", "duration", "singers",
                        "new_switch_str", "video_pay", "hint", "code", "msg", "name",
                        "desc", "playcnt", "pubdate", "isfav", "fileid", "filesize_v2",
                        "switch_pay_type", "pay", "pay_info", "uploader_headurl",
                        "uploader_nick", "uploader_uin", "uploader_encuin", "play_forbid_reason"
                    ]
                }
            },
            "mvUrl": {
                "module": "music.stream.MvUrlProxy",
                "method": "GetMvUrls",
                "param": {
                    "vids": [vid],
                    "request_type": 10003,
                    "addrtype": 3,
                    "format": 264,
                    "maxFiletype": 60
                }
            }
        }
        
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "Sec-Fetch-Site": "same-site",
        }
        headers.update(self._base_headers)
        
        return await self._post(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
            json.dumps(body),
            headers
        )

    async def get_singer_info(self, singermid: str) -> dict[str, Any]:
        """
        获取歌手信息
        
        Args:
            singermid: 歌手 MID
        """
        url = f"https://u.y.qq.com/cgi-bin/musicu.fcg?format=json&loginUin=0&hostUin=0inCharset=utf8&outCharset=utf-8&platform=yqq.json&needNewCode=0&data=%7B%22comm%22%3A%7B%22ct%22%3A24%2C%22cv%22%3A0%7D%2C%22singer%22%3A%7B%22method%22%3A%22get_singer_detail_info%22%2C%22param%22%3A%7B%22sort%22%3A5%2C%22singermid%22%3A%22{singermid}%22%2C%22sin%22%3A0%2C%22num%22%3A50%7D%2C%22module%22%3A%22music.web_singer_info_svr%22%7D%7D"
        return await self._get(url)

    # 工具函数
    def get_album_cover_image(self, albummid: str) -> str:
        """
        获取专辑封面图
        
        Args:
            albummid: 专辑的 MID
        """
        return f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"
    
    def get_song_cover_image(self, album_mid: str) -> str:
        """
        获取歌曲封面图（通过专辑 MID）
        
        Args:
            album_mid: 专辑的 MID
        """
        # QQ 音乐封面 URL 格式，使用专辑 MID
        if not album_mid:
            return ""
        return f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg"

    def parse_lyric(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        解析歌词
        
        Args:
            data: 从 QQ 音乐申请来的数据
        """
        parsed = {
            "ti": "",
            "ar": "",
            "al": "",
            "by": "",
            "offset": "",
            "count": 0,
            "haveTrans": False,
            "lyric": [],
        }
        
        lyric_lines = data.get("lyric", "").split("\n")
        trans_lines = data.get("trans", "").split("\n")
        parsed["haveTrans"] = bool(data.get("trans", "").strip())

        def substr(s: str) -> str:
            start = s.find(":") + 1
            end = s.find("]")
            return s[start:end] if start > 0 and end > start else ""

        if lyric_lines and not lyric_lines[0].startswith("[0"):
            parsed["ti"] = substr(lyric_lines[0]) if len(lyric_lines) > 0 else ""
            parsed["ar"] = substr(lyric_lines[1]) if len(lyric_lines) > 1 else ""
            parsed["al"] = substr(lyric_lines[2]) if len(lyric_lines) > 2 else ""
            parsed["by"] = substr(lyric_lines[3]) if len(lyric_lines) > 3 else ""
            parsed["offset"] = substr(lyric_lines[4]) if len(lyric_lines) > 4 else ""
            lyric_lines = lyric_lines[5:]
            if parsed["haveTrans"]:
                trans_lines = trans_lines[5:]

        parsed["count"] = len(lyric_lines)
        for i in range(parsed["count"]):
            if i >= len(lyric_lines):
                break
                
            line = lyric_lines[i]
            ele = {"time": "", "lyric": "", "trans": ""}
            
            # 提取时间
            end_bracket = line.find("]")
            if end_bracket > 0:
                ele["time"] = line[1:end_bracket]
                ele["lyric"] = line[end_bracket + 1:]
            else:
                ele["lyric"] = line
            
            # 提取翻译
            if parsed["haveTrans"] and i < len(trans_lines):
                trans_line = trans_lines[i]
                trans_end_bracket = trans_line.find("]")
                if trans_end_bracket > 0:
                    ele["trans"] = trans_line[trans_end_bracket + 1:]
                else:
                    ele["trans"] = trans_line
            
            parsed["lyric"].append(ele)

        return parsed

    # 简化的 API 方法，返回处理后的数据
    async def get_music_url_simple(self, songmid: str, quality: str = "320") -> str | None:
        """获取音乐播放 URL（简化版）"""
        try:
            data = await self.get_music_url(songmid, quality)
            print(f"[DEBUG] QQ Music get_music_url response for {songmid}: {data}")
            
            req_data = data.get("req_1", {}).get("data", {})
            sip = req_data.get("sip", [])
            midurlinfo = req_data.get("midurlinfo", [])
            
            print(f"[DEBUG] sip: {sip}")
            print(f"[DEBUG] midurlinfo: {midurlinfo}")
            
            if sip and midurlinfo:
                midurl_item = midurlinfo[0]
                
                # 优先使用完整播放链接
                if midurl_item.get("purl"):
                    url = sip[0] + midurl_item["purl"]
                    print(f"[DEBUG] Generated full URL: {url}")
                    return url
                
                # 如果没有完整链接，尝试试听链接
                if midurl_item.get("opi30surl"):
                    print(f"[DEBUG] Using 30s preview URL: {midurl_item['opi30surl']}")
                    return midurl_item["opi30surl"]
                
                # 检查其他可用的链接
                for key in ["opi48kurl", "opi96kurl", "opi128kurl", "opi192kurl"]:
                    if midurl_item.get(key):
                        print(f"[DEBUG] Using {key}: {midurl_item[key]}")
                        return midurl_item[key]
                
                result_code = midurl_item.get('result')
                print(f"[DEBUG] Result code: {result_code}, No playable URLs found")
                
                # 根据错误码提供更具体的错误信息
                if result_code == 104003:
                    raise Exception("该歌曲需要 VIP 会员或付费购买才能播放")
                elif result_code:
                    raise Exception(f"无法获取播放链接，错误码: {result_code}")
            
            print(f"[DEBUG] Failed to get URL - sip empty: {not sip}, midurlinfo empty: {not midurlinfo}")
            return None
        except Exception as e:
            print(f"[DEBUG] Exception in get_music_url_simple: {e}")
            return None

    async def get_song_list_simple(self, category_id: str) -> list[dict[str, Any]]:
        """获取歌单歌曲信息（简化版）"""
        try:
            data = await self.get_song_list(category_id)
            cdlist = data.get("cdlist", [])
            if cdlist:
                return cdlist[0].get("songlist", [])
            return []
        except Exception:
            return []

    async def get_song_list_name_simple(self, category_id: str) -> str | None:
        """获取歌单名称（简化版）"""
        try:
            data = await self.get_song_list(category_id)
            cdlist = data.get("cdlist", [])
            if cdlist:
                return cdlist[0].get("dissname")
            return None
        except Exception:
            return None

    async def search_songs_simple(self, keyword: str, limit: int = 50, page: int = 1) -> list[dict[str, Any]]:
        """搜索歌曲（简化版）"""
        try:
            data = await self.search_with_keyword(keyword, search_type=0, result_num=limit, page_num=page)
            return data.get("req", {}).get("data", {}).get("body", {}).get("song", {}).get("list", [])
        except Exception:
            return []

    async def get_song_lyric_simple(self, songmid: str, parse: bool = False) -> str | dict[str, Any] | None:
        """获取歌曲歌词（简化版）"""
        try:
            data = await self.get_song_lyric(songmid)
            if parse:
                return self.parse_lyric(data)
            else:
                lyric = data.get("lyric", "")
                trans = data.get("trans", "")
                return lyric + "\n" + trans if trans else lyric
        except Exception:
            return None

    # QQ Music Login functionality
    async def get_qr_key(self) -> dict[str, Any]:
        """获取二维码登录密钥"""
        import random
        import time
        import base64
        
        # First, initialize login session to get pt_login_sig
        try:
            print("Initializing QQ login session...")
            xlogin_url = "https://xui.ptlogin2.qq.com/cgi-bin/xlogin"
            xlogin_params = {
                "appid": "716027609",
                "daid": "383",
                "style": "33",
                "login_text": "授权并登录",
                "hide_title_bar": "1",
                "hide_border": "1",
                "target": "self",
                "s_url": "https://graph.qq.com/oauth2.0/login_jump",
                "pt_3rd_aid": "100497308",
                "pt_feedback_link": "https://support.qq.com/products/77942?customInfo=.appid100497308",
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": "https://xui.ptlogin2.qq.com/"
            }
            
            async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
                # Initialize session
                xlogin_response = await client.get(xlogin_url, params=xlogin_params)
                print(f"XLogin response status: {xlogin_response.status_code}")
                print(f"XLogin cookies: {xlogin_response.cookies}")
                
                # Get pt_login_sig from cookies
                pt_login_sig = None
                if xlogin_response.cookies:
                    pt_login_sig = xlogin_response.cookies.get("pt_login_sig")
                    print(f"Got pt_login_sig: {pt_login_sig}")
                
                if not pt_login_sig:
                    raise Exception("Failed to get pt_login_sig from xlogin")
                
                # Store session cookies and pt_login_sig
                self._session_cookies = {}
                for name, value in xlogin_response.cookies.items():
                    self._session_cookies[name] = value
                
                self._pt_login_sig = pt_login_sig
                
                # Now get QR code
                timestamp = str(int(time.time() * 1000))
                random_suffix = str(random.randint(100, 999))
                qr_token = timestamp + random_suffix
                
                qr_url = "https://ssl.ptlogin2.qq.com/ptqrshow"
                qr_params = {
                    "appid": "716027609",
                    "e": "2",
                    "l": "M",
                    "s": "3",
                    "d": "72",
                    "v": "4",
                    "t": qr_token,
                    "daid": "383",
                    "pt_3rd_aid": "100497308"
                }
                
                print(f"Requesting QR code with token: {qr_token}")
                qr_response = await client.get(qr_url, params=qr_params)
                print(f"QR response status: {qr_response.status_code}")
                print(f"QR response cookies: {qr_response.cookies}")
                
                qr_response.raise_for_status()
                
                # Get qrsig from cookies
                qrsig = None
                if qr_response.cookies:
                    qrsig = qr_response.cookies.get("qrsig")
                    print(f"Got qrsig: {qrsig}")
                    
                    # Add qrsig to session cookies
                    self._session_cookies["qrsig"] = qrsig
                
                if not qrsig:
                    raise Exception("Failed to get qrsig from QR response")
                
                # Build QR URL
                param_str = "&".join([f"{k}={v}" for k, v in qr_params.items()])
                qr_url_full = f"{qr_url}?{param_str}"

                qr_image_base64 = base64.b64encode(qr_response.content).decode("ascii")
                
                # Calculate ptqrtoken using qrsig
                ptqrtoken = self._hash33(qrsig)
                
                print(f"Generated ptqrtoken: {ptqrtoken}")
                
                return {
                    "qr_url": qr_url_full,
                    "qr_image_base64": qr_image_base64,
                    "qr_key": qrsig,
                    "ptqrtoken": ptqrtoken,
                    "pt_login_sig": pt_login_sig,
                    "debug_info": {
                        "original_token": qr_token,
                        "cookies_found": len(qr_response.cookies) if qr_response.cookies else 0,
                        "status_code": qr_response.status_code
                    }
                }
        except Exception as e:
            print(f"QR generation error: {e}")
            raise Exception(f"获取二维码失败: {str(e)}")

    def _cookie_header_from_session(self) -> str:
        parts: list[str] = []
        if hasattr(self, "_session_cookies") and isinstance(self._session_cookies, dict):
            for k, v in self._session_cookies.items():
                if v is None:
                    continue
                parts.append(f"{k}={v}")
        return "; ".join(parts)

    def _merge_response_cookies_into_session(self, cookies: httpx.Cookies) -> None:
        if not hasattr(self, "_session_cookies") or not isinstance(self._session_cookies, dict):
            self._session_cookies = {}
        for k, v in cookies.items():
            self._session_cookies[k] = v

    async def confirm_qr_login(self, auth_url: str) -> dict[str, Any]:
        """扫码成功后，访问 auth_url 让 QQ 写入最终 cookies，并保存到 client cookie 中。"""
        if not auth_url:
            raise Exception("auth_url 不能为空")

        headers = {
            "User-Agent": self._base_headers.get("User-Agent", ""),
            "Referer": "https://xui.ptlogin2.qq.com/",
        }
        cookie_header = self._cookie_header_from_session()
        if cookie_header:
            headers["Cookie"] = cookie_header

        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=False) as client:
            r = await client.get(auth_url)
            # 不强制 2xx：有些情况下会 302 / 3xx
            self._merge_response_cookies_into_session(r.cookies)

        # 将 session cookies 写入通用 cookie（供后续 musicu 请求使用）
        final_cookie = self._cookie_header_from_session()
        if final_cookie:
            self.set_cookie(final_cookie)

        # 访问 QQ 音乐页面来获取完整的音乐服务 cookie（包括 VIP 认证）
        try:
            await self._fetch_qqmusic_cookies()
            print("[DEBUG] Successfully fetched QQ Music cookies after login")
        except Exception as e:
            print(f"[DEBUG] Failed to fetch QQ Music cookies: {e}")

        return {
            "ok": True,
            "uin": self.get_uin(),
        }

    def _hash33(self, t: str) -> str:
        """计算 ptqrtoken"""
        e = 0
        for i in range(len(t)):
            e += (e << 5) + ord(t[i])
        return str(e & 2147483647)

    async def check_qr_status(self, qr_key: str, ptqrtoken: str) -> dict[str, Any]:
        """检查二维码登录状态"""
        url = "https://ssl.ptlogin2.qq.com/ptqrlogin"
        params = {
            "u1": "https://graph.qq.com/oauth2.0/login_jump",
            "ptqrtoken": ptqrtoken,
            "ptredirect": "0",
            "h": "1",
            "t": "1",
            "g": "1",
            "from_ui": "1",
            "ptlang": "2052",
            "action": f"0-0-{int(time.time() * 1000)}",
            "js_ver": "20102616",
            "js_type": "1",
            "login_sig": getattr(self, '_pt_login_sig', ''),
            "pt_uistyle": "40",
            "aid": "716027609",
            "daid": "383",
            "pt_3rd_aid": "100497308",
            "has_onekey": "1",
        }

        headers = {
            "User-Agent": self._base_headers.get("User-Agent", ""),
            "Referer": "https://xui.ptlogin2.qq.com/",
        }
        cookie_header = self._cookie_header_from_session()
        headers["Cookie"] = cookie_header or f"qrsig={qr_key}"

        try:
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                response = await client.get(url, params=params)
                response_text = response.text

                import re
                match = re.search(r"ptuiCB\((.*?)\)", response_text)
                if not match:
                    return {"status": "error", "message": "获取二维码状态失败"}

                callback_data = match.group(1)
                data = [p.strip().strip("'").strip('"') for p in callback_data.split(",")]
                if not data:
                    return {"status": "error", "message": "解析回调数据失败"}

                code_str = data[0]
                if not code_str.isdigit():
                    return {"status": "error", "message": f"未知状态码: {code_str}"}
                code = int(code_str)

                if code == 0:
                    auth_url = data[2] if len(data) > 2 else ""
                    uin_match = re.search(r"&uin=(.+?)&", auth_url)
                    sigx_match = re.search(r"&ptsigx=(.+?)&", auth_url)
                    payload: dict[str, Any] = {"status": "success", "message": "登录成功"}
                    if auth_url:
                        payload["auth_url"] = auth_url
                    if uin_match:
                        payload["uin"] = uin_match.group(1)
                    if sigx_match:
                        payload["sigx"] = sigx_match.group(1)
                    return payload
                if code == 65:
                    return {"status": "expired", "message": "二维码已失效"}
                if code == 66:
                    return {"status": "waiting", "message": "二维码未失效，请扫码"}
                if code == 67:
                    return {"status": "scanning", "message": "二维码认证中，请在手机上确认"}
                if code == 68:
                    return {"status": "expired", "message": "二维码已失效"}

                message = data[4] if len(data) > 4 and data[4] else f"状态码: {code}"
                return {"status": "waiting", "message": message}
        except Exception as e:
            return {"status": "error", "message": f"检查登录状态失败: {str(e)}"}

    async def _authorize_qq_qr(self, uin: str, sigx: str) -> dict[str, Any]:
        """使用QQ登录授权信息获取QQ音乐cookies"""
        try:
            # 这里应该实现获取QQ音乐cookies的逻辑
            # 由于涉及复杂的OAuth流程，暂时返回基本信息
            return {
                "uin": uin,
                "sigx": sigx,
                "message": "获取授权信息成功"
            }
        except Exception as e:
            raise Exception(f"授权失败: {str(e)}")

    async def refresh_login(self) -> dict[str, Any]:
        """刷新登录状态"""
        if not self._cookie:
            return {"success": False, "message": "未设置 Cookie"}
        
        try:
            # 尝试获取用户信息来验证登录状态
            user_info = await self.get_user_info()
            if user_info and user_info.get("code") == 0:
                return {"success": True, "message": "登录状态有效"}
            else:
                return {"success": False, "message": "登录状态已失效"}
        except Exception as e:
            return {"success": False, "message": f"刷新登录失败: {str(e)}"}

    async def get_user_info(self) -> dict[str, Any]:
        """获取用户信息"""
        if not self._cookie:
            raise Exception("未设置 Cookie，请先登录")
        
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        body = {
            "comm": {
                "ct": 24,
                "cv": 0
            },
            "req_0": {
                "module": "music.user.UserInfoServer",
                "method": "get_user_detail_info",
                "param": {
                    "vec_uin": [self._uin] if self._uin else []
                }
            }
        }
        
        return await self._post(url, json.dumps(body))

    async def get_user_playlists(self) -> dict[str, Any]:
        """获取用户歌单"""
        if not self._cookie or not self._uin:
            raise Exception("未设置 Cookie 或 UIN，请先登录")
        
        url = "https://c.y.qq.com/rsc/fcgi-bin/fcg_user_created_diss"
        params = {
            "hostuin": self._uin,
            "sin": "0",
            "size": "200",
            "g_tk": self._get_gtk(),
            "loginUin": self._uin,
            "hostUin": "0",
            "format": "json",
            "inCharset": "utf8",
            "outCharset": "utf-8",
            "notice": "0",
            "platform": "yqq.json",
            "needNewCode": "0"
        }
        
        param_str = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{param_str}"
        
        return await self._get(full_url)

    def _get_gtk(self) -> str:
        """计算 g_tk 参数"""
        if not self._cookie:
            return "0"

        jar = SimpleCookie()
        try:
            jar.load(self._cookie)
        except Exception:
            jar = SimpleCookie()

        p_skey = jar.get("p_skey").value.strip() if jar.get("p_skey") and jar.get("p_skey").value else ""
        if not p_skey:
            p_skey = jar.get("skey").value.strip() if jar.get("skey") and jar.get("skey").value else ""
        if not p_skey:
            return "0"
        
        # 计算 gtk
        gtk = 5381
        for char in p_skey:
            gtk += (gtk << 5) + ord(char)
        
        return str(gtk & 2147483647)

    async def _fetch_qqmusic_cookies(self) -> None:
        """访问 QQ 音乐页面获取完整的音乐服务 cookie（包括 VIP 认证）"""
        # QQ 音乐主页和关键页面，用于触发 VIP cookie 设置
        urls_to_visit = [
            "https://y.qq.com/",
            "https://y.qq.com/n/ryqq/profile",
            "https://u.y.qq.com/cgi-bin/musicu.fcg"
        ]
        
        headers = {
            "User-Agent": self._base_headers.get("User-Agent", ""),
            "Referer": "https://y.qq.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }
        
        cookie_header = self._cookie_header_from_session()
        if cookie_header:
            headers["Cookie"] = cookie_header
        
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            for url in urls_to_visit:
                try:
                    print(f"[DEBUG] Visiting {url} to fetch QQ Music cookies")
                    r = await client.get(url)
                    self._merge_response_cookies_into_session(r.cookies)
                    
                    # 检查是否获取到音乐相关的 cookie
                    new_cookies = dict(r.cookies)
                    music_cookies = [k for k in new_cookies.keys() if any(indicator in k.lower() for indicator in ["music", "vip", "qm_", "qqmusic"])]
                    if music_cookies:
                        print(f"[DEBUG] Found music cookies from {url}: {music_cookies}")
                    
                except Exception as e:
                    print(f"[DEBUG] Failed to visit {url}: {e}")
                    continue
        
        # 更新最终的 cookie
        final_cookie = self._cookie_header_from_session()
        if final_cookie:
            self.set_cookie(final_cookie)
            print(f"[DEBUG] Updated cookie after fetching QQ Music cookies")
