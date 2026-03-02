import os
import asyncio
import logging
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from dotenv import load_dotenv
import platform
import sys

from configs.keys import keys

# Set proxy from environment variables if available
http_proxy = keys.get("HTTP_PROXY")
https_proxy = keys.get("HTTPS_PROXY")
if http_proxy:
    os.environ['http_proxy'] = http_proxy
if https_proxy:
    os.environ['https_proxy'] = https_proxy

load_dotenv()

from autogen_core import (
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
    SystemMessage,
    UserMessage,
)
from autogen_core.tools import Tool
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from utils import ranking, summarize
from configs.constants import DEFAULT_RETRIEVAL_CONFIG
from configs.utils import token_counter

os.makedirs('logs', exist_ok=True)
current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
log_filename = f'logs/debate_system_{current_time}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 创建文件处理器
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# 添加处理器到logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logging.getLogger().handlers = []

# 从环境变量获取API密钥
endpoint = os.getenv("ENDPOINT_URL")  
deployment = os.getenv("DEPLOYMENT_NAME")  
subscription_key = os.getenv("AZURE_OPENAI_API_KEY")  

# 创建Azure OpenAI客户端
client = AzureOpenAIChatCompletionClient(
    azure_endpoint=endpoint,  
    model=deployment,
    api_key=subscription_key,  
    api_version="2024-05-01-preview", 
)

# 定义常量
MAX_DEBATE_ROUNDS = 3  # 最大辩论轮数

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
    env_vars = ["ENDPOINT_URL", "DEPLOYMENT_NAME", "AZURE_OPENAI_API_KEY"]
    logger.info("环境变量:")
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # 隐藏敏感信息
            if var in ["ENDPOINT_URL", "AZURE_OPENAI_API_KEY"] and value:
                value = value[:10] + "..." + value[-10:] if len(value) > 20 else value
            logger.info(f"  {var}: {value}")
        else:
            logger.info(f"  {var}: 未设置")

# 记录命令行参数的函数
def log_arguments(args):
    """记录命令行参数"""
    logger.info("==================== 命令行参数 ====================")
    for arg, value in vars(args).items():
        logger.info(f"{arg}: {value}")

# 定义数据模型
class DebateQuestion(BaseModel):
    question: str
    background: str
    resolution_criteria: str
    date_begin: str
    date_end: str
    urls_in_background: list[str] = []

class DebateArgument(BaseModel):
    side: str  # "yes" 或 "no"
    argument: str
    evidence: str
    round: int

class DebateSummary(BaseModel):
    round: int
    yes_arguments: str
    no_arguments: str
    moderator_comments: str

class DebateResult(BaseModel):
    final_decision: str  # "yes" 或 "no"

# 辅助函数
def get_question_prompt(question: DebateQuestion) -> str:
    """生成问题提示，参考DebateAgent中的get_question_prompt"""
    prompt = f"""
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

# 定义主持人Agent
class ModeratorAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        system_message: SystemMessage,
        model_client: AzureOpenAIChatCompletionClient,
        tools: list[Tool],
    ) -> None:
        super().__init__(description)
        self._system_message = system_message
        self._model_client = model_client
        self._tools = dict([(tool.name, tool) for tool in tools])
        self._tool_schema = [tool.schema for tool in tools]
        self.current_round = 0
        self.debate_history = []
        self.question = None

    @message_handler
    async def start_debate(self, message: DebateQuestion, ctx: MessageContext) -> None:
        """开始辩论，设置问题"""
        self.question = message
        self.current_round = 0
        self.debate_history = []
        
        logger.info("=======Moderator: Debate Started=======")
        logger.info(f"Question: {message.question}")
        
        # 发送问题给正方和反方
        await self.publish_message(
            message, 
            topic_id=TopicId(type='debate_question', source='moderator')
        )
        
        # 返回辩论介绍
        intro_prompt = f"""
        You are moderating a debate on the following question:
        {get_question_prompt(message)}
        
        Please provide an introduction to this debate, explaining the question and setting the stage for the debaters.
        """
        
        user_message = UserMessage(content=intro_prompt, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message] + [user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)
        
        logger.info(f"Debate introduction:\n{llm_result.content}")
        
        # 通知第一轮辩论开始
        await self.publish_message(
            DebateArgument(side="request", argument="", evidence="", round=1),
            topic_id=TopicId(type='debate_turn', source='moderator')
        )

    @message_handler
    async def handle_argument(self, message: DebateArgument, ctx: MessageContext) -> None:
        """处理辩论者的论点"""
        if message.side not in ["yes", "no"]:
            return
            
        # 记录论点
        self.debate_history.append(message)
        logger.info(f"=======Moderator: Received {message.side.upper()} Argument for Round {message.round}=======")
        
        # 检查是否收到了当前轮次的两个论点
        current_round_args = [arg for arg in self.debate_history if arg.round == self.current_round + 1]
        
        if len(current_round_args) == 2:
            # 已收到两方论点，进入下一轮
            self.current_round += 1
            
            # 总结当前轮次
            yes_arg = next((arg for arg in current_round_args if arg.side == "yes"), None)
            no_arg = next((arg for arg in current_round_args if arg.side == "no"), None)
            
            summary_prompt = f"""
            Round {self.current_round} of the debate on:
            {self.question.question}
            
            YES side argument:
            {yes_arg.argument}
            
            Evidence for YES:
            {yes_arg.evidence}
            
            NO side argument:
            {no_arg.argument}
            
            Evidence for NO:
            {no_arg.evidence}
            
            Please summarize this round of debate, highlighting the key points from both sides and evaluating the strength of their arguments.
            """
            
            user_message = UserMessage(content=summary_prompt, source='user')
            llm_result = await self._model_client.create(
                messages=[self._system_message] + [user_message],
                cancellation_token=ctx.cancellation_token
            )
            token_counter.add_usage(llm_result.usage)
            
            round_summary = DebateSummary(
                round=self.current_round,
                yes_arguments=yes_arg.argument,
                no_arguments=no_arg.argument,
                moderator_comments=llm_result.content
            )
            
            logger.info(f"=======Moderator: Round {self.current_round} Summary=======")
            logger.info(f"Summary:\n{llm_result.content}")
            
            # 发布轮次总结
            await self.publish_message(
                round_summary,
                topic_id=TopicId(type='debate_summary', source='moderator')
            )
            
            # 检查是否达到最大轮数
            if self.current_round >= MAX_DEBATE_ROUNDS:
                # 辩论结束，做出最终判断
                await self.make_final_decision(ctx)
            else:
                # 开始下一轮
                await self.publish_message(
                    DebateArgument(side="request", argument="", evidence="", round=self.current_round + 1),
                    topic_id=TopicId(type='debate_turn', source='moderator')
                )
    
    async def make_final_decision(self, ctx: MessageContext) -> None:
        """做出最终判断"""
        # 整理所有轮次的论点
        yes_arguments = "\n\n".join([
            f"Round {arg.round}:\n{arg.argument}\nEvidence: {arg.evidence}"
            for arg in self.debate_history if arg.side == "yes"
        ])
        
        no_arguments = "\n\n".join([
            f"Round {arg.round}:\n{arg.argument}\nEvidence: {arg.evidence}"
            for arg in self.debate_history if arg.side == "no"
        ])
        
        decision_prompt = f"""
        You have moderated a debate on the following question:
        {get_question_prompt(self.question)}
        
        YES side arguments:
        {yes_arguments}
        
        NO side arguments:
        {no_arguments}
        
        Based on the strength of arguments and evidence presented by both sides, please make a final decision.
        Your response should only include your final decision (Yes or No).
        
        Format your response as:
        Decision: [Yes/No]
        """
        
        user_message = UserMessage(content=decision_prompt, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message] + [user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)
        
        # 解析结果
        result_text = llm_result.content
        decision_line = next((line for line in result_text.split('\n') if line.startswith('Decision:')), "")

        decision = decision_line.split(':', 1)[1].strip() if decision_line else "Unclear"

        # 简化决策结果为yes或no
        if decision.lower() not in ['yes', 'no']:
            if 'yes' in decision.lower():
                decision = 'yes'
            elif 'no' in decision.lower():
                decision = 'no'
            else:
                decision = 'Unclear'
        

        final_result = DebateResult(
            final_decision=decision
        )
        
        logger.info("=======Moderator: Final Decision=======")
        logger.info(f"Decision: {decision}")
        
        # 发布最终结果
        await self.publish_message(
            final_result,
            topic_id=TopicId(type='debate_result', source='moderator')
        )

# 定义辩论者Agent
class DebaterAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        system_message: SystemMessage,
        model_client: AzureOpenAIChatCompletionClient,
        tools: list[Tool],
        side: str  # "yes" 或 "no"
    ) -> None:
        super().__init__(description)
        self._system_message = system_message
        self._model_client = model_client
        self._tools = dict([(tool.name, tool) for tool in tools])
        self._tool_schema = [tool.schema for tool in tools]
        self.side = side
        self.question = None
        self.debate_history = []
        self.opponent_arguments = []
        self.moderator_summaries = []
    
    @message_handler
    async def receive_question(self, message: DebateQuestion, ctx: MessageContext) -> None:
        """接收辩论问题"""
        self.question = message
        self.debate_history = []
        self.opponent_arguments = []
        self.moderator_summaries = []
        logger.info(f"=======Debater {self.side.upper()}: Received Question=======")
    
    @message_handler
    async def receive_summary(self, message: DebateSummary, ctx: MessageContext) -> None:
        """接收轮次总结"""
        logger.info(f"=======Debater {self.side.upper()}: Received Round {message.round} Summary=======")
        self.moderator_summaries.append(message)

    @message_handler
    async def debate_turn(self, message: DebateArgument, ctx: MessageContext) -> DebateArgument:
        """轮到该辩论者发言"""
        if message.side != "request":
            if message.side != self.side:
                self.opponent_arguments.append(message)
            return None
            
        current_round = message.round
        logger.info(f"=======Debater {self.side.upper()}: Turn for Round {current_round}=======")
        
        # 获取对方的最新论点
        opponent_latest = ""
        if self.opponent_arguments:
            latest_opponent_arg = self.opponent_arguments[-1]
            opponent_latest = f"""
            Your opponent's latest argument (Round {latest_opponent_arg.round}):
            {latest_opponent_arg.argument}
            """
        
        # 获取主持人的最新总结
        moderator_latest = ""
        if self.moderator_summaries:
            latest_summary = self.moderator_summaries[-1]
            moderator_latest = f"""
            Moderator's latest summary (Round {latest_summary.round}):
            {latest_summary.moderator_comments}
            """

        # 确定需要检索的信息
        info_prompt = f"""
        You are debating the following question:
        {get_question_prompt(self.question)}
        
        You are on the {self.side.upper()} side.
        
        This is round {current_round} of the debate.
        
        {opponent_latest}
        
        {moderator_latest}
        
        What specific information would you need to retrieve to support your position?
        Please be specific and focus on factual information that would strengthen your argument.
        If the opponent has made arguments, consider what information you need to counter them.
        
        Return your answer in the format: (information to retrieve)
        """
        
        user_message = UserMessage(content=info_prompt, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message] + [user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)
        
        # 提取需要检索的信息
        info_to_retrieve = llm_result.content.strip()
        if info_to_retrieve.startswith('(') and info_to_retrieve.endswith(')'):
            info_to_retrieve = info_to_retrieve[1:-1].strip()
        
        logger.info(f"Information to retrieve: {info_to_retrieve}")
        
        # 使用ranking.retrieve_summarize_and_rank_articles检索信息
        ranked_articles = await ranking.retrieve_summarize_and_rank_articles(
            question=self.question.question,
            background_info=self.question.background,
            resolution_criteria=self.question.resolution_criteria,
            date_range=(self.question.date_begin, self.question.date_end),
            domain_ref=info_to_retrieve,
            urls=self.question.urls_in_background,
            return_intermediates=False
        )
        
        # 合并摘要
        all_summaries = summarize.concat_summaries(
            ranked_articles[: DEFAULT_RETRIEVAL_CONFIG["NUM_SUMMARIES_THRESHOLD"]]
        )
        
        logger.info(f"Retrieved information summary length: {len(all_summaries)}")
        
        # 生成论点
        argument_prompt = f"""
        You are debating the following question:
        {get_question_prompt(self.question)}
        
        You are on the {self.side.upper()} side.
        
        This is round {current_round} of the debate.
        
        {opponent_latest}
        
        {moderator_latest}
        
        Based on the following retrieved information, construct a strong argument for your position:
        
        {all_summaries}
        
        Your argument should be persuasive, logical, and well-supported by the evidence.
        Focus on the strongest points that support your position.
        
        If this is not the first round, make sure to address your opponent's arguments and the moderator's feedback.
        
        Format your response as:
        Argument: [your main argument]
        Evidence: [key evidence supporting your argument]
        """
        
        user_message = UserMessage(content=argument_prompt, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message] + [user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)
        
        # 解析结果
        result_text = llm_result.content
        argument_line = next((line for line in result_text.split('\n') if line.startswith('Argument:')), "")
        evidence_line = next((line for line in result_text.split('\n') if line.startswith('Evidence:')), "")
        
        argument = result_text
        evidence = all_summaries
        
        if argument_line and evidence_line:
            argument_start = result_text.find(argument_line)
            evidence_start = result_text.find(evidence_line)
            
            if argument_start >= 0 and evidence_start > argument_start:
                argument = result_text[argument_start + len('Argument:'):evidence_start].strip()
                evidence = result_text[evidence_start + len('Evidence:'):].strip()
        
        logger.info(f"=======Debater {self.side.upper()}: Argument for Round {current_round}=======")
        logger.info(f"Argument:\n{argument}")
        
        # 返回论点
        return DebateArgument(
            side=self.side,
            argument=argument,
            evidence=evidence,
            round=current_round
        )

# 主函数
async def run_debate(question: DebateQuestion, max_rounds: int = MAX_DEBATE_ROUNDS) -> DebateResult:
    """运行辩论"""

    runtime = SingleThreadedAgentRuntime()
    
    # 注册主持人
    await ModeratorAgent.register(
        runtime,
        type="moderator",
        factory=lambda: ModeratorAgent(
            description="A debate moderator",
            system_message=SystemMessage(
                content="""You are a fair and impartial debate moderator. Your responsibilities include:
                1. Introducing the debate topic
                2. Ensuring both debaters take turns speaking
                3. Summarizing each round of debate
                4. Evaluating the strength of arguments from both sides
                5. Making a final yes/no judgment based on the strength and persuasiveness of the arguments
                
                You should remain neutral throughout the debate and base your final decision solely on the quality of arguments and evidence presented.
                """
            ),
            model_client=client,
            tools=[],
        ),
    )
    
    # 注册支持方辩论者
    await DebaterAgent.register(
        runtime,
        type="yes_debater",
        factory=lambda: DebaterAgent(
            description="A debater supporting the YES position",
            system_message=SystemMessage(
                content="""You are a skilled debater arguing for the YES position. Your goal is to provide strong, evidence-based arguments that support a YES answer to the question.
                
                You should:
                1. Present clear, logical arguments
                2. Use factual evidence to support your points
                3. Address and counter opposing arguments
                4. Be persuasive but honest
                
                Focus on making the strongest case possible for the YES position.
                """
            ),
            model_client=client,
            tools=[],
            side="yes"
        ),
    )
    
    # 注册反对方辩论者
    await DebaterAgent.register(
        runtime,
        type="no_debater",
        factory=lambda: DebaterAgent(
            description="A debater supporting the NO position",
            system_message=SystemMessage(
                content="""You are a skilled debater arguing for the NO position. Your goal is to provide strong, evidence-based arguments that support a NO answer to the question.
                
                You should:
                1. Present clear, logical arguments
                2. Use factual evidence to support your points
                3. Address and counter opposing arguments
                4. Be persuasive but honest
                
                Focus on making the strongest case possible for the NO position.
                """
            ),
            model_client=client,
            tools=[],
            side="no"
        ),
    )
    
    # 设置订阅
    await runtime.add_subscription(TypeSubscription(topic_type="debate_question", agent_type="yes_debater"))
    await runtime.add_subscription(TypeSubscription(topic_type="debate_question", agent_type="no_debater"))
    await runtime.add_subscription(TypeSubscription(topic_type="debate_turn", agent_type="yes_debater"))
    await runtime.add_subscription(TypeSubscription(topic_type="debate_turn", agent_type="no_debater"))
    await runtime.add_subscription(TypeSubscription(topic_type="debate_summary", agent_type="yes_debater"))
    await runtime.add_subscription(TypeSubscription(topic_type="debate_summary", agent_type="no_debater"))
    
    # 创建结果队列
    result_queue = asyncio.Queue()
    
    # 注册结果收集器
    async def collect_result(_agent: ClosureContext, message: DebateResult, ctx: MessageContext) -> None:
        await result_queue.put(message)
    
    await ClosureAgent.register_closure(
        runtime,
        "result_collector",
        collect_result,
        subscriptions=lambda: [TypeSubscription(topic_type="debate_result", agent_type="result_collector")],
    )
    
    # 启动运行时
    runtime.start()
    
    # 发送问题给主持人
    moderator_id = AgentId(type="moderator", key="default")
    await runtime.send_message(question, moderator_id)
    
    # 等待结果
    result = await result_queue.get()
    
    # 停止运行时
    await runtime.stop_when_idle()
    
    return result

async def main(args):
    """主函数"""
    # 从文件加载问题
    log_environment_info()
    log_arguments(args)
    
    # 从文件加载问题
    file1 = os.path.join('./data', args.dataset, 'binary.json')
    with open(file1, 'r') as f:
        tdata = json.load(f)
    
    data = []
    for item in tdata:
        if item['date_resolve_at'] is not None:
            data.append(item)

    logger.info(f"Total number of questions: {len(data)}")
    logger.info(f"Number of questions with no: {len([item for item in data if item['resolution']==0])}")
    logger.info(f"Number of questions with yes: {len([item for item in data if item['resolution']==1])}")
    
    tdata = data[0]
    logger.info(f"====================Question====================")
    logger.info(f"Question URL: {tdata['url']}")
    logger.info(f"Question: {tdata['question']}")
    
    if len(tdata['extracted_urls']) < 1:
        tdata['extracted_urls'] = []
    
    if tdata['resolution'] == 0:
        ground_truth = 'no'
    elif tdata['resolution'] == 1:
        ground_truth = 'yes'
    else:
        ground_truth = 'unknown'

    # 创建问题对象
    question = DebateQuestion(
        question=tdata['question'],
        background=tdata['background'],
        resolution_criteria=tdata['resolution_criteria'],
        date_begin=tdata['date_begin'],
        date_end=tdata['date_close'],
        urls_in_background=tdata["extracted_urls"]
    )
    
    # 运行辩论
    # result = await run_debate(question)
    retry_count = 0
    max_retries = args.max_retries
    result = None
    while retry_count <= max_retries:
        try:
            logger.info(f"尝试执行 (第 {retry_count + 1}/{max_retries + 1} 次)")
            # asyncio.run(main(quest, args))
            result = await run_debate(question)
            logger.info("执行成功")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"执行失败: {str(e)}")
            
            if retry_count <= max_retries:
                logger.info(f"将在 5 秒后重试 ({retry_count}/{max_retries})...")
                time.sleep(5)
            else:
                logger.error(f"已达到最大重试次数 ({max_retries})，程序终止")
                break
    # 输出结果
    if result:
        # 简化输出，只显示最终结果和真实答案
        final_answer = result.final_decision.lower()
        if final_answer not in ['yes', 'no']:
            # 处理可能的格式不一致
            if 'yes' in final_answer:
                final_answer = 'yes'
            elif 'no' in final_answer:
                final_answer = 'no'
            else:
                final_answer = 'unknown'

    logger.info("====================Results====================")
    logger.info(f"Final results: {final_answer}")
    logger.info(f"Token usage:\n{token_counter}")
    logger.info(f"Question resolution: {ground_truth}")
    

    logger.info("Finish")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='辩论式预测系统')
    parser.add_argument('--dataset', type=str, default='cset',
                        help='数据集',choices=['cset','gjopen'])
    parser.add_argument('--max_rounds', type=int, default=MAX_DEBATE_ROUNDS,
                        help=f'最大辩论轮数，默认为{MAX_DEBATE_ROUNDS}')
    parser.add_argument('--max_retries', type=int, default=3,
                        help='执行失败时的最大重试次数，默认为3')
    args = parser.parse_args()
    
    # 运行主函数
    asyncio.run(main(args))