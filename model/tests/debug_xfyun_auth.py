"""
[DEBUG-xfyun-auth] 最小化讯飞星火 API 认证测试
用法: cd model && python tests/debug_xfyun_auth.py
"""
import os
import sys

# 确保从 model/ 目录加载 .env
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, MODEL_DIR)
os.chdir(MODEL_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(MODEL_DIR, ".env"), override=True)

import requests

BASE_URL = "https://spark-api-open.xf-yun.com/v1/chat/completions"

# 读取凭证
pw_lite = os.getenv("SPARK_API_PASSWORD_LITE") or os.getenv("SPARK_API_PASSWORD")
pw_pro = os.getenv("SPARK_API_PASSWORD_PRO") or os.getenv("SPARK_API_PASSWORD")
pw_max = os.getenv("SPARK_API_PASSWORD_MAX") or os.getenv("SPARK_API_PASSWORD")

model_lite = os.getenv("SPARK_MODEL_LITE") or "lite"
model_pro = os.getenv("SPARK_MODEL_PRO") or "generalv3"
model_max = os.getenv("SPARK_MODEL_MAX") or "generalv3"

print("=" * 60)
print("[DEBUG-xfyun-auth] Xunfei Spark Auth Diagnosis")
print("=" * 60)

# 检查凭证格式
for label, pw, model in [
    ("LITE", pw_lite, model_lite),
    ("PRO", pw_pro, model_pro),
    ("MAX", pw_max, model_max),
]:
    if not pw:
        print(f"[FAIL] {label}: credential is empty!")
        continue
    has_colon = ":" in pw
    has_whitespace = ' ' in pw or '\n' in pw or '\t' in pw
    print(f"[INFO] {label}: model={model}, pw_len={len(pw)}, has_colon={has_colon}, "
          f"prefix={pw[:6]}..., suffix=...{pw[-4:]}, "
          f"has_whitespace={has_whitespace}")

print()

# 测试每个档位
payload = {
    "messages": [{"role": "user", "content": "Hello, please reply OK"}],
    "max_tokens": 50,
    "temperature": 0.5,
    "stream": False,
}

for label, pw, model in [
    ("LITE", pw_lite, model_lite),
    ("PRO", pw_pro, model_pro),
    ("MAX", pw_max, model_max),
]:
    if not pw:
        continue
    print(f"[TEST] {label}: model={model}...")
    try:
        resp = requests.post(
            BASE_URL,
            headers={
                "Authorization": f"Bearer {pw}",
                "Content-Type": "application/json",
            },
            json={**payload, "model": model},
            timeout=30,
        )
        print(f"   HTTP {resp.status_code}")
        body = resp.json()
        if resp.status_code == 200:
            content = body.get('choices', [{}])[0].get('message', {}).get('content', 'N/A')
            print(f"   [PASS] Reply: {content[:100]}")
        else:
            error = body.get("error", {})
            print(f"   [FAIL] code={error.get('code')}, message={error.get('message')}")
    except Exception as e:
        print(f"   [ERROR] {e}")
    print()

print("=" * 60)
print("Diagnosis suggestions:")
print("1. If ALL tiers fail with 11200 -> Check Xunfei console for quota / activation")
print("2. If only LITE fails -> APIPassword might not match model='lite'")
print("3. Console: https://console.xfyun.cn/services/cbm -> Spark LLM -> check quota")
print("4. Free tier also requires clicking 'Buy Now' (0 yuan) to activate quota")
print("=" * 60)
