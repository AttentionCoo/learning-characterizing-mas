"""verify_token 鉴权单测：覆盖 HS256/HS512/篡改/过期/密钥不符/alg=none。

背景：jjwt 0.13 升级时曾按 512 位密钥自动签发 HS512，模型层只接受 HS256，
导致所有模型调用 401。此后 verify_token 兼容两种算法，本文件锁定该行为。
"""
import base64
import time

import jwt as pyjwt
import pytest
from fastapi import HTTPException

import app.runtime as runtime

TEST_SECRET = "test-secret-0123456789abcdef0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def _pin_secret(monkeypatch):
    monkeypatch.setattr(runtime, "SECRET_KEY", TEST_SECRET)


def _make_token(alg="HS256", secret=None, exp_delta=3600):
    payload = {"id": 1, "exp": int(time.time()) + exp_delta}
    return pyjwt.encode(payload, secret or TEST_SECRET, algorithm=alg)


def test_accepts_hs256_token():
    # 不抛异常即通过
    runtime.verify_token(_make_token("HS256"))


def test_accepts_hs512_token():
    # 兼容升级窗口期签发的 HS512 令牌
    runtime.verify_token(_make_token("HS512"))


def test_rejects_token_signed_with_different_secret():
    with pytest.raises(HTTPException) as exc:
        runtime.verify_token(_make_token("HS256", secret="another-secret-0123456789abcdef-extra"))
    assert exc.value.status_code == 401


def test_rejects_tampered_token():
    token = _make_token("HS256")
    last = token[-1]
    tampered = token[:-1] + ("A" if last != "A" else "B")
    with pytest.raises(HTTPException) as exc:
        runtime.verify_token(tampered)
    assert exc.value.status_code == 401


def test_rejects_expired_token():
    with pytest.raises(HTTPException) as exc:
        runtime.verify_token(_make_token("HS256", exp_delta=-60))
    assert exc.value.status_code == 401


def test_rejects_none_algorithm():
    # 手工构造 alg=none 令牌（pyjwt 2.13 已拒绝用非空密钥签发 none 令牌）
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(b'{"id":1}').rstrip(b"=")
    token = (header + b"." + payload + b".").decode("ascii")
    with pytest.raises(HTTPException) as exc:
        runtime.verify_token(token)
    assert exc.value.status_code == 401
