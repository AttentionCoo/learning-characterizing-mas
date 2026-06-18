
import os
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_yaml(filename: str) -> Dict[str, Any]:
    filepath = os.path.join(CONFIG_DIR, filename)
    logger.info(f"📂 尝试加载: {filepath}")

    if not os.path.exists(filepath):
        logger.error(f"❌ 配置文件不存在: {filepath}")
        try:
            files = os.listdir(CONFIG_DIR)
            logger.info(f"config/ 目录内容: {files}")
        except Exception:
            pass
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()

        logger.info(f"   文件大小: {len(raw)} 字节")

        data = yaml.safe_load(raw)

        if data and isinstance(data, dict):
            keys = list(data.keys())
            logger.info(f"✅ 已加载配置: {filename} ({len(keys)} 个 key)")
            logger.info(f"   所有 key: {keys}")

            for k, v in data.items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    logger.warning(f"   ⚠️ key '{k}' 的值为空!")
        else:
            logger.warning(f"⚠️ 配置文件为空或格式错误: {filename}")
            return {}

        return data

    except yaml.YAMLError as e:
        logger.error(f"❌ YAML 解析失败 {filename}: {e}")
        if hasattr(e, 'problem_mark'):
            mark = e.problem_mark
            logger.error(
                f"   错误位置: 第{mark.line + 1}行, 第{mark.column + 1}列"
            )
        return {}
    except Exception as e:
        logger.error(f"❌ 配置文件读取失败: {e}")
        return {}


class PromptManager:
    def __init__(self, prompt_file: str = "prompts.yaml"):
        self._prompts = _load_yaml(prompt_file)
        if not self._prompts:
            logger.warning("⚠️ Prompt 配置为空，所有调用将使用内置 fallback")

    def get(self, key: str, **kwargs) -> Optional[str]:
        template = self._prompts.get(key)

        if template is None:
            logger.warning(
                f"⚠️ Prompt key 不存在: '{key}'，"
                f"可用 keys: {list(self._prompts.keys())}"
            )
            return None

        if not isinstance(template, str) or not template.strip():
            logger.warning(f"⚠️ Prompt key '{key}' 的值为空")
            return None

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"⚠️ Prompt 变量缺失: {key} -> {e}")
            return template

    def has(self, key: str) -> bool:
        return (
            key in self._prompts
            and self._prompts[key] is not None
            and isinstance(self._prompts[key], str)
            and bool(self._prompts[key].strip())
        )

    def reload(self, prompt_file: str = "prompts.yaml"):
        self._prompts = _load_yaml(prompt_file)
        logger.info(f"🔄 Prompt 已热更新: {prompt_file}")


class ReportTemplateManager:
    def __init__(self, template_file: str = "report_templates.yaml"):
        self._data = _load_yaml(template_file)
        self._system_role = self._data.get("system_role", "")
        self._templates = {
            k: v for k, v in self._data.items()
            if k != "system_role" and isinstance(v, dict)
        }

    @property
    def system_role(self) -> str:
        if not self._system_role:
            return (
                "你是一位拥有20年教学经验的高等教育个性化学习顾问。"
                "禁止绝对性结论。禁止过度承诺。"
            )
        return self._system_role

    def get_template(self, mode: str = "emergency") -> str:
        entry = self._templates.get(mode, {})
        if not entry:
            logger.warning(f"⚠️ 报告模板不存在: {mode}，使用 emergency")
            entry = self._templates.get("emergency", {})
        return entry.get("template", "")

    def get_template_name(self, mode: str = "emergency") -> str:
        entry = self._templates.get(mode, {})
        return entry.get("name", mode)

    def get_template_config(self, mode: str = "emergency") -> dict:
        entry = self._templates.get(mode, {})
        if not entry:
            entry = self._templates.get("emergency", {})
        return entry

    def list_modes(self) -> list:
        return list(self._templates.keys())

    def update_doc_list(self, doc_names: list) -> None:
        import re
        if not doc_names:
            logger.warning("[文献列表] 传入文件名为空，保持静态列表")
            return

        new_list_text = "\n".join(f"- {name}" for name in sorted(set(doc_names)))
        pattern = r"(严禁自行创造[^\n]*\n)((?:- [^\n]*\n)+)(如需引用)"
        new_role, n = re.subn(pattern, rf"\g<1>{new_list_text}\n\g<3>", self._system_role)
        if n:
            self._system_role = new_role
            logger.info(f"[文献列表] 动态更新成功，共 {len(doc_names)} 篇: {doc_names}")
        else:
            fallback_inject = (
                f"\n\n【本次服务实际加载文献，引用时只能使用以下名称】\n"
                f"{new_list_text}\n"
                f"严禁引用上述列表之外的任何文献名。"
            )
            self._system_role += fallback_inject
            logger.warning(
                f"[文献列表] 正则定位失败，已末尾追加兜底注入，共 {len(doc_names)} 篇"
            )

    def reload(self, template_file: str = "report_templates.yaml"):
        self._data = _load_yaml(template_file)
        self._system_role = self._data.get("system_role", "")
        self._templates = {
            k: v for k, v in self._data.items()
            if k != "system_role" and isinstance(v, dict)
        }
        logger.info(f"🔄 报告模板已热更新: {template_file}")


class ExpertConfigManager:
    """专家配置管理器 - 管理多专家推理系统的专家配置"""

    def __init__(self, config_file: str = "expert_config.yaml"):
        self._data = _load_yaml(config_file)
        if not self._data:
            logger.warning("⚠️ 专家配置为空，使用默认配置")
            self._data = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认专家配置"""
        return {
            "experts": [
                {
                    "role": "画像对话智能体",
                    "instruction": "请与学生进行自然对话，引导其表达学习背景、知识水平、学习目标等信息。",
                    "system_prompt": "你是专业的学习画像构建顾问",
                    "priority": 1
                },
                {
                    "role": "特征抽取智能体",
                    "instruction": "请从对话内容中抽取结构化特征，包括专业、目标、知识水平、认知风格等维度。",
                    "system_prompt": "你是专业的学习特征分析专家",
                    "priority": 2
                },
                {
                    "role": "需求分析智能体",
                    "instruction": "请结合学生画像分析学习需求，拆解生成任务，确定需要的资源类型和难度级别。",
                    "system_prompt": "你是专业的学习需求分析师",
                    "priority": 3
                }
            ],
            "synthesis": {
                "prompt_template": "作为教学总监，请统筹以下各位智能体的意见，并给出最终综合提案(Proposal)和潜在问题批评(Critique)：\n{expert_opinions}\n请将输出分为两部分，用 \"### PROPOSAL ###\" 和 \"### CRITIQUE ###\" 隔开。",
                "opinion_separator": "【{role}建议】{opinion}\n",
                "proposal_separator": "### PROPOSAL ###",
                "critique_separator": "### CRITIQUE ###"
            },
            "enabled_experts": ["画像对话智能体", "特征抽取智能体", "需求分析智能体"]
        }

    def get_experts(self) -> list:
        """获取所有专家配置"""
        experts = self._data.get("experts", [])
        enabled = self._data.get("enabled_experts", [])
        
        if enabled:
            return [e for e in experts if e.get("role") in enabled]
        return experts

    def get_expert_by_role(self, role: str) -> Optional[Dict[str, Any]]:
        """根据角色名称获取专家配置"""
        experts = self.get_experts()
        for expert in experts:
            if expert.get("role") == role:
                return expert
        return None

    def get_synthesis_config(self) -> Dict[str, str]:
        """获取意见综合配置"""
        return self._data.get("synthesis", {})

    def get_debate_config(self) -> Dict[str, Any]:
        """获取辩论-仲裁配置"""
        return self._data.get("debate", {})

    def is_debate_enabled(self) -> bool:
        """是否启用辩论模式"""
        debate = self._data.get("debate", {})
        return debate.get("enabled", False)

    def get_debate_max_rounds(self) -> int:
        """获取辩论最大轮数"""
        debate = self._data.get("debate", {})
        return debate.get("max_rounds", 2)

    def get_arbitrator_role(self) -> str:
        """获取仲裁智能体角色名"""
        debate = self._data.get("debate", {})
        return debate.get("arbitrator_role", "仲裁智能体")

    def get_dynamic_orchestration_config(self) -> Dict[str, Any]:
        """获取动态编排配置"""
        return self._data.get("dynamic_orchestration", {})

    def is_dynamic_orchestration_enabled(self) -> bool:
        """是否启用动态编排"""
        orch = self._data.get("dynamic_orchestration", {})
        return orch.get("enabled", False)

    def get_intent_expert_mapping(self) -> Dict[str, list]:
        """获取意图-专家映射"""
        orch = self._data.get("dynamic_orchestration", {})
        return orch.get("intent_expert_mapping", {})

    def get_difficulty_thresholds(self) -> Dict[str, float]:
        """获取难度阈值配置"""
        orch = self._data.get("dynamic_orchestration", {})
        return orch.get("difficulty_thresholds", {"low": 0.3, "medium": 0.6, "high": 1.0})

    def get_experts_for_intent_and_difficulty(self, intent_type: str, difficulty_score: float) -> list:
        """根据意图类型和难度评分获取应参与的专家列表"""
        orch = self._data.get("dynamic_orchestration", {})
        if not orch.get("enabled", False):
            return [e.get("role") for e in self.get_experts()]

        intent_mapping = orch.get("intent_expert_mapping", {})
        intent_experts = intent_mapping.get(intent_type, [])

        if not intent_experts:
            return [e.get("role") for e in self.get_experts()]

        all_experts = self.get_experts()
        result = []
        for expert in all_experts:
            role = expert.get("role")
            if role not in intent_experts:
                continue
            min_diff = expert.get("min_difficulty", 0.0)
            if difficulty_score >= min_diff:
                result.append(role)

        if not result:
            result = intent_experts[:3]

        return result

    def reload(self, config_file: str = "expert_config.yaml"):
        """重新加载配置"""
        self._data = _load_yaml(config_file)
        if not self._data:
            self._data = self._get_default_config()
        logger.info(f"🔄 专家配置已热更新: {config_file}")


class ValidationConfigManager:
    """校验配置管理器 - 管理规则引擎和校验设置"""

    def __init__(self, config_file: str = "rules_config.yaml"):
        self._data = _load_yaml(config_file)
        if not self._data:
            logger.warning("⚠️ 校验配置为空，使用默认配置")
            self._data = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认校验配置"""
        return {
            "contraindication_rules": {
                "资源生成": ["内容与知识点无关", "难度与学生水平不匹配", "缺少实例或练习"],
                "画像构建": ["未覆盖核心维度", "描述不具体", "水平评估无依据"],
                "学习路径": ["阶段划分不合理", "时间估算不可行", "缺少评估节点"]
            },
            "validation_settings": {
                "max_reflection_count": 3,
                "enable_rule_engine": True,
                "enable_llm_reflection": True
            }
        }

    def get_contraindication_rules(self) -> Dict[str, list]:
        """获取质量校验规则"""
        return self._data.get("contraindication_rules", {})

    def get_max_reflection_count(self) -> int:
        """获取最大反思次数"""
        settings = self._data.get("validation_settings", {})
        return settings.get("max_reflection_count", 3)

    def is_rule_engine_enabled(self) -> bool:
        """是否启用规则引擎"""
        settings = self._data.get("validation_settings", {})
        return settings.get("enable_rule_engine", True)

    def is_llm_reflection_enabled(self) -> bool:
        """是否启用LLM反思"""
        settings = self._data.get("validation_settings", {})
        return settings.get("enable_llm_reflection", True)

    def is_annealing_enabled(self) -> bool:
        """是否启用动态退火策略"""
        annealing = self._data.get("annealing", {})
        return annealing.get("enabled", False)

    def get_weight_decay_factor(self) -> float:
        """获取权重衰减因子"""
        annealing = self._data.get("annealing", {})
        return annealing.get("weight_decay_factor", 0.5)

    def get_category_correction_prompts(self) -> Dict[str, str]:
        """获取分类修正提示词"""
        annealing = self._data.get("annealing", {})
        return annealing.get("category_correction_prompts", {})

    def get_rejection_category_keywords(self) -> Dict[str, list]:
        """获取驳回分类关键词映射"""
        annealing = self._data.get("annealing", {})
        return annealing.get("rejection_category_keywords", {})

    def classify_rejection(self, feedback: str) -> str:
        """根据驳回反馈自动分类驳回原因"""
        category_keywords = self.get_rejection_category_keywords()
        if not category_keywords:
            return "general"
        for category, keywords in category_keywords.items():
            for kw in keywords:
                if kw in feedback:
                    return category
        return "general"

    def get_correction_prompt_for_category(self, category: str) -> str:
        """根据驳回分类获取针对性修正提示词"""
        correction_prompts = self.get_category_correction_prompts()
        return correction_prompts.get(category, "请根据反馈意见修正你的输出。")

    def reload(self, config_file: str = "rules_config.yaml"):
        """重新加载配置"""
        self._data = _load_yaml(config_file)
        if not self._data:
            self._data = self._get_default_config()
        logger.info(f"🔄 校验配置已热更新: {config_file}")


class LimitsConfigManager:
    """参数限制配置管理器 - 管理各种字符数限制和关键词配置"""

    def __init__(self, config_file: str = "limits_config.yaml"):
        self._data = _load_yaml(config_file)
        if not self._data:
            logger.warning("⚠️ 参数限制配置为空，使用默认配置")
            self._data = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认参数限制配置"""
        return {
            "limits": {
                "max_sub_questions": 3,
                "max_evidence_chars": 2000,
                "max_evidence_per_question": 600,
                "max_proposal_chars": 3000,
                "max_critique_chars": 3000
            },
            "keywords": {
                "diagnostic": ["知识水平", "认知风格", "学习目标", "薄弱点", "画像", "维度", "特征", "评估", "诊断"],
                "treatment": ["资源生成", "辅导", "学习路径", "推荐", "个性化", "难度", "练习", "课程", "规划"],
                "prognosis": ["学习效果", "掌握度", "进度", "评估", "优化", "调整", "反馈", "完成率"]
            }
        }

    def get_limit(self, key: str) -> int:
        """获取指定的限制值"""
        limits = self._data.get("limits", {})
        return limits.get(key, 0)

    def get_max_sub_questions(self) -> int:
        """获取最大子问题数量"""
        return self.get_limit("max_sub_questions")

    def get_max_evidence_chars(self) -> int:
        """获取最大证据字符数"""
        return self.get_limit("max_evidence_chars")

    def get_max_evidence_per_question(self) -> int:
        """获取每个问题的最大证据字符数"""
        return self.get_limit("max_evidence_per_question")

    def get_max_proposal_chars(self) -> int:
        """获取最大提案字符数"""
        return self.get_limit("max_proposal_chars")

    def get_max_critique_chars(self) -> int:
        """获取最大批判字符数"""
        return self.get_limit("max_critique_chars")

    def get_keywords(self, category: str) -> list:
        """获取指定类别的关键词"""
        keywords = self._data.get("keywords", {})
        return keywords.get(category, [])

    def get_diagnostic_keywords(self) -> list:
        """获取学习诊断相关关键词"""
        return self.get_keywords("diagnostic")

    def get_treatment_keywords(self) -> list:
        """获取学习辅导相关关键词"""
        return self.get_keywords("treatment")

    def get_prognosis_keywords(self) -> list:
        """获取学习预后相关关键词"""
        return self.get_keywords("prognosis")

    def reload(self, config_file: str = "limits_config.yaml"):
        """重新加载配置"""
        self._data = _load_yaml(config_file)
        if not self._data:
            self._data = self._get_default_config()
        logger.info(f"🔄 参数限制配置已热更新: {config_file}")


_prompt_manager: Optional[PromptManager] = None
_report_manager: Optional[ReportTemplateManager] = None
_expert_manager: Optional[ExpertConfigManager] = None
_validation_manager: Optional[ValidationConfigManager] = None
_limits_manager: Optional[LimitsConfigManager] = None


def get_prompt_manager() -> PromptManager:
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def get_report_manager() -> ReportTemplateManager:
    global _report_manager
    if _report_manager is None:
        _report_manager = ReportTemplateManager()
    return _report_manager


def get_expert_manager() -> ExpertConfigManager:
    """获取专家配置管理器单例"""
    global _expert_manager
    if _expert_manager is None:
        _expert_manager = ExpertConfigManager()
    return _expert_manager


def get_validation_manager() -> ValidationConfigManager:
    """获取校验配置管理器单例"""
    global _validation_manager
    if _validation_manager is None:
        _validation_manager = ValidationConfigManager()
    return _validation_manager


def get_limits_manager() -> LimitsConfigManager:
    """获取参数限制配置管理器单例"""
    global _limits_manager
    if _limits_manager is None:
        _limits_manager = LimitsConfigManager()
    return _limits_manager