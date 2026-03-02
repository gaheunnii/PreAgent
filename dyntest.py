import os

from configs.keys import keys

# Set proxy from environment variables if available
http_proxy = keys.get("HTTP_PROXY")
https_proxy = keys.get("HTTPS_PROXY")
if http_proxy:
    os.environ['http_proxy'] = http_proxy
if https_proxy:
    os.environ['https_proxy'] = https_proxy


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

# def get_env_variable(name: str) -> str:
#     value = os.getenv(name)
#     if value is None:
#         raise ValueError(f"Environment variable {name} is not set")
#     return value


# # Create the client with type-checked environment variables
# client = AzureOpenAIChatCompletionClient(
#     azure_deployment=get_env_variable("AZURE_OPENAI_DEPLOYMENT_NAME"),
#     model=get_env_variable("AZURE_OPENAI_MODEL"),
#     api_version=get_env_variable("AZURE_OPENAI_API_VERSION"),
#     azure_endpoint=get_env_variable("AZURE_OPENAI_ENDPOINT"),
#     api_key=get_env_variable("AZURE_OPENAI_API_KEY"),
# )

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging
current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
log_filename = f'logs/dynamic_agent_conversation_{current_time}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'#,
    # handlers=[
    #     logging.FileHandler(log_filename),
    #     logging.StreamHandler()  # This will also print to console
    # ]
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
client=AzureOpenAIChatCompletionClient(
            azure_endpoint=endpoint,  
            model=deployment,
            api_key=subscription_key,  
            api_version="2024-05-01-preview", 
        )

# Get proxy settings from environment variables
http_proxy = keys.get("HTTP_PROXY")
https_proxy = keys.get("HTTPS_PROXY")
proxies = {}
if http_proxy:
    proxies["http"] = http_proxy
if https_proxy:
    proxies["https"] = https_proxy

# class TokenCounter:
#     def __init__(self):
#         self.total_tokens = 0
#         self.total_prompt_tokens = 0
#         self.total_completion_tokens = 0
#         self.call_count = 0
#         self.embedding_count = 0
#         self.embedding_tokens = 0

#     def add_usage(self, usage):
#         self.total_tokens += usage.total_tokens
#         self.total_prompt_tokens += usage.prompt_tokens
#         self.total_completion_tokens += usage.completion_tokens
#         self.call_count += 1

#     def add_embedding_usage(self, usage):
#         self.embedding_count += 1
#         self.embedding_tokens += usage.prompt_tokens

#     def __str__(self):
#         return f"""
# Token Usage Statistics:
# ----------------------
# Total API Calls: {self.call_count}
# Total Tokens: {self.total_tokens}
# Total Prompt Tokens: {self.total_prompt_tokens}
# Total Completion Tokens: {self.total_completion_tokens}
# Average Tokens per Call: {self.total_tokens / self.call_count if self.call_count > 0 else 0:.2f}
# Embedding Token Usage Statistics:
# -------------------------------
# Total API Calls: {self.embedding_count}
# Total Tokens: {self.embedding_tokens}
# Average Tokens per Call: {self.embedding_tokens / self.embedding_count if self.embedding_count > 0 else 0:.2f}
# """

# # Create global token counter
# token_counter = TokenCounter()


def google_search(query: str, num_results: int = 2, max_chars: int = 500) -> list:  # type: ignore[type-arg]
    
    

    api_key = os.getenv("GOOGLE_API_KEY")
    search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

    if not api_key or not search_engine_id:
        raise ValueError("API key or Search Engine ID not found in environment variables")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": search_engine_id, "q": query, "num": num_results}

    response = requests.get(url, params=params, proxies=proxies)  # type: ignore[arg-type]

    if response.status_code != 200:
        # print(response.json())
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
            # print(f"Error fetching {url}: {str(e)}")
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

    @message_handler
    async def handle_question(self,message:Question, ctx: MessageContext)->expersdomains:
        # 生成几个专家，让他们处理问题
        local_task_prompts="""
        Please list the fields of expertise required to solve the aforementioned problem, with a maximum of 5 fields. 
        Generally, the more complex the problem, the broader the scope, and the more fields of expertise are needed.
        Return results in the following format, (Field 1, Feild 2, ...).
        One return example is, "(Differential Geometry, Deep Learning)".
        """
        user_message=UserMessage(content=get_question_prompt(message)+local_task_prompts,source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        # print(llm_result.content)
        domains=llm_result.content[1:-1].split(',')
        for item in domains:
            self.domainexperts.add(item.strip())

        # print('=======org: domain get=======')
        # print(user_message.content)
        # print(llm_result.content)
        logger.info("=======org: domain get=======")
        logger.info(f"User message:\n{user_message.content}")
        logger.info(f"LLM response:\n{llm_result.content}")
        return expersdomains(domains=llm_result.content)
    

    # @message_handler
    # async def save_hist_sum(self,message:QandA,ctx:MessageContext)->None:
    #     llm_local_prompts="""
    #     Question:
    #     {}
        
    #     History minutes:
    #     {}

    #     New feedback:
    #     {}

    #     According to the question, sort out historical minutes and new feedback, and give summary minutes.
    #     """.format(message.questionall, self.hist, message.feedbacks)
    #     user_message=UserMessage(content=llm_local_prompts,source='user')
    #     llm_results=await self._model_client.create(
    #         messages=[self._system_message]+[user_message],
    #         cancellation_token=ctx.cancellation_token
    #     )
    #     self.hist=llm_results.content
    #     tmpres=discuss(question=message.question,background=message.background,resolution_criteria=message.resolution_criteria,\
    #                    date_begin=message.date_begin,date_end=message.date_end,urls_in_background=message.urls_in_background,\
    #                    questionall=message.questionall,disc=llm_results.content,ret='ret')
    #     await self.send_message(tmpres,AgentId('organ_agent','default'))

    @message_handler
    async def handle_response(self,message:QandA,ctx:MessageContext)->finalans:
        self.round+=1
        
        llm_local_prompts="""
        Question:
        {}
        
        History minutes:
        {}

        New feedback:
        {}

        According to the question, sort out historical minutes and new feedback, and give the summary minutes of the combination of the historyical minutes and new feedback.
        """.format(message.questionall, self.hist, message.feedbacks)
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
        
        # print('=======org: discussion round: %d======='%self.round)
        # print(user_message.content)
        # print('\n\n')
        # print(llm_results.content)
        logger.info(f"=======org: discussion round: {self.round}=======")
        logger.info(f"User message:\n{user_message.content}")
        logger.info(f"LLM response:\n{llm_results.content}")
        
        if self.round>MAX_DISCUSS_ROUND:
            local_task_prompts="""
            Consider the questions and the summary of discussion.
            Please give the final result, and return results in the following format, (Yes/No)
            """
        else:
            local_task_prompts="""
            Consider the questions and the summary of discussion.
            If you can confidently make a judgment based on the information you have, then give the final result, otherwise return to the expert field you need to consult.
            If you are confident to make the judgement, return results in the following format, (Yes/No)
            Otherwise, only return the expert field, (Area)
            """
        user_message=UserMessage(content=dismessage.questionall+"\n The following are the summary of discussion, \n"+dismessage.disc+'\n'+local_task_prompts,source='user')
        
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        res=llm_result.content
    
        # print(user_message.content)
        # print('\n\n')
        # print(llm_result.content)
        logger.info(user_message.content)
        logger.info(f"LLM response:\n{llm_result.content}")

        if res=='Yes' or res=='No':            
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
        local_task_prompts="""

        Discussion summary:
        {}

        Considering the discussion summary, what information do you need to retrieve to solve the above question?
        If you need to retrieve the information, briefly describe the information you need to retrieve and return the answer in the following format:
        (the information)
        If you do not need to retrieve the information, return (No)
        """.format(message.disc)
        user_message=UserMessage(content=message.questionall+local_task_prompts,source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        # print('=====exp %s========='%self.domains)
        # print(user_message.content)
        # print('\n\n')
        # print(llm_result.content)
        logger.info(f"=====Expert {self.domains} Response=====")
        logger.info(f"User message:\n{user_message.content}")
        logger.info(f"LLM response:\n{llm_result.content}")

        domain_ref=llm_result.content[1:-1].strip()
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
        local_task_prompts="""
        Please combine the following retrieved summary:
        {}
        Then give your answers to the above questions and provide reasons. 
        Return results in the following format,
        Answer: answer.
        Reasons: reasons.
        """.format(all_summaries)
        user_message=UserMessage(content=get_question_prompt(message)+local_task_prompts,source='user')
        llm_result = await self._model_client.create(
            messages=[self._system_message]+[user_message],
            cancellation_token=ctx.cancellation_token
        )
        token_counter.add_usage(llm_result.usage) 
        firstres=firstrounds(answer='',reason='',\
                             allres="Expert in %s provide the following feedback:\n"%self.domains+llm_result.content,\
                             domains=self.domains)
        # print(firstres)

        # print(user_message.content)
        # print('\n\n')
        # print(llm_result.content)
        logger.info(f"User message:\n{user_message.content}")
        logger.info(f"LLM response:\n{llm_result.content}")

        if message.ret=='pub':
            await self.publish_message(firstres, topic_id=TopicId(type='first_round_feedback',source='default'))
        return firstres

async def main(question:Question)->None:
    runtime = SingleThreadedAgentRuntime()
    await OrganAgent.register(
        runtime,
        type="organ_agent",
        factory=lambda: OrganAgent(
            description="An organizer",
            system_message=SystemMessage(
                content="You are an organizer who organizes experts to make predictions."
                "Analyse the questions and organize experts to solve the question."
                "According to the gathered statements from experts, make the final prediction."
            ),
            model_client=client,
            tools=[],
            user_topic_type="experts"
        ),
    )
    runtime.start()
    # session_id=str(uuid.uuid4())
    org_agent_id=AgentId('organ_agent','default')
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

    # print('first round: =====get domains======')
    # print(domains)
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
        # print(tmpexp.type)
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
        # print(tmp)
        # print(await queue.get())
        res+=tmp.allres+'\n'
        # print('hah===========+\n'+res)
    runtime.start()
    qanda=QandA(question=question.question,background=question.background,resolution_criteria=question.resolution_criteria,\
                date_begin=question.date_begin,date_end=question.date_end,\
                urls_in_background=question.urls_in_background,questionall=get_question_prompt(question),feedbacks=res)

    # print(res)
    # print(qanda)
    # print('final start======================')
    finals=await runtime.send_message(qanda,org_agent_id)
    # print(finals)
    # print(token_counter)
    # print(question.resolution)
    logger.info(f"Final results: {finals}")
    logger.info(f"Token usage:\n{token_counter}")
    logger.info(f"Question resolution: {question.resolution}")
    await runtime.stop_when_idle()


file1='./data/cset/binary.json'
with open(file1,'r') as f:
    tdata=json.load(f)

data=[]
for item in tdata:
    if item['date_resolve_at'] is None:
        continue
    data.append(item)
# print(type(data[0]['date_begin']))
# print(len(data))
# for i in range(3):
#     print(data[i]['date_begin'])
#     print(data[i]['date_close'])
#     print(data[i]['date_resolve_at'])
# for i in range(10):
#     print('============%d=========='%i)
#     print(data[i]['extracted_urls'])
tdata=data[0]
# print('====================Question====================')
# print(tdata['url'])
# print(tdata['question'])
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

asyncio.run(main(quest))

# print('====================Finish====================')
logger.info("Finish")