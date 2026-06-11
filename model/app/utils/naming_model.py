import os
import logging

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NamingModel(object):
    def __init__(self):
        api_key = os.environ.get("DEEPSEEK-API-KEY")
        if not api_key:
            raise ValueError("未找到环境变量 DEEPSEEK-API-KEY，请设置该环境变量")
        self.llm = ChatOpenAI(
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key=api_key,
            temperature=0.3,
            max_tokens=300,
            timeout=25
        )

    def run_naming(self, question):
        logger.info(f"开始执行 run_naming() 方法，待处理内容: {question}")
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