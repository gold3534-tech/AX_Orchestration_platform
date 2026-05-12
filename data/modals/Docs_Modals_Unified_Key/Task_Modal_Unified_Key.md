## Task Unified Key

| Unified Key | Parameters | Type | Description |
| --- | --- | --- | --- |
| **Description** | `description` | `str` | A clear, concise statement of what the task entails. |
| **Expected Output** | `expected_output` | `str` | A detailed description of what the task’s completion looks like. |
| **Name** | `name` | `Optional[str]` | A name identifier for the task. |
| **Agent** | `agent` | `Optional[BaseAgent]` | The agent responsible for executing the task. |
| **Tools** | `tools` | `List[BaseTool]` | The tools/resources the agent is limited to use for this task. |
| **CrewAI Context** | `context` | `Optional[List["Task"]]` | Other tasks whose outputs will be used as context for this task. |
| **Async Execution** | `async_execution` | `Optional[bool]` | Whether the task should be executed asynchronously. Defaults to False. |
| **Human Input** | `human_input` | `Optional[bool]` | Whether the task should have a human review the final answer of the agent. Defaults to False. |
| **Markdown Output** | `markdown` | `Optional[bool]` | Whether the task should instruct the agent to return the final answer formatted in Markdown. Defaults to False. |
| **Output File Path** | `output_file` | `Optional[str]` | File path for storing the task output. |
| **Create Directory** | `create_directory` | `Optional[bool]` | Whether to create the directory for output_file if it doesn’t exist. Defaults to True. |
| **Output JSON** | `output_json` | `Optional[Type[BaseModel]]` | A Pydantic model to structure the JSON output. |
| **Output Pydantic** | `output_pydantic` | `Optional[Type[BaseModel]]` | A Pydantic model for task output. |
| **Guardrails** | `guardrail` | `str` |  **Guardrails 설정은 보안 문제로 오직 문자열만 받아 처리합니다.** |