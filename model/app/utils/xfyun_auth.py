"""讯飞开放平台通用 URL 鉴权。

图片理解（WebSocket）与文本向量化（HTTP）共用同一套签名机制：
以 APISecret 对 "host / date / request-line" 三行做 HMAC-SHA256，
签名结果拼入 authorization 参数后附加到请求 URL。
参见 https://www.xfyun.cn/doc/spark/general_url_authentication.html
"""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse


def get_xfyun_credentials() -> tuple:
    """返回 (app_id, api_key, api_secret)，缺失项为 None。"""
    return (
        os.getenv("XFYUN_APP_ID"),
        os.getenv("XFYUN_API_KEY"),
        os.getenv("XFYUN_API_SECRET"),
    )


def assemble_auth_url(url: str, api_key: str, api_secret: str, method: str = "GET") -> str:
    """为讯飞 ws(s)/http(s) 接口生成带签名参数的完整 URL。"""
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path

    # RFC1123 格式 GMT 时间，服务端允许 ±5 分钟时钟偏移
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

    signature_origin = f"host: {host}\ndate: {date}\n{method} {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")

    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

    query = urlencode({"authorization": authorization, "date": date, "host": host})
    return f"{url}?{query}"
