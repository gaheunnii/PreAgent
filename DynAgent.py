import os
os.environ['http_proxy'] = "http://172.23.61.8:4780"
os.environ['https_proxy'] = "http://172.23.61.8:4780"

import argparse
import platform
import sys
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
    AssistantMessage,
    ChatCompletionClient,
    FunctionExecutionResult,
    FunctionExecutionResultMessage,
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from dataclasses import dataclass
from autogen_core.tools import FunctionTool, Tool
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from pydantic import BaseModel
import json
import uuid
from typing import List, Tuple
import time
from utils import ranking,summarize
from configs.constants import DEFAULT_RETRIEVAL_CONFIG,MAX_DISCUSS_ROUND
from configs.utils import token_counter
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import asyncio
import logging
from datetime import datetime

load_dotenv()

os.makedirs('logs', exist_ok=True)

# Configure logging
current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
log_filename = f'logs/dynamic_agent_conversation_{current_time}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'#,
)
logger = logging.getLogger(__name__)

# # Create file handler
# file_handler = logging.FileHandler(log_filename)
# file_handler.setLevel(logging.INFO)
# file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# # Create console handler
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging.INFO)
# console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# # Add handlers to logger
# logger.addHandler(file_handler)
# logger.addHandler(console_handler)
# logging.getLogger().handlers = []

endpoint = os.getenv("ENDPOINT_URL")  
deployment = os.getenv("DEPLOYMENT_NAME")  
subscription_key = os.getenv("AZURE_OPENAI_API_KEY")  


proxies = {
    "http": "http://172.23.61.8:4780",  # 替换为翻墙工具的代理地址
    "https": "http://172.23.61.8:4780",
}

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
    env_vars = ["ENDPOINT_URL", "DEPLOYMENT_NAME", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"]
    logger.info("环境变量:")
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # 隐藏敏感信息
            if var in ["ENDPOINT_URL", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"] and value:
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

def google_search(query: str, num_results: int = 2, max_chars: int = 500) -> list:  # type: ignore[type-arg]
    
    

    api_key = os.getenv("GOOGLE_API_KEY")
    search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

    if not api_key or not search_engine_id:
        raise ValueError("API key or Search Engine ID not found in environment variables")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": search_engine_id, "q": query, "num": num_results}

    response = requests.get(url, params=params, proxies=proxies)  # type: ignore[arg-type]

    if response.status_code != 200:
        logger.info(response.json())
        logger.error(f"Error in API request: {response.status_code}")
        raise Exception(f"Error in API request: {response.status_code}")

    results = response.json().get("items", [])

    def get_page_content(url: str) -> str:
        try:
            response = requests.get(url, timeout=10, proxies=proxies)
            soup = BeautifulSoup(response.content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            words = text.split()
            content = ""
            for word in words:
                if len(content) + len(word) + 1 > max_chars:
                    break
                content += " " + word
            return content.strip()
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return ""

    enriched_results = []
    for item in results:
        body = get_page_content(item["link"])
        enriched_results.append(
            {"title": item["title"], "link": item["link"], "snippet": item["snippet"], "body": body}
        )
        time.sleep(1)  # Be respectful to the servers

    return enriched_results

class Question(BaseModel):
    question: str
    background: str
    resolution_criteria:str
    date_begin:str
    date_end:str
    urls_in_background:list[str]
    resolution:str

class expersdomains(BaseModel):
    domains:str

class firstrounds(BaseModel):
    answer:str
    reason: str
    allres:str
    domains:str

class QandA(BaseModel):
    question: str
    background: str
    resolution_criteria:str
    date_begin:str
    date_end:str
    urls_in_background:list[str]
    questionall:str
    feedbacks:str

class finalans(BaseModel):
    ans:str

class discuss(BaseModel):
    question: str
    background: str
    resolution_criteria:str
    date_begin:str
    date_end:str
    urls_in_background:list[str]
    questionall:str
    disc:str
    ret:str

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

def get_expert_domains_prompt(max_experts=5):
    return f"""
    Please identify the key domains of expertise required to analyze and predict the outcome of this question.
    
    Consider the following aspects:
    1. The specific subject matter of the question
    2. Technical or specialized knowledge areas relevant to the prediction
    3. Methodological approaches that would be valuable (e.g., statistical analysis, historical analysis)
    4. Contextual knowledge domains that would provide important perspective
    
    List a maximum of {max_experts} domains of expertise, prioritizing those most critical for accurate prediction.
    
    Return results in the following format: (Domain 1, Domain 2, ...).
    For example: (Economic Policy, International Relations, Political Science).
    """

# def get_expert_analysis_prompt(disc):
#     return f"""
#     Discussion summary:
#     {disc}

#     Based on the discussion summary and your domain expertise, what specific information would be most valuable to retrieve to improve our prediction?
    
#     If you need additional information, please consider:
#     - The exact type of information needed
#     - Why this information would be valuable for the prediction
#     - How specific or broad the search should be
    
#     If you need to retrieve information, return your search request in the format: (search request). Only return the search request, do not return any other content.

#     If you have sufficient information already, return: (No). Only return (No).
#     """

def get_expert_analysis_prompt(disc):
    return f"""
    Discussion summary:
    {disc}

    Consider the following aspects and decide whether you need to retrieve additional information:
    1. What critical information gaps exist in the current discussion
    2. What specific data or facts could validate or challenge current assumptions
    3. What relevant historical precedents or case studies might provide insight
    4. What domain-specific statistics or trend analyses would be beneficial
    
    If you need to retrieve the information, briefly describe the information you need to retrieve to constructed the search query and return the search query in the following format: Query : [the search query].
    If you do not need to retrieve the information, return the answer in the following format: Query : [no].
    """
    # return f"""
    # Discussion summary:
    # {disc}

    # As a domain expert, please evaluate what additional information would be most valuable to enhance our prediction accuracy.
    
    # Consider the following aspects and decide whether you need to retrieve additional information:
    # 1. What critical information gaps exist in the current discussion
    # 2. What specific data or facts could validate or challenge current assumptions
    # 3. What relevant historical precedents or case studies might provide insight
    # 4. What domain-specific statistics or trend analyses would be beneficial
    
    # If you need to retrieve the information, briefly describe the information you need to retrieve to constructed the search query and return the search query in the following format: Query : [the search query].
    # If you do not need to retrieve the information, return the answer in the following format: Query : [no].
    # """

# def get_expert_analysis_prompt(disc):
#     return """

#         Discussion summary:
#         {}

#         Considering the discussion summary, what information do you need to retrieve to solve the above question?
#         If you need to retrieve the information, briefly describe the information you need to retrieve and return the answer in the following format:
#         (the information)
#         If you do not need to retrieve the information, return (No)
#         """.format(disc)

def get_expert_feedback_prompt(all_summaries):
    return f"""
    Please analyze the following retrieved information:
    {all_summaries}
    
    Based on this information and your domain expertise, provide:
    1. Your assessment of how this affects the prediction
    2. Your reasoning process, highlighting key factors
    3. Your confidence level in this assessment
    
    Return your analysis in the following format:
    Answer: [Yes/No].
    Reasons: [Your detailed reasoning]
    """

def get_organizer_summary_prompt(question, hist, feedbacks):
    return f"""
    Question:
    {question}
    
    Previous discussion summary:
    {hist}

    New expert feedback:
    {feedbacks}

    As the discussion organizer, please:
    1. Integrate the new expert feedback with previous discussions
    2. Identify areas of consensus and disagreement
    3. Highlight the most relevant insights for the prediction
    4. Note any remaining uncertainties or gaps in knowledge
    
    Provide a comprehensive summary that captures the current state of the analysis.
    """

def get_organizer_decision_prompt(round_num, max_rounds):
    if round_num > max_rounds:
        return """
        Based on all expert discussions and the complete analysis:
        
        1. Evaluate the balance of evidence for and against the prediction
        2. Consider the strength and relevance of each expert's contribution
        3. Make your final prediction
        
        Please give the final result, and return results in the following format, (Yes/No)
        """
    else:
        return """
        Based on the current state of the expert discussion:
        
        1. Evaluate whether sufficient information exists to make a confident prediction
        2. Consider if any critical domain expertise is still missing
        3. Determine if additional consultation would significantly improve prediction accuracy
        
        If you can confidently make a judgment based on the information you have, then give the final result, otherwise return to the expert field you need to consult.
        If you are confident to make the judgement, return results in the following format, (Yes/No).
        Otherwise, only return the expert field, (Area).
        """

class OrganAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        system_message:SystemMessage,
        model_client: AzureOpenAIChatCompletionClient,
        tools: list[Tool],
        user_topic_type:str
    ) -> None:
        super().__init__(description)
        self._system_message=system_message
        self._model_client=model_client
        self._tools=dict([(tool.name, tool) for tool in tools])
        self._tool_schema=[tool.schema for tool in tools]
        self.user_topic_type=user_topic_type
        self.domainexperts=set()
        self.hist=""
        self.round=0
        self.max_experts = 5

    @message_handler
    async def setup_max_experts(self, message: expersdomains, ctx: MessageContext) -> None:
        """处理设置max_experts的消息"""
        if message.domains.startswith("setup_max_experts_"):
            try:
                # 从消息中提取max_experts值
                self.max_experts = int(message.domains.split("_")[-1])
                logger.info(f"设置最大专家数量为: {self.max_experts}")
            except (ValueError, IndexError):
                logger.error("无法从消息中提取max_experts值")

    @message_handler
    async def handle_question(self,message:Question, ctx: MessageContext)->expersdomains:
        # 生成几个专家，让他们处理问题
        # local_task_prompts="""
        # Please list the fields of expertise required to solve the aforementioned problem, with a maximum of 5 fields. 
        # Generally, the more complex the problem, the broader the scope, and the more fields of expertise are needed.
        # Return results in the following format, (Field 1, Feild 2, ...).
        # One return example is, "(Differential Geometry, Deep Learning)".
        # """
        # max_experts = getattr(ctx, 'max_experts', self.max_experts)
        local_task_prompts = get_expert_domains_prompt(self.max_experts)
        user_message=UserMessage(content=get_question_prompt(message)+local_task_prompts,source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        
        domains=llm_result.content[1:-1].split(',')
        for item in domains:
            self.domainexperts.add(item.strip())
    
        logger.info("=======org: domain get=======")
        logger.info(f"需要的专家领域 User message:\n{user_message.content}")
        logger.info(f"需要的专家领域LLM response:\n{llm_result.content}")
        return expersdomains(domains=llm_result.content)
    
    @message_handler
    async def handle_response(self,message:QandA,ctx:MessageContext)->finalans:
        self.round+=1
        
        # llm_local_prompts="""
        # Question:
        # {}
        
        # History minutes:
        # {}

        # New feedback:
        # {}

        # According to the question, sort out historical minutes and new feedback, and give the summary minutes of the combination of the historyical minutes and new feedback.
        # """.format(message.questionall, self.hist, message.feedbacks)
        llm_local_prompts = get_organizer_summary_prompt(message.questionall, self.hist, message.feedbacks)
        user_message=UserMessage(content=llm_local_prompts,source='user')
        llm_results=await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        
        self.hist=llm_results.content
        token_counter.add_usage(llm_results.usage) 
        dismessage=discuss(question=message.question,background=message.background,resolution_criteria=message.resolution_criteria,\
                       date_begin=message.date_begin,date_end=message.date_end,urls_in_background=message.urls_in_background,\
                       questionall=message.questionall,disc=llm_results.content,ret='ret')
        
        
        logger.info(f"=======org: discussion round: {self.round}=======")
        logger.info(f"组织者总结已有的知识User message:\n{user_message.content}")
        logger.info(f"组织者总结已有的知识LLM response:\n{llm_results.content}")
        
        # if self.round>MAX_DISCUSS_ROUND:
        #     local_task_prompts="""
        #     Consider the questions and the summary of discussion.
        #     Please give the final result, and return results in the following format, (Yes/No)
        #     """
        # else:
        #     local_task_prompts="""
        #     Consider the questions and the summary of discussion.
        #     If you can confidently make a judgment based on the information you have, then give the final result, otherwise return to the expert field you need to consult.
        #     If you are confident to make the judgement, return results in the following format, (Yes/No)
        #     Otherwise, only return the expert field, (Area)
        #     """
        local_task_prompts = get_organizer_decision_prompt(self.round, MAX_DISCUSS_ROUND)
        user_message=UserMessage(content=dismessage.questionall+"\n The following are the summary of discussion, \n"+dismessage.disc+'\n'+local_task_prompts,source='user')
        
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        res=llm_result.content
    
        
        logger.info(user_message.content)
        logger.info(f"是否还需要新的专家LLM response:\n{llm_result.content}")

        if res=='Yes' or res=='No' or res=='(Yes)' or res=='(No)':             
            return finalans(ans=llm_result.content)    
        else:
            domainfield=res[1:-1].strip()
            self.domainexperts.add(domainfield)
            agentid=AgentId(type='discuss_exp',key='default')
            await self.send_message(expersdomains(domains=domainfield),agentid)
            ts=await self.send_message(dismessage,agentid)
            qanda=QandA(question=message.question,background=message.background,resolution_criteria=message.resolution_criteria,\
                date_begin=message.date_begin,date_end=message.date_end,\
                urls_in_background=message.urls_in_background,questionall=message.questionall,feedbacks=ts)
            return await self.send_message(qanda,AgentId('organ_agent','default'))


class ExpertAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        system_message:SystemMessage,
        model_client: AzureOpenAIChatCompletionClient,
        tools: list[Tool],
        user_topic_type:str
    ) -> None:
        super().__init__(description)
        self._system_message=system_message
        self._model_client=model_client
        self._tools=dict([(tool.name, tool) for tool in tools])
        self._tool_schema=[tool.schema for tool in tools]
        self.user_topic_type=user_topic_type

    @message_handler
    async def set_systemmeessage_domains(self,message:expersdomains,ctx:MessageContext)->None:
        self.domains=message.domains
        self._system_message.content=self._system_message.content.format(self.domains)
        

    @message_handler
    async def handle_question(self,message:discuss, ctx: MessageContext)->firstrounds:
        # local_task_prompts="""

        # Discussion summary:
        # {}

        # Considering the discussion summary, what information do you need to retrieve to solve the above question?
        # If you need to retrieve the information, briefly describe the information you need to retrieve and return the answer in the following format:
        # (the information)
        # If you do not need to retrieve the information, return (No)
        # """.format(message.disc)
        local_task_prompts = get_expert_analysis_prompt(message.disc)
        user_message=UserMessage(content=message.questionall+local_task_prompts,source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        
        logger.info(f"=====Expert {self.domains} Response=====")
        logger.info(f"专家{self.domains}是否需要检索知识User message:\n{user_message.content}")
        logger.info(f"专家{self.domains}是否需要检索知识LLM response:\n{llm_result.content}")

        domain_ref=llm_result.content.strip()
        # if domain_ref.startswith('[') or domain_ref.startswith('('):
        #     domain_ref=domain_ref[1:-1]
        if '[' in domain_ref:
            domain_ref=domain_ref.split('[')[1].strip()
        if '(' in domain_ref:
            domain_ref=domain_ref.split('(')[1].strip()
        if ']' in domain_ref:
            domain_ref=domain_ref.split(']')[0].strip()
        if ')' in domain_ref:
            domain_ref=domain_ref.split(')')[0].strip()
        if domain_ref.lower()=='no':
            all_summaries="No need to retrieve."
        else:
            ranked_articles=await ranking.retrieve_summarize_and_rank_articles(
                question=message.question,
                background_info=message.background,
                resolution_criteria=message.resolution_criteria,
                date_range=(message.date_begin,message.date_end),
                domain_ref=domain_ref,
                urls=message.urls_in_background,
                return_intermediates=False)
            all_summaries = summarize.concat_summaries(
                ranked_articles[: DEFAULT_RETRIEVAL_CONFIG["NUM_SUMMARIES_THRESHOLD"]]
            )
        # local_task_prompts="""
        # Please combine the following retrieved summary:
        # {}
        # Then give your answers to the above questions and provide reasons. 
        # Return results in the following format,
        # Answer: answer.
        # Reasons: reasons.
        # """.format(all_summaries)
        local_task_prompts = get_expert_feedback_prompt(all_summaries)
        user_message=UserMessage(content=get_question_prompt(message)+local_task_prompts,source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        firstres=firstrounds(answer='',reason='',\
                             allres="Expert in %s provide the following feedback:\n"%self.domains+llm_result.content,\
                             domains=self.domains)
        
        logger.info(f"专家{self.domains}的回答User message:\n{user_message.content}")
        logger.info(f"专家{self.domains}的回答LLM response:\n{llm_result.content}")

        if message.ret=='pub':
            await self.publish_message(firstres, topic_id=TopicId(type='first_round_feedback',source='default'))
        return firstres

async def main(question:Question, args=None)->None:
    global MAX_DISCUSS_ROUND
    if args and args.max_rounds:
        MAX_DISCUSS_ROUND = args.max_rounds
    max_experts = args.max_experts if args and hasattr(args, 'max_experts') else 5

    runtime = SingleThreadedAgentRuntime()
    await OrganAgent.register(
        runtime,
        type="organ_agent",
        factory=lambda: OrganAgent(
            description="An organizer",
            # system_message=SystemMessage(
            #     content="You are an organizer who organizes experts to make predictions."
            #     "Analyse the questions and organize experts to solve the question."
            #     "According to the gathered statements from experts, make the final prediction."
            # ),
            system_message=SystemMessage(
                content="""You are a skilled discussion organizer and decision-maker.
                Your role is to:
                1. Identify the necessary domains of expertise for complex predictions
                2. Coordinate expert input and synthesize their insights
                3. Identify knowledge gaps and request specific expertise when needed
                4. Make a final prediction when sufficient information is available
                
                Maintain a structured approach to problem-solving and ensure all relevant perspectives are considered.
                """
            ),
            model_client=client,
            tools=[],
            user_topic_type="experts"
        ),
    )
    runtime.start()
    # session_id=str(uuid.uuid4())
    
    # ctx = MessageContext()
    # ctx.max_experts = max_experts
    
    # org_agent_id=AgentId('organ_agent','default')
    # expertds=await runtime.send_message(question, org_agent_id, ctx)

    org_agent_id=AgentId('organ_agent','default')
    # organ_agent = runtime.get_agent(org_agent_id)
    # if hasattr(organ_agent, 'max_experts'):
    #     organ_agent.max_experts = max_experts
    setup_message = expersdomains(domains=f"setup_max_experts_{max_experts}")
    await runtime.send_message(setup_message, org_agent_id)

    expertds=await runtime.send_message(question,org_agent_id)
    await runtime.stop_when_idle()
    domains=expertds.domains[1:-1].split(',')
    expertsIDs=[]
    runtime.start()
    tmpexp=await ExpertAgent.register(
        runtime,
        type="discuss_exp",#之后让他让助手收集整理哪些资料，根据问题和助手提供的总结分析给出反馈
        factory=lambda: ExpertAgent(
            description="An expert in %s"%item,
            system_message=SystemMessage(
                content="You are an experts in {}."
                "Analyse the question and provide the feedback."
            ),
            model_client=client,
            tools=[],
            user_topic_type=""
        )
    )

    
    logger.info("First round: =====get domains======")
    logger.info(f"Domains: {domains}")

    for titem in domains:
        item=titem.strip()
        tmpexp=await ExpertAgent.register(
            runtime,
            type=item.replace(' ','_'),#之后让他让助手收集整理哪些资料，根据问题和助手提供的总结分析给出反馈
            factory=lambda: ExpertAgent(
                description="An expert in %s"%item,
                system_message=SystemMessage(
                    content="You are an experts in {}."
                    "Analyse the question and provide the feedback."
                ),
                model_client=client,
                tools=[],
                user_topic_type=""
            )
        )
        
        await runtime.add_subscription(TypeSubscription(topic_type="first_round",agent_type=tmpexp.type))
        agentid=AgentId(type=item.replace(' ','_'),key='default')
        expertsIDs.append(agentid)
        ### 好像只有经历这个步骤才会固定，这个时候的item才是最终的值，如果没经过这个，所有值都一样，都是最后的item
        ### 只是注册，还没有实例化好像。
        await runtime.send_message(expersdomains(domains=item),agentid)
    await runtime.stop_when_idle()

    queue = asyncio.Queue[firstrounds]()
    async def collect_result(_agent: ClosureContext, message: firstrounds, ctx: MessageContext) -> None:
        await queue.put(message)
    runtime.start()
    CLOSURE_AGENT_TYPE = "collect_result_agent"
    await ClosureAgent.register_closure(
        runtime,
        CLOSURE_AGENT_TYPE,
        collect_result,
        subscriptions=lambda: [TypeSubscription(topic_type='first_round_feedback', agent_type=CLOSURE_AGENT_TYPE)],
    )

    disc=discuss(question=question.question,background=question.background,resolution_criteria=question.resolution_criteria,\
                date_begin=question.date_begin,date_end=question.date_end,urls_in_background=question.urls_in_background,\
                questionall=get_question_prompt(question),disc="",ret='pub')
    await runtime.publish_message(disc,topic_id=TopicId(type='first_round',source='default'))

    await runtime.stop_when_idle()

    res=''
    while not queue.empty():
        tmp=await queue.get()
        res+=tmp.allres+'\n'
        
    runtime.start()
    qanda=QandA(question=question.question,background=question.background,resolution_criteria=question.resolution_criteria,\
                date_begin=question.date_begin,date_end=question.date_end,\
                urls_in_background=question.urls_in_background,questionall=get_question_prompt(question),feedbacks=res)

    
    finals=await runtime.send_message(qanda,org_agent_id)
    finals=finals.ans
    logger.info(f"Final results: {finals}")
    logger.info(f"Token usage:\n{token_counter}")
    logger.info(f"Question resolution: {question.resolution}")
    await runtime.stop_when_idle()
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
    
    

def get_log_filename(args):
    """Generate log filename based on arguments"""
    # dynamic_agent_conversation_
    return f'logs/dynamic_{args.dataset}_r{args.max_rounds}_e{args.max_experts}_t{args.temperature}_s{args.seed}_{current_time}.log'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='多专家预测系统')
    parser.add_argument('--dataset', type=str, default='cset',
                        help='数据集',choices=['cset','gjopen'])
    parser.add_argument('--max_rounds', type=int, default=MAX_DISCUSS_ROUND,
                        help=f'最大讨论轮数，默认为{MAX_DISCUSS_ROUND}')
    parser.add_argument('--max_retries', type=int, default=3,
                        help='执行失败时的最大重试次数, 默认为3')
    parser.add_argument('--max_experts', type=int, default=5,
                        help='最大专家数量，默认为5')
    parser.add_argument('--seed', type=int, default=42,
                        help='LLM随机种子，用于结果复现，默认为42')
    parser.add_argument('--temperature', type=float, default=0.0,
                        help='LLM温度参数，值越低结果越确定，默认为0.0')
    args = parser.parse_args()
        # Update log filename creation
    log_filename = get_log_filename(args)
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

    # 记录环境信息
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
            # exit()
        quest=Question(question=tdata['question'],background=tdata['background'],\
                    resolution_criteria=tdata['resolution_criteria'],\
                        date_begin=tdata['date_begin'],date_end=tdata['date_close'],\
                        urls_in_background=tdata["extracted_urls"],resolution=gres)

        # asyncio.run(main(quest,args))
        retry_count = 0
        max_retries = args.max_retries
        

        # tres=asyncio.run(main(quest, args))
        # pred.append(tres[0])
        # ground.append(tres[1])
        while retry_count <= max_retries:
            try:
                logger.info(f"尝试执行 (第 {retry_count + 1}/{max_retries + 1} 次)")
                tres=asyncio.run(main(quest, args))
                pred.append(tres[0])
                ground.append(tres[1])
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
    logger.info("Finish")