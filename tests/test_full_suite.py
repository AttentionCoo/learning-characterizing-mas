"""
多智能体个性化学习系统 — 全链路自动化测试套件
运行前提: 后端(8080) + 模型层(8000) + MySQL + Redis 均已启动
用法:  python -m pytest tests/test_full_suite.py -v --tb=short
断点续跑: 中断后再次运行同一命令, 已通过的用例自动跳过
清除断点: 删除 tests/test_checkpoint.json 或设置环境变量 FORCE_RERUN=1
"""
import os
import re
import sys
import json
import time
import uuid
import threading
import functools
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pytest
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = os.getenv("API_BASE", "http://127.0.0.1:8080")
MODEL_BASE = os.getenv("MODEL_BASE", "http://127.0.0.1:8000")
TIMEOUT = 120

session = requests.Session()
session.verify = False

results_log = []

CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_checkpoint.json")
_checkpoint_data = {}


def _load_checkpoint():
    global _checkpoint_data
    if os.getenv("FORCE_RERUN", "").strip() in ("1", "true", "True"):
        _checkpoint_data = {}
        return
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                _checkpoint_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            _checkpoint_data = {}


def _save_checkpoint():
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(_checkpoint_data, f, ensure_ascii=False, indent=2)


_load_checkpoint()


def _sse_post(url, headers=None, json=None, max_retries=3):
    retries = 0
    while retries < max_retries:
        try:
            start = time.time()
            r = session.post(url, headers=headers, json=json, stream=True, timeout=TIMEOUT)
            events = []
            full = ""
            first_chunk_time = None
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    data = line[5:].strip()
                    if data and data != "[DONE]":
                        if first_chunk_time is None:
                            first_chunk_time = time.time()
                        events.append(data)
                        full += data
            elapsed = (time.time() - start) * 1000
            first_token_ms = (first_chunk_time - start) * 1000 if first_chunk_time else -1
            return events, full, elapsed, first_token_ms
        except (requests.exceptions.ChunkedEncodingError,
                urllib3.exceptions.ProtocolError,
                requests.exceptions.ConnectionError,
                ConnectionResetError) as e:
            retries += 1
            if retries >= max_retries:
                raise
            time.sleep(2 * retries)
    return [], "", 0, -1


def _log(module, case_id, status, elapsed_ms, detail=""):
    entry = {
        "module": module,
        "case_id": case_id,
        "status": status,
        "elapsed_ms": round(elapsed_ms, 1),
        "detail": detail,
        "timestamp": datetime.now().isoformat(),
    }
    results_log.append(entry)
    _checkpoint_data[f"{module}::{case_id}"] = entry
    _save_checkpoint()


def resume(test_func):
    @functools.wraps(test_func)
    def wrapper(*args, **kwargs):
        if args and hasattr(args[0], '__class__') and hasattr(args[0].__class__, 'module'):
            case_key = f"{args[0].__class__.__name__}.{test_func.__name__}"
            module = getattr(args[0].__class__, 'module', args[0].__class__.__name__)
        else:
            case_key = test_func.__name__
            module = test_func.__name__
        if case_key in _checkpoint_data and _checkpoint_data[case_key].get("status") in ("PASS", "PARTIAL"):
            results_log.append(_checkpoint_data[case_key])
            pytest.skip(f"断点续跑跳过(已通过): {case_key}")
        try:
            result = test_func(*args, **kwargs)
        except Exception as e:
            if not results_log or results_log[-1].get("module") != module:
                _log(module, case_key, "FAIL", 0, str(e)[:200])
            elif results_log:
                _checkpoint_data[case_key] = results_log[-1]
                _save_checkpoint()
            raise
        if results_log:
            _checkpoint_data[case_key] = results_log[-1]
            _save_checkpoint()
        return result
    return wrapper


class TestAuth:
    module = "AUTH"

    @resume
    def test_register_new_user(self):
        name = f"test_{uuid.uuid4().hex[:8]}"
        r = session.post(f"{BASE}/api/user/register",
                          json={"name": name, "password": "Test1234!"},
                          timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 1
        _log(self.module, "AUTH-01", "PASS", r.elapsed.total_seconds() * 1000,
             f"user={name}")

    @resume
    def test_register_duplicate(self):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/register",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        assert r.json()["code"] == 0
        _log(self.module, "AUTH-02", "PASS", r.elapsed.total_seconds() * 1000)

    @resume
    def test_login_success(self):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        body = r.json()
        assert body["code"] == 1
        assert "token" in body["data"]
        _log(self.module, "AUTH-03", "PASS", r.elapsed.total_seconds() * 1000)

    @resume
    def test_login_wrong_password(self):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "WrongPass"}, timeout=TIMEOUT)
        assert r.json()["code"] == 0
        _log(self.module, "AUTH-04", "PASS", r.elapsed.total_seconds() * 1000)

    @resume
    def test_access_without_token(self):
        r = session.get(f"{BASE}/api/profile", timeout=TIMEOUT)
        body = r.json()
        no_auth = body.get("code") == 0 or r.status_code in (401, 403)
        if no_auth:
            _log(self.module, "AUTH-05", "PASS", r.elapsed.total_seconds() * 1000)
        else:
            _log(self.module, "AUTH-05", "FAIL", r.elapsed.total_seconds() * 1000,
                 f"未拦截无token访问, code={body.get('code')}, status={r.status_code}")


class TestProfile:
    module = "PROFILE"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    @resume
    def test_profile_conversation_first(self):
        token = self._get_token()
        headers = {"token": token}
        events, full, elapsed = _sse_post(
            f"{BASE}/api/profile/conversation",
            headers=headers,
            json={"message": "我是大三医学生，正在学神经病学，对脑血管疾病比较感兴趣", "talkId": ""})
        assert len(events) > 0
        _log(self.module, "PROFILE-01", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_profile_query(self):
        token = self._get_token()
        headers = {"token": token}
        _sse_post(f"{BASE}/api/profile/conversation", headers=headers,
                  json={"message": "我是大四医学生，正在准备神经病学期末考试", "talkId": ""})
        r = session.get(f"{BASE}/api/profile", headers=headers, timeout=TIMEOUT)
        body = r.json()
        assert body["code"] == 1
        data = body["data"]
        assert data is not None
        dims = data.get("dimensions", {})
        dim_count = len(dims)
        _log(self.module, "PROFILE-03", "PASS", r.elapsed.total_seconds() * 1000,
             f"dimensions={dim_count}")

    @resume
    def test_profile_dimension_count(self):
        token = self._get_token()
        headers = {"token": token}
        _sse_post(f"{BASE}/api/profile/conversation", headers=headers,
                  json={"message": "我是研一医学生，想做脑血管方向研究", "talkId": ""})
        r = session.get(f"{BASE}/api/profile", headers=headers, timeout=TIMEOUT)
        data = r.json().get("data")
        if data:
            dims = data.get("dimensions", {})
            assert len(dims) >= 6
            _log(self.module, "PROFILE-04", "PASS", r.elapsed.total_seconds() * 1000,
                 f"dim_count={len(dims)}")
        else:
            _log(self.module, "PROFILE-04", "FAIL", r.elapsed.total_seconds() * 1000,
                 "no profile data")


class TestResource:
    module = "RESOURCE"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    def _generate_resource(self, resource_type, token):
        headers = {"token": token}
        events, full, elapsed = _sse_post(
            f"{BASE}/api/resources/generate",
            headers=headers,
            json={
                "message": f"请生成脑卒中诊断流程的{resource_type}学习资源",
                "courseName": "神经病学",
                "resourceTypes": [resource_type],
                "difficulty": "intermediate"
            })
        return events, full, elapsed

    @resume
    def test_generate_document(self):
        token = self._get_token()
        events, full, elapsed = self._generate_resource("document", token)
        assert len(events) > 0
        _log(self.module, "RESOURCE-01", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_generate_mindmap(self):
        token = self._get_token()
        events, full, elapsed = self._generate_resource("mindmap", token)
        assert len(events) > 0
        _log(self.module, "RESOURCE-02", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_generate_quiz(self):
        token = self._get_token()
        events, full, elapsed = self._generate_resource("quiz", token)
        assert len(events) > 0
        _log(self.module, "RESOURCE-03", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_generate_reading(self):
        token = self._get_token()
        events, full, elapsed = self._generate_resource("reading", token)
        assert len(events) > 0
        _log(self.module, "RESOURCE-04", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_generate_video_script(self):
        token = self._get_token()
        events, full, elapsed = self._generate_resource("video_script", token)
        assert len(events) > 0
        _log(self.module, "RESOURCE-05", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_generate_code_practice(self):
        token = self._get_token()
        events, full, elapsed = self._generate_resource("code_practice", token)
        assert len(events) > 0
        _log(self.module, "RESOURCE-06", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_generate_code_example(self):
        token = self._get_token()
        events, full, elapsed = self._generate_resource("code_example", token)
        assert len(events) > 0
        _log(self.module, "RESOURCE-07", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_resource_list(self):
        token = self._get_token()
        headers = {"token": token}
        self._generate_resource("document", token)
        r = session.get(f"{BASE}/api/resources?page=1&size=10",
                         headers=headers, timeout=TIMEOUT)
        assert r.json()["code"] == 1
        _log(self.module, "RESOURCE-08", "PASS", r.elapsed.total_seconds() * 1000)


class TestTutor:
    module = "TUTOR"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    @resume
    def test_tutor_text_chat(self):
        token = self._get_token()
        headers = {"token": token}
        events, full, elapsed = _sse_post(
            f"{BASE}/api/tutor/chat",
            headers=headers,
            json={"message": "什么是缺血性脑卒中的静脉溶栓适应症？", "mode": "explain"})
        assert len(events) > 0
        _log(self.module, "TUTOR-01", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_tutor_with_code(self):
        token = self._get_token()
        headers = {"token": token}
        events, full, elapsed = _sse_post(
            f"{BASE}/api/tutor/chat",
            headers=headers,
            json={
                "message": "请帮我分析这段代码",
                "codeSnippet": "import pandas as pd\ndf = pd.read_csv('stroke_data.csv')\nprint(df.describe())"
            })
        assert len(events) > 0
        _log(self.module, "TUTOR-02", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")


class TestLearningPath:
    module = "PATH"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    @resume
    def test_path_generate(self):
        token = self._get_token()
        headers = {"token": token}
        events, full, elapsed = _sse_post(
            f"{BASE}/api/learning-path/generate",
            headers=headers,
            json={
                "courseName": "神经病学",
                "goalDescription": "掌握脑卒中诊疗全流程",
                "deadline": "2026-09-01",
                "weeklyHours": 10
            })
        assert len(events) > 0
        _log(self.module, "PATH-01", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_path_list(self):
        token = self._get_token()
        headers = {"token": token}
        r = session.get(f"{BASE}/api/learning-path?page=1&size=10",
                         headers=headers, timeout=TIMEOUT)
        assert r.json()["code"] == 1
        _log(self.module, "PATH-02", "PASS", r.elapsed.total_seconds() * 1000)


class TestAssessment:
    module = "ASSESSMENT"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    @resume
    def test_assessment_generate(self):
        token = self._get_token()
        headers = {"token": token}
        events, full, elapsed = _sse_post(
            f"{BASE}/api/evaluation/generate",
            headers=headers,
            json={
                "assessmentType": "comprehensive",
                "courseName": "神经病学"
            })
        assert len(events) > 0
        _log(self.module, "ASSESS-01", "PASS", elapsed,
             f"events={len(events)}, chars={len(full)}")

    @resume
    def test_behavior_submit(self):
        token = self._get_token()
        headers = {"token": token}
        r = session.post(f"{BASE}/api/evaluation/behavior",
                          headers=headers,
                          json={
                              "behaviorType": "resource_view",
                              "duration": 300,
                              "detail": {"resourceTitle": "脑卒中诊断流程"}
                          },
                          timeout=TIMEOUT)
        assert r.json()["code"] == 1
        _log(self.module, "ASSESS-02", "PASS", r.elapsed.total_seconds() * 1000)


class TestCode:
    module = "CODE"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    @resume
    def test_code_execute_normal(self):
        token = self._get_token()
        headers = {"token": token}
        r = session.post(f"{BASE}/api/code/execute",
                          headers=headers,
                          json={"code": "print('hello world')", "language": "python", "timeout": 30},
                          timeout=TIMEOUT)
        body = r.json()
        assert body["code"] == 1
        _log(self.module, "CODE-01", "PASS", r.elapsed.total_seconds() * 1000,
             f"output={body.get('data', {}).get('output', '')[:50]}")

    @resume
    def test_code_execute_error(self):
        token = self._get_token()
        headers = {"token": token}
        r = session.post(f"{BASE}/api/code/execute",
                          headers=headers,
                          json={"code": "1/0", "language": "python", "timeout": 30},
                          timeout=TIMEOUT)
        body = r.json()
        assert body["code"] == 1
        _log(self.module, "CODE-02", "PASS", r.elapsed.total_seconds() * 1000)

    @resume
    def test_code_assist(self):
        token = self._get_token()
        headers = {"token": token}
        r = session.post(f"{BASE}/api/code/assist",
                          headers=headers,
                          json={"prompt": "生成一个读取CSV文件并计算均值的Python脚本", "language": "python"},
                          timeout=TIMEOUT)
        body = r.json()
        assert body["code"] == 1
        _log(self.module, "CODE-03", "PASS", r.elapsed.total_seconds() * 1000)


class TestChat:
    module = "CHAT"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    @resume
    def test_sse_streaming_chat(self):
        token = self._get_token()
        headers = {"token": token}
        start = time.time()
        r = session.post(f"{BASE}/api/user/ques/streamingQues",
                          headers=headers,
                          json={"question": "什么是脑卒中？", "talkId": ""},
                          stream=True, timeout=TIMEOUT)
        events = []
        first_chunk_time = None
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                    events.append(data)
        total_elapsed = (time.time() - start) * 1000
        first_token_ms = (first_chunk_time - start) * 1000 if first_chunk_time else -1
        assert len(events) > 0
        _log(self.module, "CHAT-01", "PASS", total_elapsed,
             f"events={len(events)}, first_token={first_token_ms:.0f}ms")

    @resume
    def test_talk_list(self):
        token = self._get_token()
        headers = {"token": token}
        r = session.get(f"{BASE}/api/user/title", headers=headers, timeout=TIMEOUT)
        assert r.status_code == 200
        _log(self.module, "CHAT-02", "PASS", r.elapsed.total_seconds() * 1000)


class TestConcurrency:
    module = "CONCURRENCY"

    @classmethod
    def _get_tokens(cls, count):
        tokens = []
        for _ in range(count):
            name = f"ctest_{uuid.uuid4().hex[:8]}"
            session.post(f"{BASE}/api/user/register",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
            r = session.post(f"{BASE}/api/user/login",
                              json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
            tokens.append(r.json()["data"]["token"])
        return tokens

    @resume
    def test_concurrent_sse_10(self):
        tokens = self._get_tokens(10)
        results = []

        def worker(token):
            headers = {"token": token}
            start = time.time()
            try:
                r = session.post(f"{BASE}/api/user/ques/streamingQues",
                                  headers=headers,
                                  json={"question": "简述脑卒中的分类", "talkId": ""},
                                  stream=True, timeout=TIMEOUT)
                events = 0
                for line in r.iter_lines(decode_unicode=True):
                    if line and line.startswith("data:"):
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            events += 1
                elapsed = (time.time() - start) * 1000
                return {"ok": True, "events": events, "elapsed": elapsed}
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                return {"ok": False, "error": str(e), "elapsed": elapsed}

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(worker, t) for t in tokens]
            for f in as_completed(futures):
                results.append(f.result())

        success = sum(1 for r in results if r["ok"])
        fail = len(results) - success
        latencies = [r["elapsed"] for r in results if r["ok"]]
        avg_ms = statistics.mean(latencies) if latencies else 0
        p50 = statistics.median(latencies) if latencies else 0
        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else (latencies[0] if latencies else 0)

        _log(self.module, "CONC-10", "PASS" if success == 10 else "PARTIAL",
             avg_ms,
             f"success={success}/10, fail={fail}, avg={avg_ms:.0f}ms, "
             f"p50={p50:.0f}ms, p95={p95:.0f}ms")

    @resume
    def test_concurrent_sse_50(self):
        tokens = self._get_tokens(50)
        results = []

        def worker(token):
            headers = {"token": token}
            start = time.time()
            try:
                r = session.post(f"{BASE}/api/user/ques/streamingQues",
                                  headers=headers,
                                  json={"question": "脑卒中的危险因素有哪些？", "talkId": ""},
                                  stream=True, timeout=TIMEOUT)
                events = 0
                for line in r.iter_lines(decode_unicode=True):
                    if line and line.startswith("data:"):
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            events += 1
                elapsed = (time.time() - start) * 1000
                return {"ok": True, "events": events, "elapsed": elapsed}
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                return {"ok": False, "error": str(e), "elapsed": elapsed}

        with ThreadPoolExecutor(max_workers=50) as pool:
            futures = [pool.submit(worker, t) for t in tokens]
            for f in as_completed(futures):
                results.append(f.result())

        success = sum(1 for r in results if r["ok"])
        fail = len(results) - success
        latencies = [r["elapsed"] for r in results if r["ok"]]
        avg_ms = statistics.mean(latencies) if latencies else 0
        p50 = statistics.median(latencies) if latencies else 0
        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else (latencies[0] if latencies else 0)

        _log(self.module, "CONC-50", "PASS" if success >= 45 else "PARTIAL",
             avg_ms,
             f"success={success}/50, fail={fail}, avg={avg_ms:.0f}ms, "
             f"p50={p50:.0f}ms, p95={p95:.0f}ms")

    @resume
    def test_concurrent_sse_100(self):
        tokens = self._get_tokens(100)
        results = []

        def worker(token):
            headers = {"token": token}
            start = time.time()
            try:
                r = session.post(f"{BASE}/api/user/ques/streamingQues",
                                  headers=headers,
                                  json={"question": "什么是NIHSS评分？", "talkId": ""},
                                  stream=True, timeout=TIMEOUT)
                events = 0
                for line in r.iter_lines(decode_unicode=True):
                    if line and line.startswith("data:"):
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            events += 1
                elapsed = (time.time() - start) * 1000
                return {"ok": True, "events": events, "elapsed": elapsed}
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                return {"ok": False, "error": str(e), "elapsed": elapsed}

        with ThreadPoolExecutor(max_workers=100) as pool:
            futures = [pool.submit(worker, t) for t in tokens]
            for f in as_completed(futures):
                results.append(f.result())

        success = sum(1 for r in results if r["ok"])
        fail = len(results) - success
        latencies = [r["elapsed"] for r in results if r["ok"]]
        avg_ms = statistics.mean(latencies) if latencies else 0
        p50 = statistics.median(latencies) if latencies else 0
        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else (latencies[0] if latencies else 0)

        _log(self.module, "CONC-100", "PASS" if success >= 90 else "PARTIAL",
             avg_ms,
             f"success={success}/100, fail={fail}, avg={avg_ms:.0f}ms, "
             f"p50={p50:.0f}ms, p95={p95:.0f}ms")


class TestNonAI:
    module = "NON_AI"

    @classmethod
    def _get_token(cls):
        name = f"test_{uuid.uuid4().hex[:8]}"
        session.post(f"{BASE}/api/user/register",
                      json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        r = session.post(f"{BASE}/api/user/login",
                          json={"name": name, "password": "Test1234!"}, timeout=TIMEOUT)
        return r.json()["data"]["token"]

    @resume
    def test_profile_query_latency(self):
        token = self._get_token()
        headers = {"token": token}
        latencies = []
        for _ in range(20):
            start = time.time()
            session.get(f"{BASE}/api/profile", headers=headers, timeout=TIMEOUT)
            latencies.append((time.time() - start) * 1000)
        avg = statistics.mean(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        _log(self.module, "NON_AI-01", "PASS" if p95 < 500 else "FAIL", avg,
             f"avg={avg:.0f}ms, p95={p95:.0f}ms (20次)")

    @resume
    def test_resource_list_latency(self):
        token = self._get_token()
        headers = {"token": token}
        latencies = []
        for _ in range(20):
            start = time.time()
            session.get(f"{BASE}/api/resources?page=1&size=10",
                         headers=headers, timeout=TIMEOUT)
            latencies.append((time.time() - start) * 1000)
        avg = statistics.mean(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        _log(self.module, "NON_AI-02", "PASS" if p95 < 500 else "FAIL", avg,
             f"avg={avg:.0f}ms, p95={p95:.0f}ms (20次)")

    @resume
    def test_path_list_latency(self):
        token = self._get_token()
        headers = {"token": token}
        latencies = []
        for _ in range(20):
            start = time.time()
            session.get(f"{BASE}/api/learning-path?page=1&size=10",
                         headers=headers, timeout=TIMEOUT)
            latencies.append((time.time() - start) * 1000)
        avg = statistics.mean(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        _log(self.module, "NON_AI-03", "PASS" if p95 < 500 else "FAIL", avg,
             f"avg={avg:.0f}ms, p95={p95:.0f}ms (20次)")


def test_generate_report():
    all_results = list(results_log)
    seen = set()
    unique = []
    for r in all_results:
        key = f"{r['module']}::{r['case_id']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)
    for key, entry in _checkpoint_data.items():
        if key not in seen:
            unique.append(entry)
            seen.add(key)
    unique.sort(key=lambda x: x.get("timestamp", ""))
    if not unique:
        return
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_cases": len(unique),
        "passed": sum(1 for r in unique if r["status"] == "PASS"),
        "failed": sum(1 for r in unique if r["status"] == "FAIL"),
        "partial": sum(1 for r in unique if r["status"] == "PARTIAL"),
        "results": unique,
    }
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n{'='*60}")
    print(f"测试报告已生成: {report_path}")
    print(f"总用例: {report['total_cases']}, 通过: {report['passed']}, "
          f"失败: {report['failed']}, 部分通过: {report['partial']}")
    print(f"{'='*60}")