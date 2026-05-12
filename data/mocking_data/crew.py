from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from .models import InstagramPostOutput, ImageResult
from .tools import scrape_and_summarize_website, search_internet, search_internet_recent


# 콘텐츠 생성 담당 Crew
# IT 리서치 → 카드뉴스 텍스트 + 캡션 작성 → HITL 순으로 순차 실행
@CrewBase
class ContentCrew:
    """Crew responsible for researching IT trends and writing card news content."""

    agents_config = "config/content_agents.yaml"
    tasks_config = "config/content_tasks.yaml"

    # 최신 IT 트렌드 및 뉴스레터 소스를 수집하는 리서치 에이전트
    @agent
    def it_researcher_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["it_researcher_agent"],
            tools=[scrape_and_summarize_website, search_internet_recent],
        )

    # 리서치 결과를 AEO 형식의 카드뉴스 텍스트 + 캡션으로 변환하는 에이전트
    @agent
    def content_creator_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["content_creator_agent"],
            tools=[search_internet],
        )

    # IT 트렌드 수집 태스크
    @task
    def research_task(self) -> Task:
        return Task(config=self.tasks_config["research_task"])

    # 카드뉴스 슬라이드 텍스트 + 캡션 + 해시태그 작성 태스크 (HITL 포함, InstagramPostOutput 구조화 출력)
    @task
    def content_creation_task(self) -> Task:
        return Task(
            config=self.tasks_config["content_creation_task"],
            output_pydantic=InstagramPostOutput,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            tracing=True,  # 추가
            verbose=True,
            checkpoint=True,
        )


# 비주얼 생성 담당 Crew
# 이미지 프롬프트 설계 → 총괄 디렉터 최종 검토 → HITL 순으로 순차 실행
@CrewBase
class VisualCrew:
    """Crew responsible for designing image prompts and final review."""

    agents_config = "config/visual_agents.yaml"
    tasks_config = "config/visual_tasks.yaml"

    # 슬라이드별 이미지 생성 프롬프트를 설계하는 에이전트 (표지 텍스트 오버레이 포함)
    @agent
    def photographer_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["photographer_agent"],
            tools=[],
        )

    # 이미지 프롬프트와 전체 콘텐츠를 브랜드 기준으로 최종 검토하는 에이전트
    @agent
    def creative_director_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["creative_director_agent"],
            tools=[],
        )

    # 각 슬라이드에 맞는 이미지 생성 프롬프트 설계 태스크 (ImageResult로 구조화 출력)
    @task
    def image_prompt_task(self) -> Task:
        return Task(
            config=self.tasks_config["image_prompt_task"],
            output_pydantic=ImageResult,
        )

    # 전체 콘텐츠 최종 검토 및 이미지 프롬프트 확정 태스크 (HITL 포함, ImageResult로 구조화 출력)
    @task
    def final_review_task(self) -> Task:
        return Task(
            config=self.tasks_config["final_review_task"],
            output_pydantic=ImageResult,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            tracing=True,  # 추가
            verbose=True,
        )
