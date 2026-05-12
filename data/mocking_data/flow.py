from datetime import date, timedelta

from crewai.flow import Flow, human_feedback, listen, start
from crewai.flow.human_feedback import HumanFeedbackResult
from pydantic import BaseModel

from .crew import ContentCrew, VisualCrew
from .models import InstagramPostOutput, CampaignResult, ImageResult


def _date_inputs() -> dict:
    today = date.today()
    return {
        "current_date": today.isoformat(),
        "date_range_start": (today - timedelta(days=7)).isoformat(),
    }


# Flow 실행 중 단계별로 공유되는 상태 — 입력값과 각 Crew의 결과를 담음
class CampaignState(BaseModel):
    topic: str = ""
    additional_details: str = ""
    card_news: InstagramPostOutput | None = None
    image_descriptions: ImageResult | None = None


class InstagramFlow(Flow[CampaignState]):
    def __init__(self):
        super().__init__(tracing=True)  # 추가
    # [1단계] ContentCrew 실행 후 HITL① — 카드뉴스 텍스트를 사람에게 제시
    # 승인 → "content_approved" / 수정 요청 → "content_needs_revision"
    @start()
    @human_feedback(
        message="카드뉴스 초안을 검토해주세요. 승인하시겠습니까?",
        emit=["content_approved", "content_needs_revision"],
        llm="openai/gpt-4o-mini"
    )
    def generate_content(self) -> str:
        result = ContentCrew().crew().kickoff(
            inputs={
                "topic": self.state.topic,
                "additional_details": self.state.additional_details,
                **_date_inputs(),
            }
        )
        self.state.card_news = result.pydantic
        return str(self.state.card_news)

    # 수정 요청 시 피드백을 additional_details에 추가하여 ContentCrew 재실행 후 다시 HITL①
    @listen("content_needs_revision")
    @human_feedback(
        message="수정된 카드뉴스를 검토해주세요. 승인하시겠습니까?",
        emit=["content_approved", "content_needs_revision"],
        llm="openai/gpt-4o-mini",
    )
    def revise_content(self, result: HumanFeedbackResult) -> str:
        revision_result = ContentCrew().crew().kickoff(
            inputs={
                "topic": self.state.topic,
                "additional_details": f"{self.state.additional_details}\n수정 요청: {result.feedback}",
                **_date_inputs(),
            }
        )
        self.state.card_news = revision_result.pydantic
        return str(self.state.card_news)

    # [2단계] 카드뉴스 승인 후 VisualCrew 실행 + HITL② — 이미지 프롬프트를 사람에게 제시
    # 승인 → "visuals_approved" / 수정 요청 → "visuals_needs_revision"
    @listen("content_approved")
    @human_feedback(
        message="이미지 프롬프트를 검토해주세요. 발행하시겠습니까?",
        emit=["visuals_approved", "visuals_needs_revision"],
        llm="openai/gpt-4o-mini",
    )
    def generate_visuals(self, _result: HumanFeedbackResult) -> str:
        if self.state.card_news:
            cn = self.state.card_news
            body = "\n".join(
                f"{s.subtitle}: {', '.join(s.bullet_points)}" for s in cn.body_slides
            )
            slides_text = "\n".join([cn.title_slide, body, cn.outro_slide])
        else:
            slides_text = ""
        visual_result = VisualCrew().crew().kickoff(
            inputs={
                "topic": self.state.topic,
                "additional_details": self.state.additional_details,
                "card_news_slides": slides_text,
            }
        )
        self.state.image_descriptions = visual_result.pydantic
        return str(self.state.image_descriptions)

    # 수정 요청 시 피드백을 반영해 VisualCrew 재실행 후 다시 HITL②
    @listen("visuals_needs_revision")
    @human_feedback(
        message="수정된 이미지 프롬프트를 검토해주세요. 발행하시겠습니까?",
        emit=["visuals_approved", "visuals_needs_revision"],
        llm="openai/gpt-4o-mini",
    )
    def revise_visuals(self, result: HumanFeedbackResult) -> str:
        if self.state.card_news:
            cn = self.state.card_news
            body = "\n".join(
                f"{s.subtitle}: {', '.join(s.bullet_points)}" for s in cn.body_slides
            )
            slides_text = "\n".join([cn.title_slide, body, cn.outro_slide])
        else:
            slides_text = ""
        revision_result = VisualCrew().crew().kickoff(
            inputs={
                "topic": self.state.topic,
                "additional_details": f"{self.state.additional_details}\n이미지 수정 요청: {result.feedback}",
                "card_news_slides": slides_text,
            }
        )
        self.state.image_descriptions = revision_result.pydantic
        return str(self.state.image_descriptions)

    # 두 Crew의 결과를 CampaignResult로 묶어 반환
    def get_result(self) -> CampaignResult:
        return CampaignResult(
            card_news=self.state.card_news,
            image_descriptions=self.state.image_descriptions,
        )


# 외부(API 등)에서 호출하는 진입점 — topic과 additional_details는 선택 사항
def run_campaign(topic: str = "", additional_details: str = "") -> CampaignResult:
    flow = InstagramFlow()
    flow.kickoff(inputs={"topic": topic, "additional_details": additional_details})
    return flow.get_result()


if __name__ == "__main__":
    # Flow 구조를 시각화한 그래프 파일 생성 (디버깅/문서화용)
    InstagramFlow().plot("flow_graph")
