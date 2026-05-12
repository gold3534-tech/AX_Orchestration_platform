from pydantic import BaseModel, Field
from typing import List

class SlideContent(BaseModel):
    subtitle: str = Field(..., description="15자 이내의 짧고 강렬한 소제목")
    # 핵심: 설명(Description)을 없애고, 무조건 리스트(불릿 포인트)로만 받습니다.
    bullet_points: List[str] = Field(..., description="20자 이내의 핵심 포인트 1줄. 명사형 종결")

class InstagramPostOutput(BaseModel):
    title_slide: str = Field(..., description="표지: 20자 이내 질문형 제목")
    body_slides: List[SlideContent] = Field(..., description="본문 슬라이드 2장")
    outro_slide: str = Field(..., description="마무리: 1줄 요약과 CTA")
    caption: str = Field(..., description="인스타그램 캡션. 적절한 이모지와 줄바꿈을 포함하여 가독성 있게 작성.")
    hashtags: List[str] = Field(...) # 기존과 동일


# 이미지 생성 결과 — 각 슬라이드에 대한 이미지 생성 프롬프트
class ImageResult(BaseModel):
    descriptions: list[str]


# Flow 진입점 입력값 — 카테고리 힌트(선택)와 추가 컨텍스트(선택)
# topic이 비어 있으면 IT 리서처가 자율적으로 최신 트렌드를 선정함
class CampaignInputs(BaseModel):
    topic: str = ""
    additional_details: str = ""


# Flow 최종 반환값 — 카드뉴스 텍스트 + 이미지 설명을 묶어서 반환
class CampaignResult(BaseModel):
    card_news: InstagramPostOutput
    image_descriptions: ImageResult
