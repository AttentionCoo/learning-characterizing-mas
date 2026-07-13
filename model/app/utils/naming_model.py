import os
import logging

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

# 独立运行时也需要讯飞兼容性补丁（main.py 中也会执行，幂等安全）
from app.utils.xfyun_compat import apply_patches
apply_patches()

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NamingModel(object):
    def __init__(self):
        # 默认使用 PRO 档（原 Lite 服务已无额度，轻量任务复用 Pro）
        api_key = os.environ.get("SPARK_API_PASSWORD_PRO") or os.environ.get("SPARK_API_PASSWORD")
        model = os.environ.get("SPARK_MODEL_PRO") or "generalv3"
        base_url = (
            os.environ.get("SPARK_BASE_URL_PRO")
            or os.environ.get("SPARK_BASE_URL")
            or "https://spark-api-open.xf-yun.com/v1"
        )

        if not api_key:
            logger.warning("未找到环境变量 SPARK_API_PASSWORD，标题生成功能将不可用")
            self.llm = None
        else:
            self.llm = ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=0.3,
                max_tokens=300,
                timeout=25
            )

    def run_naming(self, question):
        logger.info(f"开始执行 run_naming() 方法，待处理内容: {question}")
        if self.llm is None:
            logger.warning("DEEPSEEK_API_KEY 未配置，跳过标题生成，返回默认标题")
            return "学习咨询"
        try:
            response = self.llm.invoke([
                SystemMessage(
                    content="你是一位专业教育标题生成人员，请将输入文本准确生成简短标题，标题长度控制在5-10个汉字内。"),
                HumanMessage(content=f"请将以下学习相关内容生成简洁的标题：\n{question}")
            ])
            result = response.content.strip()
            logger.info(f"生成标题结果: {result}")
            return result
        except Exception as e:
            logger.error(f"生成标题时发生错误: {str(e)}")
            return "学习咨询"


if __name__ == '__main__':
    nm = NamingModel()
    question = "我是计算机专业大二学生，想学好数据结构。"
    result = nm.run_naming(question)
    print(result)