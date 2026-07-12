"""JsonParser 是所有 LLM 输出解析的最后防线，覆盖常见输出形态。"""
from app.agents.utils.json_parser import JsonParser


def test_plain_json():
    assert JsonParser.parse('{"a": 1}') == {"a": 1}


def test_json_in_markdown_block():
    assert JsonParser.parse('```json\n{"a": 1}\n```') == {"a": 1}


def test_json_in_bare_code_block():
    assert JsonParser.parse('```\n{"a": 1}\n```') == {"a": 1}


def test_json_with_surrounding_text():
    text = '好的，以下是结果：\n{"pathId": 3, "changes": []}\n希望对你有帮助。'
    assert JsonParser.parse(text) == {"pathId": 3, "changes": []}


def test_json_array():
    assert JsonParser.parse('[1, 2, 3]') == [1, 2, 3]


def test_invalid_returns_default():
    assert JsonParser.parse("这不是 JSON") is None
    assert JsonParser.parse("这不是 JSON", default={}) == {}
    assert JsonParser.parse("", default={}) == {}
    assert JsonParser.parse(None, default={}) == {}


def test_nested_chinese_content():
    text = '```json\n{"quickOpinion": "建议结合《神经病学》复习", "keyPoints": ["要点1"]}\n```'
    result = JsonParser.parse(text)
    assert result["quickOpinion"].startswith("建议")
