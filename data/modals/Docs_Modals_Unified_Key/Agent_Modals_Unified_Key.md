## Agent Modals Unified Key

| Unified Key | Parameter | Type | Description |
| --- | --- | --- | --- |
| **Agent Name** | None | `str` | DB에 저장되어 사용자 UI에서 보여지는 이름 |
| **Role** | `role` | `str` | Defines the agent’s function and expertise within the crew. |
| **Goal** | `goal` | `str` | The individual objective that guides the agent’s decision-making. |
| **Backstory** | `backstory` | `str` | Provides context and personality to the agent, enriching interactions. |
| **LLM Config** | `llm` | `Union[str, LLM, Any]` | Language model that powers the agent. Defaults to the model specified in `OPENAI_MODEL_NAME` or “gpt-4”. |
| **Agent Tools** | `tools` | `List[BaseTool]` | Capabilities or functions available to the agent. Defaults to an empty list. |
| **Func-Calling Config** | `function_calling_llm` | `Optional[Any]` | Language model for tool calling, overrides crew’s LLM if specified. |
| **Max Iter** | `max_iter` | `int` | Maximum iterations before the agent must provide its best answer. Default is 20. |
| **Max RPM** | `max_rpm` | `Optional[int]` | Maximum requests per minute to avoid rate limits. |
| **Execution Time** | `max_execution_time` | `Optional[int]` | Maximum time (in seconds) for task execution. |
| **Verbose Logging** | `verbose` | `bool` | Enable detailed execution logs for debugging. Default is False. |
| **Allow Delegation** | `allow_delegation` | `bool` | Allow the agent to delegate tasks to other agents. Default is False. |
| **Cache** | `cache` | `bool` | Enable caching for tool usage. Default is True. |
| **Retry Limit** | `max_retry_limit` | `int` | Maximum number of retries when an error occurs. Default is 2. |
| **Context Window** | `respect_context_window` | `bool` | Keep messages under context window size by summarizing. Default is True. |
| **Multimodal** | `multimodal` | `bool` | Whether the agent supports multimodal capabilities. Default is False. |
| **Inject Date** | `inject_date` | `bool` | Whether to automatically inject the current date into tasks. Default is False. |
| **Date Format** | `date_format` | `str` | Format string for date when inject_date is enabled. Default is “%Y-%m-%d” (ISO format). |
| **Reasoning** | `reasoning` | `bool` | Whether the agent should reflect and create a plan before executing a task. Default is False. |
| **Max Reasoning Attempts** | `max_reasoning_attempts` | `Optional[int]` | Maximum number of reasoning attempts before executing the task. If None, will try until ready. |
| **Embedder** | `embedder` | `Optional[Dict[str, Any]]` | Configuration for the embedder used by the agent. |
| **Knowledge Sources** | `knowledge_sources` | `Optional[List[BaseKnowledgeSource]]` | Knowledge sources available to the agent. |