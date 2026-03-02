class TokenCounter:
        """跟踪模型的token使用情况"""
    def __init__(self):
        self._chat_tokens = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "call_count": 0
        }
        self._embedding_tokens = {
            "total_tokens": 0,
            "call_count": 0
        }
    
    def add_usage(self, usage):
        """添加token使用记录"""
        print(usage)
        self._chat_tokens["total_tokens"] += (usage.completion_tokens+usage.prompt_tokens)
        self._chat_tokens["prompt_tokens"] += usage.prompt_tokens
        self._chat_tokens["completion_tokens"] += usage.completion_tokens
        self._chat_tokens["call_count"] += 1
    
    def add_embedding_usage(self, usage):
        """添加embedding token使用记录"""
        self._embedding_tokens["total_tokens"] += usage.prompt_tokens
        self._embedding_tokens["call_count"] += 1
    
    def __str__(self):
        """返回token使用统计信息的字符串表示"""
        return f"""
Token Usage Statistics:
----------------------
Chat Completions:
  Total API Calls: {self._chat_tokens['call_count']}
  Total Tokens: {self._chat_tokens['total_tokens']}
  Prompt Tokens: {self._chat_tokens['prompt_tokens']}
  Completion Tokens: {self._chat_tokens['completion_tokens']}
  
Embeddings:
  Total API Calls: {self._embedding_tokens['call_count']}
  Total Tokens: {self._embedding_tokens['total_tokens']}
"""

# Create a global instance
token_counter = TokenCounter()