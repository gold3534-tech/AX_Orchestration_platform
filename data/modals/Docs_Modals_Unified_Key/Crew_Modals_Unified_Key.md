## Crew **Modals Unified Key**

| Attribute | Parameters | Description |
| --- | --- | --- |
| **Crew Name** | `crewName` | CrewAI 정식 파라미터 아님, 사용자 UI 표시 및 DB 저장용으로 사용됨, 입력은 문자열만 받음 |
| **Tasks** | `tasks` | CrewAI의 실제 params는 tasks지만, 우리는 Node 기반 독립 엔진으로 `runtime_tasks` 로 처리함.타입은 `Dict[str, Dict[str, Any]]` |
| **Agents** | `agents` | CrewAI의 실제 params는 tasks지만, 우리는 Node 기반 독립 엔진으로 `runtime_agents` 로 처리함. 타입은 `Dict[str, Dict[str, Any]]` |
| **Process Type** | `process` | The process flow (e.g., sequential, hierarchical) the crew follows. Default is `sequential`. |
| **Verbose** | `verbose`  | The verbosity level for logging during execution. Defaults to `False`. |
| **Manager LLM** | `manager_llm` | The language model used by the manager agent in a hierarchical process. **Required when using a hierarchical process.** |
| **Config** *(optional)* | `config` | Optional configuration settings for the crew, in `Json` or `Dict[str, Any]` format. |
| **Global MAX RPM** | `max_rpm` | Maximum requests per minute the crew adheres to during execution. Defaults to `None`. |
| **Memory**  | `memory` | Utilized for storing execution memories (short-term, long-term, entity memory). |
| **Cache**  | `cache` | Specifies whether to use a cache for storing the results of tools’ execution. Defaults to `True`. |
| **Embedder** | `embedder` | Configuration for the embedder to be used by the crew. Mostly used by memory for now. Default is `{"provider": "openai"}`. |
| **Output Log File** | `output_log_file` | Set to True to save logs as logs.txt in the current directory or provide a file path. Logs will be in JSON format if the filename ends in .json, otherwise .txt. Defaults to `None`. |
| **Manager Agent**  | `manager_agent` | `manager` sets a custom agent that will be used as a manager. |
| **Planning**  | `planning` | Adds planning ability to the Crew. When activated before each Crew iteration, all Crew data is sent to an AgentPlanner that will plan the tasks and this plan will be added to each task description. |
| **Planning LLM**  | `planning_llm` | The language model used by the AgentPlanner in a planning process. |
| **Stream**  | `stream` | Enable streaming output to receive real-time updates during crew execution. Returns a `CrewStreamingOutput` object that can be iterated for chunks. Defaults to `False`. |
| **Chat with Crew** | `chat_llm` | The language model used to orchestrate `crewai chat` CLI interactions with the crew. Accepts a model name string or `LLM` instance. Defaults to `None`. |
| **Tracing** | `tracing` | Controls OpenTelemetry tracing for the crew. `True` = always enable, `False` = always disable, `None` = inherit from environment / user settings. Defaults to `None`. |
| **Checkpoint** | `checkpoint` | Enables automatic checkpointing. Pass `True` for sensible defaults, a `CheckpointConfig` for full control, `False` to opt out, or `None` to inherit. See the [Checkpointing](about:blank#checkpointing) section below. Defaults to `None`. |