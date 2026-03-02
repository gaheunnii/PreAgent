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
# from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_ext.models.replay import ReplayChatCompletionClient

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

async def google_search(query: str, num_results: int = 2, max_chars: int = 500) -> list:  # type: ignore[type-arg]
    
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
    retrieved_info:str
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

def get_agent_reasoing_prompt(retrieved_info):
    return f"""
    Please analyze the following retrieved information:
    {retrieved_info}
    
    Based on this information and your domain expertise, provide:
    1. Your assessment of how this affects the prediction
    2. Your reasoning process, highlighting key factors
    3. Your confidence level in this assessment
    
    Return your analysis in the following format:
    Answer: [Yes/No].
    Reasons: [Your detailed reasoning]
    """

def get_agent_decision_prompt(question, hist):
    return f"""
    Question:
    {question}
    
    Reasoning agents' analysis:
    {hist}

    Return your analysis in the following format:
    Answer: [Yes/No].
    Reasons: [Your detailed reasoning: Summary and evaluation of each key argument]

    """

class SearchAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        system_message: SystemMessage,
        model_client: AzureOpenAIChatCompletionClient,
        tools: list[Tool],
        search_function: callable  # This will be our google_search function
    ) -> None:
        super().__init__(description)
        self._system_message = system_message
        self._model_client = model_client
        self._tools = dict([(tool.name, tool) for tool in tools])
        self._tool_schema = [tool.schema for tool in tools]
        self._search_function = search_function

    @message_handler
    async def handle_search_request(self, message: Question, ctx: MessageContext) -> str:
        """Handle a search request by first determining what to search for, then processing results"""
        
        # Step 1: Determine what information needs to be searched
        search_prompt = """
        Given the following question:
        {question}
        
        What specific information would be most helpful to search for to answer this question?
        Please list the key search terms or queries in the following format:
        [search term 1, search term 2, ...]
        """.format(question=message.question)

        user_message = UserMessage(content=search_prompt, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message] + [user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)
        
        logger.info(f"=====Search Agent Response=====")
        logger.info(f"Search terms determination - User message:\n{user_message.content}")
        logger.info(f"Search terms determination - LLM response:\n{llm_result.content}")

        # Extract search terms from the response
        search_terms = self._extract_search_terms(llm_result.content)
        
        # ranked_articles=await ranking.retrieve_summarize_and_rank_articles(
        #         question=message.question,
        #         background_info=message.background,
        #         resolution_criteria=message.resolution_criteria,
        #         date_range=(message.date_begin,message.date_end),
        #         domain_ref=search_terms,
        #         urls=message.urls_in_background,
        #         return_intermediates=False)

        # Step 2: Perform the actual searches
        search_results_list = []
        for term in search_terms:
            results = await self._search_function(term, num_results=5)  # TODO: add start-end date
            search_results_list.extend(results)
        
        # Step 3: Rank the articles by relevance
        ranking_prompt = """
        Please rank the following search results by their relevance to answering this question:
        {question}
        
        The results to rank are:
        {results}
        
        Return the ranked list in the same format, with the most relevant first.
        """.format(question=message.question, results="\n".join([r['title'] + ": " + r['snippet'] for r in search_results_list]))

        # FIXME: Here is the simplest method to rank the results, can align to the NIPS paper.
        user_message = UserMessage(content=ranking_prompt, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message] + [user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)
        
        ranked_results = self._parse_ranked_results(llm_result.content, search_results_list)
        
        # Step 4: Summarize the top results
        # logger.info(ranked_results[0].keys())
        # logger.info(ranked_results[1].keys())
        # logger.info(ranked_results[2].keys())
        # dict_keys(['title', 'link', 'snippet', 'body'])
        summary_prompt = """
        Please summarize the key information from these search results that helps answer the question:
        {question}
        
        The top results are:
        {top_results}
        
        Provide a concise summary focusing on the most relevant information.
        """.format(
            question=message.question,
            top_results="\n".join([f"{r['title']}\n{r['snippet']}\n{r['link']}" for r in ranked_results[:3]])
        )

        # FIXME: Here is the simplest method to summarize the results, can align to the NIPS paper.
        user_message = UserMessage(content=summary_prompt, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message] + [user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)

        
        # Step 5: Prepare the final response
        # Prepare the final response
        final_response = llm_result.content
        
        # if message.ret == 'pub':
        #     await self.publish_message(final_response, topic_id=TopicId(type='search_results', source='default'))
        
        return final_response

    def _extract_search_terms(self, content: str) -> list[str]:
        """Extract search terms from LLM response"""
        content = content.strip()
        if content.startswith('[') and content.endswith(']'):
            terms = content[1:-1].split(',')
        elif content.startswith('(') and content.endswith(')'):
            terms = content[1:-1].split(',')
        else:
            # Fallback - try to find terms in brackets
            if '[' in content and ']' in content:
                terms_str = content.split('[')[1].split(']')[0]
                terms = terms_str.split(',')
            else:
                terms = [content]  # Use the whole response as a single term
        
        return [term.strip() for term in terms if term.strip()]

    def _parse_ranked_results(self, ranking_response: str, original_results: list) -> list:
        """Parse the LLM's ranking response and reorder the original results"""
        # This is a simplified approach - you might need a more sophisticated matching
        ranked_titles = [line.strip() for line in ranking_response.split('\n') if line.strip()]
        
        # Create a mapping of title to result
        title_to_result = {result['title']: result for result in original_results}
        
        # Reorder based on the ranking
        ranked_results = []
        for title in ranked_titles:
            if title in title_to_result:
                ranked_results.append(title_to_result[title])
        
        # Add any remaining results that weren't explicitly ranked
        for result in original_results:
            if result['title'] not in ranked_titles and result not in ranked_results:
                ranked_results.append(result)
                
        return ranked_results

class ReasoningAgent(RoutedAgent):
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
    async def handle_question(self, message:discuss, ctx: MessageContext)->firstrounds:

        local_task_prompts = get_agent_reasoing_prompt(message.retrieved_info)
        user_message=UserMessage(content=get_question_prompt(message) + local_task_prompts, source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        firstres=firstrounds(answer='',reason='',\
                             allres="Reasoning Agent provides the following analysis:\n" + llm_result.content,\
                             domains='test just test')
        
        logger.info(f"User message:\n{user_message.content}")
        logger.info(f"LLM response:\n{llm_result.content}")

        if message.ret=='pub':
            await self.publish_message(firstres, topic_id=TopicId(type='first_round_feedback',source='default'))

        return firstres

class DecisionAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        system_message: SystemMessage,
        model_client: AzureOpenAIChatCompletionClient,
        tools: list[Tool],
        user_topic_type: str,
        decision_threshold: float = 0.7  # Confidence threshold for final decisions
    ) -> None:
        """
        A specialized agent for making final decisions by synthesizing expert inputs.
        
        Args:
            decision_threshold: Minimum consensus score (0.0-1.0) required for automatic decision
        """
        super().__init__(description)
        # Core components
        self._system_message = system_message
        self._model_client = model_client
        self._tools = {tool.name: tool for tool in tools}
        self._tool_schemas = [tool.schema for tool in tools]
        self.user_topic_type = user_topic_type  # Subscription topic for receiving questions

    @message_handler
    async def handle_responses(self, message: QandA, ctx: MessageContext) -> finalans:
        """
        Primary decision-making endpoint.
        Processes aggregated expert feedback and renders final verdict.
        """
        # 1. Format decision prompt with live data
        decision_prompt = get_agent_decision_prompt(
            question=message.question,
            hist=message.feedbacks
        )
        
        # 2. Query LLM for decision
        llm_result = await self._model_client.create(
            messages=[
                self._system_message,
                UserMessage(content=decision_prompt, source='user')
            ],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage)
        
        # 3. Parse and log decision
        decision = self._parse_decision(llm_result.content)
        
        logger.info(f"Decision made: {decision}")
        return finalans(ans=decision)

    def _parse_decision(self, raw_response: str) -> str:
        """
        Extracts structured decision from LLM's text response.
        
        Returns:
            "YES"/"NO" for clear decisions, "UNCERTAIN" otherwise
        """
        if "yes" in raw_response.lower():
            return "yes"
        elif "no" in raw_response.lower():
            return "no"
        else:
            return "uncertain"


async def main(question:Question, args=None)->None:

    global MAX_DISCUSS_ROUND

    if args and args.max_rounds:
        MAX_DISCUSS_ROUND = args.max_rounds

    runtime = SingleThreadedAgentRuntime()
    # Step 1: create a search agent and get the information of this question.
    search_agent = await SearchAgent.register(
        runtime,
        type="search_agent",
        factory=lambda: SearchAgent(
            description="A search agent",
            system_message=SystemMessage(
                content="""You are a skilled searcher and information seeker."""
            ),
            model_client=client,
            tools=[],
            search_function=google_search
        ),
    )
    runtime.start()
    search_agent_id = AgentId(type=search_agent.type, key="default")
    retrieved_info = await runtime.send_message(question, search_agent_id)
    await runtime.stop_when_idle()
    print('Debugging 2')

    # Step 2: create x reasoing agents and get their analysis of the question.
    agent_prompts = [
        'You are a bold and risk-taking analyst.',
        'You are an eternal optimist.',
        'You are a cautious and pragmatic thinker.'
    ]
    reasoning_agent_ids = []

    runtime.start()
    for i in range(3):
        agent = await ReasoningAgent.register(
            runtime,
            type=f"reasoning_agent_{i+1}",  # 类型唯一标识
            factory=lambda prompt=agent_prompts[i]: ReasoningAgent(
                description=f"Reasoning Agent #{i+1}",
                system_message=SystemMessage(content=prompt),
                model_client=client,
                tools=[],
                user_topic_type=""
            )
        )
        
        await runtime.add_subscription(
            TypeSubscription(topic_type="first_round", agent_type=agent.type)
        )
        
        reasoning_agent_ids.append(AgentId(type=agent.type, key="default"))

    # Step 3: create an decision agent and get the final decision.
    decision_agent = await DecisionAgent.register(
        runtime,
        type="decision_agent",
        factory=lambda: DecisionAgent(
            description="A decision agent",
            system_message=SystemMessage(
                content="""You are the final decision-maker. Your sole task is to:
                1. Comprehensively analyze all provided inputs
                2. Generate complete reasoning process
                3. Deliver unambiguous yes/no conclusion
                """
            ),
            model_client=client,
            tools=[],
            user_topic_type="",
        )
    )

    decision_agent_id = AgentId(type=decision_agent.type, key="default")

    queue = asyncio.Queue[firstrounds]()
    async def collect_result(_agent: ClosureContext, message: firstrounds, ctx: MessageContext) -> None:
        await queue.put(message)

    CLOSURE_AGENT_TYPE = "collect_result_agent"
    await ClosureAgent.register_closure(
        runtime,
        CLOSURE_AGENT_TYPE,
        collect_result,
        subscriptions=lambda: [TypeSubscription(topic_type='first_round_feedback', agent_type=CLOSURE_AGENT_TYPE)],
    )

    disc = discuss(question=question.question, background=question.background, resolution_criteria=question.resolution_criteria,\
                date_begin=question.date_begin, date_end=question.date_end, urls_in_background=question.urls_in_background,\
                questionall=get_question_prompt(question), retrieved_info=retrieved_info, disc="", ret='pub')
    await runtime.publish_message(disc, topic_id=TopicId(type='first_round',source='default'))

    await runtime.stop_when_idle()

    res = ''
    while not queue.empty():
        tmp = await queue.get()
        res += tmp.allres+'\n'
        
    runtime.start()
    qanda = QandA(question=question.question, background=question.background, resolution_criteria=question.resolution_criteria,\
                date_begin=question.date_begin, date_end=question.date_end,\
                urls_in_background=question.urls_in_background, questionall=get_question_prompt(question), feedbacks=res)
  
    finals = await runtime.send_message(qanda, decision_agent_id)
    finals = finals.ans

    logger.info(f"Final results: {finals}")
    logger.info(f"Token usage:\n{token_counter}")
    logger.info(f"Question resolution: {question.resolution}")

    if ('no' in finals.lower() and 'no' in question.resolution.lower()):
        return [0,0]
    elif ('yes' in finals.lower() and 'yes' in question.resolution.lower()):
        return [1,1]
    elif ('yes' in finals.lower() and 'no' in question.resolution.lower()):
        return [1,0]
    else:   
        return [0,1]
    

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

    # client = OllamaChatCompletionClient(
    #     model="qwen2.5:32b",
    #     options={
    #         "seed": args.seed if hasattr(args, 'seed') else 42,
    #         "temperature": args.temperature if hasattr(args, 'temperature') else 0.0
    #     }
    # )

    # chat_completions = [
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    #     "Hello, how can I assist you today?",
    #     "I'm happy to help with any questions you have.",
    #     "Is there anything else I can assist you with?",
    # ]
    # client = ReplayChatCompletionClient(chat_completions)

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
        tres=asyncio.run(main(quest, args))
        # while retry_count <= max_retries:
        #     try:
        #         logger.info(f"尝试执行 (第 {retry_count + 1}/{max_retries + 1} 次)")
        #         tres=asyncio.run(main(quest, args))
        #         pred.append(tres[0])
        #         ground.append(tres[1])
        #         logger.info("执行成功")
        #         break
        #     except Exception as e:
        #         retry_count += 1
        #         logger.error(f"执行失败: {str(e)}")
                
        #         if retry_count <= max_retries:
        #             logger.info(f"将在 5 秒后重试 ({retry_count}/{max_retries})...")
        #             time.sleep(5)
        #         else:
        #             logger.error(f"已达到最大重试次数 ({max_retries})，程序终止")
        #             break
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