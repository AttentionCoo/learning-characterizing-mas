import logging

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage

from app.config.qwen import create_qwen_chat_model

load_dotenv(override=True)
logger = logging.getLogger(__name__)


class NamingModel(object):
    def __init__(self):
        try:
            self.llm = create_qwen_chat_model(
                "turbo",
                temperature=0.3,
                max_tokens=300,
                timeout=25,
            )
        except ValueError as exc:
            logger.warning(f"Qwen 模型未配置，标题生成功能将不可用: {exc}")
            self.llm = None

    def run_naming(self, question):
        logger.info(f"开始执行 run_naming() 方法，待处理内容: {question}")
        if self.llm is None:
            logger.warning("Qwen API Key 未配置，跳过标题生成，返回默认标题")
            return "学习咨询"
        try:
            response = self.llm.invoke([
                SystemMessage(
                    content="你是一位专业教育标题生成人员，请将输入文本准确生成简短标题，标题长度控制在5-10个汉字内。"),
                HumanMessage(content=f"请将以下学习相关内容生成简洁的标题：\n{question}")
            ])
            result = self._clean_title(getattr(response, "content", "") or "")
            logger.info(f"生成标题结果: {result}")
            return result
        except Exception as e:
            logger.error(f"生成标题时发生错误: {str(e)}")
            return "学习咨询"

    @staticmethod
    def _clean_title(text: str) -> str:
        """清理 LLM 返回的标题：去引号/书名号/markdown、去常见前缀、限制长度。"""
        title = (text or "").strip()
        # 去掉包裹的引号/书名号/反引号/空白
        title = title.strip('"\'「」『』《》`\u3000 \t\n')
        # 去掉 markdown 加粗标记
        title = title.strip('*#')
        title = title.strip()
        # 去掉常见前缀
        for prefix in ("标题：", "标题:", "题目：", "题目:", "标题是", "标题为"):
            if title.startswith(prefix):
                title = title[len(prefix):].strip()
        # 限制长度（避免 LLM 返回超长标题）
        if len(title) > 20:
            title = title[:20]
        return title or "学习咨询"


if __name__ == '__main__':
    nm = NamingModel()
    question = "我是计算机专业大二学生，想学好数据结构。"
    result = nm.run_naming(question)
    print(result)
