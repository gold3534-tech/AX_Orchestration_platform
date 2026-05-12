## Task Attributes

| Attribute                              | Parameters              | Type                        | Description                                                                                                     |
| :------------------------------------- | :---------------------- | :-------------------------- | :-------------------------------------------------------------------------------------------------------------- |
| **Description**                        | `description`           | `str`                       | A clear, concise statement of what the task entails.                                                            |
| **Expected Output**                    | `expected_output`       | `str`                       | A detailed description of what the task's completion looks like.                                                |
| **Name** *(optional)*                  | `name`                  | `Optional[str]`             | A name identifier for the task.                                                                                 |
| **Agent** *(optional)*                 | `agent`                 | `Optional[BaseAgent]`       | The agent responsible for executing the task.                                                                   |
| **Tools** *(optional)*                 | `tools`                 | `List[BaseTool]`            | The tools/resources the agent is limited to use for this task.                                                  |
| **Context** *(optional)*               | `context`               | `Optional[List["Task"]]`    | Other tasks whose outputs will be used as context for this task.                                                |
| **Async Execution** *(optional)*       | `async_execution`       | `Optional[bool]`            | Whether the task should be executed asynchronously. Defaults to False.                                          |
| **Human Input** *(optional)*           | `human_input`           | `Optional[bool]`            | Whether the task should have a human review the final answer of the agent. Defaults to False.                   |
| **Markdown** *(optional)*              | `markdown`              | `Optional[bool]`            | Whether the task should instruct the agent to return the final answer formatted in Markdown. Defaults to False. |
| **Config** *(optional)*                | `config`                | `Optional[Dict[str, Any]]`  | Task-specific configuration parameters.                                                                         |
| **Output File** *(optional)*           | `output_file`           | `Optional[str]`             | File path for storing the task output.                                                                          |
| **Create Directory** *(optional)*      | `create_directory`      | `Optional[bool]`            | Whether to create the directory for output\_file if it doesn't exist. Defaults to True.                         |
| **Output JSON** *(optional)*           | `output_json`           | `Optional[Type[BaseModel]]` | A Pydantic model to structure the JSON output.                                                                  |
| **Output Pydantic** *(optional)*       | `output_pydantic`       | `Optional[Type[BaseModel]]` | A Pydantic model for task output.                                                                               |
| **Callback** *(optional)*              | `callback`              | `Optional[Any]`             | Function/object to be executed after task completion.                                                           |
| **Guardrail** *(optional)*             | `guardrail`             | `Optional[Callable]`        | Function to validate task output before proceeding to next task.                                                |
| **Guardrails** *(optional)*            | `guardrails`            | `Optional[List[Callable]]`  | List of guardrails to validate task output before proceeding to next task.                                      |
| **Guardrail Max Retries** *(optional)* | `guardrail_max_retries` | `Optional[int]`             | Maximum number of retries when guardrail validation fails. Defaults to 3.                                       |

<Note type="warning" title="Deprecated: max_retries">
  The task attribute `max_retries` is deprecated and will be removed in v1.0.0.
  Use `guardrail_max_retries` instead to control retry attempts when a guardrail
  fails.
</Note>