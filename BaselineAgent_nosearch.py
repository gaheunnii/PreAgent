import os
os.environ['http_proxy'] = "http://172.23.61.8:4780"
os.environ['https_proxy'] = "http://172.23.61.8:4780"
import platform
import sys
import argparse
from autogen_core import (
    FunctionCall,
    MessageContext,
    ClosureAgent,
    ClosureContext,
    RoutedAgent,
    SingleThreadedAgentRuntime,
    TopicId,
    TypeSubscription,
    message_handler,
    AgentId
)
from autogen_core.models import (
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from autogen_core import CancellationToken
from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
from autogen_core.tools import PythonCodeExecutionTool

from dataclasses import dataclass
from autogen_core.tools import FunctionTool, Tool
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from pydantic import BaseModel
import json
from configs.constants import DEFAULT_RETRIEVAL_CONFIG,MAX_DISCUSS_ROUND
from configs.utils import token_counter
from dotenv import load_dotenv
import asyncio
import logging
from datetime import datetime

load_dotenv()

os.makedirs('logs', exist_ok=True)

# Configure logging
current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
log_filename = f'logs/base_no_agent_conversation_{current_time}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'#,
)
logger = logging.getLogger(__name__)

# Create file handler
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logging.getLogger().handlers = []

endpoint = os.getenv("ENDPOINT_URL")  
deployment = os.getenv("DEPLOYMENT_NAME")  
subscription_key = os.getenv("AZURE_OPENAI_API_KEY")  
# client=AzureOpenAIChatCompletionClient(
#             azure_endpoint=endpoint,  
#             model=deployment,
#             api_key=subscription_key,  
#             api_version="2024-05-01-preview", 
#         )

proxies = {
    "http": "http://172.23.61.8:4780",  # 替换为翻墙工具的代理地址
    "https": "http://172.23.61.8:4780",
}


class Question(BaseModel):
    question: str
    background: str
    resolution_criteria:str
    date_begin:str
    date_end:str
    urls_in_background:list[str]
    resolution:str


def get_question_prompt(question: Question)->str:
    prompt=f"""
        Question:
        {question.question}

        Question Background:
        {question.background}

        Resolution Criteria:
        {question.resolution_criteria}

        Today's date: {question.date_begin}
        Question close date: {question.date_end}

    """
    return prompt


async def main(question:Question,args=None)->None:
    
    if args.prompt=='basic':
        system_prompt="""
            You are an expert in event prediction. Refer to the provided content and make a prediction for the following question. 
        """
    else:
        system_prompt="""
        You are an expert forecaster specializing in predicting future events with high accuracy. 
        You have extensive experience analyzing complex situations, identifying relevant factors, and making well-calibrated predictions.
        Your task is to analyze the provided question and make a clear yes/no prediction based on available information.
        """
    if args.prompt=='basic':
        local_task_prompts=f"""
        {get_question_prompt(question)}
        Analysis and predict the above question.
        Return the answer as either "(yes)" or "(no)". Do not return any redundant information. 
        """
    elif args.prompt=='concise':
        local_task_prompts=f"""
        {get_question_prompt(question)}
        
        Analyze the forecasting question above and provide your expert prediction.
        
        Consider all relevant information, historical trends, and specific conditions for resolution.
        
        Based on your comprehensive analysis, provide your prediction as either "(yes)" or "(no)".
        
        Your response should ONLY contain the prediction in the format "(yes)" or "(no)" without any additional text or explanation.
        """
    else:
        local_task_prompts=f"""
        {get_question_prompt(question)}
        
        Please analyze this forecasting question carefully by following these steps:
        
        1. Identify the key factors and variables that could influence the outcome
        2. Consider historical precedents and relevant trends
        3. Evaluate the timeframe and specific conditions for resolution
        4. Assess the likelihood of different scenarios
        5. Make a final prediction
        
        Based on your analysis, provide your prediction as either "(yes)" or "(no)".
        
        Your response should ONLY contain the prediction in the format "(yes)" or "(no)" without any additional text or explanation.
        """
    
    system_message = SystemMessage(
        content=system_prompt
    )
    user_message = UserMessage(
        content=local_task_prompts,source="user"
    )
    seed = args.seed if hasattr(args, 'seed') else 42
    temperature = args.temperature if hasattr(args, 'temperature') else 0.0

    llm_result = await client.create(
            messages=[system_message]+[user_message],
            cancellation_token=CancellationToken(),
            # options={
            #     "temperature": temperature,
            #     "seed": seed
            # }
        )
    token_counter.add_usage(llm_result.usage) 
    finals=llm_result.content.strip()[1:-1].strip()
    # finals=llm_result.content.strip()
    # print(finals)
    # print(token_counter)
    # print(question.resolution)
    logger.info(f"Final results: {finals}")
    logger.info(f"Token usage:\n{token_counter}")
    logger.info(f"Question resolution: {question.resolution}")
    if ('no' in finals.lower() and 'no' in question.resolution.lower()):
        # return [1,0,0,0]
        return [0,0]
    elif ('yes' in finals.lower() and 'yes' in question.resolution.lower()):
        # return [0,0,0,1]
        return [1,1]
    elif ('yes' in finals.lower() and 'no' in question.resolution.lower()):
        # return [0,1,0,0]
        return [1,0]
    else:   
        return [0,1]
        # return [0,0,1,0] 

def log_arguments(args):
    """记录命令行参数"""
    logger.info("==================== 命令行参数 ====================")
    for arg, value in vars(args).items():
        logger.info(f"{arg}: {value}")

# 记录运行环境信息的函数
def log_environment_info():
    """记录系统环境和Python版本信息"""
    logger.info("==================== 运行环境信息 ====================")
    logger.info(f"操作系统: {platform.system()} {platform.release()} ({platform.version()})")
    logger.info(f"Python版本: {platform.python_version()}")
    logger.info(f"处理器: {platform.processor()}")
    logger.info(f"机器: {platform.machine()}")
    logger.info(f"节点名称: {platform.node()}")
    logger.info(f"Python路径: {sys.executable}")
    
    # 记录重要的环境变量
    env_vars = ["ENDPOINT_URL", "DEPLOYMENT_NAME"]
    logger.info("环境变量:")
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # 隐藏敏感信息
            if var == "ENDPOINT_URL" and value:
                value = value[:10] + "..." + value[-10:] if len(value) > 20 else value
            logger.info(f"  {var}: {value}")
        else:
            logger.info(f"  {var}: 未设置")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='预测事件的发生')
    parser.add_argument('--dataset', type=str, default='cset',
                        help='数据集',choices=['cset','gjopen'])
    parser.add_argument('--prompt', type=str, default='detailed', 
                        choices=['basic', 'concise', 'detailed'],
                        help='选择提示词类型: basic(基础), concise(简洁), detailed(详细)')
    parser.add_argument('--seed', type=int, default=42,
                        help='LLM随机种子，用于结果复现，默认为42')
    parser.add_argument('--temperature', type=float, default=0.0,
                        help='LLM温度参数，值越低结果越确定，默认为0.0')
    args = parser.parse_args()
    global client
    client=AzureOpenAIChatCompletionClient(
            azure_endpoint=endpoint,  
            model=deployment,
            api_key=subscription_key,  
            api_version="2024-05-01-preview", 
            default_options={
                "seed": args.seed if hasattr(args, 'seed') else 42,
                "temperature": args.temperature if hasattr(args, 'temperature') else 0.0
            }
        )
    log_environment_info()
    log_arguments(args)
    
    file1=os.path.join('./data',args.dataset,'binary.json')
    with open(file1,'r') as f:
        tdata=json.load(f)

    data=[]
    for item in tdata:
        if item['date_resolve_at'] is None:
            continue
        data.append(item)
    logger.info(f"Total number of questions: {len(data)}")
    logger.info(f"Number of questions with no: {len([item for item in data if item['resolution']==0])}")
    logger.info(f"Number of questions with yes: {len([item for item in data if item['resolution']==1])}")
    
    
    # tdata=data[3]
    # print('====================Question====================')
    # print(tdata['url'])
    # print(tdata['question'])
    pred,ground=[],[]
    for tdata in data:
        logger.info(f"====================Question====================")
        logger.info(f"Question URL: {tdata['url']}")
        logger.info(f"Question: {tdata['question']}")

        if len(tdata['extracted_urls'])<1:
            tdata['extracted_urls']=[]
        if tdata['resolution']==0:
            gres='no'
        elif tdata['resolution']==1:
            gres='yes'
        else:
            gres='unknown'
            exit()
        quest=Question(question=tdata['question'],background=tdata['background'],\
                    resolution_criteria=tdata['resolution_criteria'],\
                        date_begin=tdata['date_begin'],date_end=tdata['date_close'],\
                        urls_in_background=tdata["extracted_urls"],resolution=gres)
        # logger.info(f"Question URL: {tdata['url']}, Question resolution: {tdata['resolution']}, {gres}")
        tres=asyncio.run(main(quest,args))
        pred.append(tres[0])
        ground.append(tres[1])
        logger.info(f"====================Finish the current question====================")
    logger.info("====================Results Stats====================")
    total = len(pred)
    correct = sum(1 for p, g in zip(pred, ground) if p == g)
    accuracy = correct / total if total > 0 else 0
    
    # 计算混淆矩阵
    true_positive = sum(1 for p, g in zip(pred, ground) if p == 1 and g == 1)
    false_positive = sum(1 for p, g in zip(pred, ground) if p == 1 and g == 0)
    true_negative = sum(1 for p, g in zip(pred, ground) if p == 0 and g == 0)
    false_negative = sum(1 for p, g in zip(pred, ground) if p == 0 and g == 1)
    
    # 计算精确率、召回率和F1分数
    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) > 0 else 0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    # 记录统计结果
    logger.info(f"总问题数: {total}")
    logger.info(f"正确预测数: {correct}")
    logger.info(f"准确率 (Accuracy): {accuracy:.4f}")
    logger.info(f"精确率 (Precision): {precision:.4f}")
    logger.info(f"召回率 (Recall): {recall:.4f}")
    logger.info(f"F1分数: {f1:.4f}")
    
    # 记录混淆矩阵
    logger.info("混淆矩阵:")
    logger.info(f"真正例 (TP): {true_positive}")
    logger.info(f"假正例 (FP): {false_positive}")
    logger.info(f"真负例 (TN): {true_negative}")
    logger.info(f"假负例 (FN): {false_negative}")
    # print('====================Finish====================')
    logger.info("Finish")