from crewai import Agent, Task, Crew, Process
from api.runtime.tool_loader import load_tool
from crewai.llms.base_llm import BaseLLM

# 1. Validation LLM 생성 (factory.py의 _runtime_llm 로직)
# JSON 파일 내에 llm_config_json 설정이 없기 때문에, 팩토리는 내부적으로 
# 통과용 더미(Mock) LLM인 _ValidationLLM을 생성해서 주입합니다.
class _ValidationLLM(BaseLLM):
    def __init__(self, model: str = "runtime-validation") -> None:
        super().__init__(model=model, provider="openai")
    def call(self, *args, **kwargs):
        return "runtime-validation"
    def supports_function_calling(self) -> bool:
        return False
    def get_context_window_size(self) -> int:
        return 8192

default_llm = _ValidationLLM()


# 2. 도구(Tools) 로드 (factory.py의 _build_task_tools 내 load_tool 호출)
# runtime_tools 정보를 바탕으로 동적 로딩됩니다.
csv_search_tool = load_tool("crewai_tools", "CSVSearchTool", {})
directory_read_tool = load_tool("crewai_tools", "DirectoryReadTool", {})


# 3. 에이전트(Agents) 정의 (factory.py의 _build_agent 로직)
# 🚨 핵심 포인트: Agent 인스턴스를 만들 때 tools를 직접 주입하지 않습니다. 
# 대신 Task를 빌드할 때 모아서 한 번에 Task 객체에 주입합니다.
agent_0ee4 = Agent(
    role="Test",
    goal="Test",
    backstory="Test",
    llm=default_llm  # Payload에 LLM이 없으므로 Default LLM 할당
)

agent_fddf = Agent(
    role="Test2",
    goal="Test2",
    backstory="Test2",
    llm=default_llm
)


# 4. 태스크(Tasks) 정의 (factory.py의 _build_task 로직)
# 🚨 핵심 포인트: _effective_task_tool_keys 함수에 의해, 
# 해당 태스크에 직접 연결된 도구(task_tool_links) 뿐만 아니라, 
# 이 태스크를 담당하는 에이전트에 연결된 도구(agent_tool_links)까지 전부 합쳐서 Task의 tools 배열에 할당합니다.

# Task 1 (ID: 3d4f20fb...)
# 담당 에이전트(agent_0ee4)의 도구: 없음
# 태스크 자체의 도구: crewai.csv_search
task_3d4f = Task(
    name="Test2",
    description="Test2",
    expected_output="Test2",
    agent=agent_0ee4,
    tools=[csv_search_tool] # csv 도구만 할당
)

# Task 2 (ID: 2163501c...)
# 담당 에이전트(agent_fddf)의 도구: crewai.directory_read
# 태스크 자체의 도구: 없음
task_2163 = Task(
    name="test",
    description="test {topic}",
    expected_output="test",
    agent=agent_fddf,
    context=[task_3d4f], # 의존성에 의해 이전 Task 결과 주입
    tools=[directory_read_tool] # 에이전트 도구가 이쪽으로 병합되어 할당됨!
)


# 5. 크루(Crew) 조립 (factory.py의 build_crew 로직)
test_crew = Crew(
    name="Test Crew",
    agents=[agent_0ee4, agent_fddf],
    tasks=[task_3d4f, task_2163] # runtime_crew.task_version_ids 순서대로 정렬됨
)
