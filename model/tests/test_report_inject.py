"""ReportNode 学习激励/质量警告注入测试。

回归：此前用固定字符串 "### 个性化建议" replace，而模板标题是
"## 九、个性化建议"（两个 # 带编号），永远匹配不上，学习激励无法进入报告。
"""
import re

from app.agents.orchestrators.nodes.report_node import _inject_before_suggestion


def test_inject_before_profile_suggestion_heading():
    template = (
        "## 八、临床经验维度\n"
        "- 临床技能掌握情况：\n"
        "\n"
        "## 九、个性化建议\n"
        "- 基于画像的脑卒中学习建议：\n"
    )
    result = _inject_before_suggestion(template, "💡 **学习激励**: 保持动力！")

    # 激励内容插入到「个性化建议」标题之前
    assert result.index("💡 **学习激励**") < result.index("## 九、个性化建议")
    # 原文保留
    assert "## 八、临床经验维度" in result
    assert "- 基于画像的脑卒中学习建议：" in result


def test_inject_before_learning_suggestion_heading():
    template = "## 五、学习建议\n- 建议一\n"
    result = _inject_before_suggestion(template, "⚠️ **质量警告**: 检查事实一致性")

    assert result.index("⚠️ **质量警告**") < result.index("## 五、学习建议")
    assert "## 五、学习建议" in result


def test_inject_appends_when_no_suggestion_heading():
    template = "## 一、基本信息\n- 专业：临床医学\n"
    result = _inject_before_suggestion(template, "💡 **学习激励**: 加油！")

    # 找不到「建议」标题时追加到末尾
    assert result.endswith("💡 **学习激励**: 加油！")
    assert "## 一、基本信息" in result


def test_inject_matches_real_profile_template():
    """用真实 profile_build 模板验证注入命中「九、个性化建议」。"""
    from app.config.config_loader import get_report_manager

    mgr = get_report_manager()
    template = mgr.get_template("profile_build")
    assert template, "profile_build 模板应存在"

    result = _inject_before_suggestion(template, "💡 **学习激励**: 测试")
    idx_inject = result.index("💡 **学习激励**")
    idx_heading = result.index("## 九、个性化建议")
    assert idx_inject < idx_heading


def test_inject_matches_real_tutor_template():
    """用真实 tutor 模板验证注入命中「## 下一步建议」。

    回归：旧正则只匹配 5 种「建议」标题，漏掉 tutor 的「下一步建议」。
    """
    from app.config.config_loader import get_report_manager

    mgr = get_report_manager()
    template = mgr.get_template("tutor")
    assert template, "tutor 模板应存在"
    assert "## 下一步建议" in template

    result = _inject_before_suggestion(template, "💡 **学习激励**: 测试")
    idx_inject = result.index("💡 **学习激励**")
    idx_heading = result.index("## 下一步建议")
    assert idx_inject < idx_heading


def test_inject_matches_all_suggestion_variants():
    """所有含「建议」的标题变体都应命中注入点。"""
    variants = [
        "## 下一步建议",
        "## 进阶建议",
        "## 八、知识提升建议",
        "## 八、技能提升建议",
        "## 八、进度优化建议",
        "## 建议行动",
        "## 六、信息缺口与追踪建议",
        "## 四、学习建议与行动方案",
        "### 中长期发展建议（1-3个月）",
    ]
    for heading in variants:
        template = f"## 一、正文\n内容\n\n{heading}\n- 建议内容\n"
        result = _inject_before_suggestion(template, "💡 激励")
        assert result.index("💡 激励") < result.index(heading), f"未命中: {heading}"
