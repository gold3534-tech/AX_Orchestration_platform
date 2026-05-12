from __future__ import annotations

import pytest

from api.tools.coupang_product_scraper_tool import (
    AXCoupangProductScraperTool,
    GeminiImageJudgeClient,
    _akamai_blocked,
    _compact_metadata,
    _extract_image_candidates,
    _fetch_image_bytes,
    _require_coupang_url,
)

try:
    from firecrawl.v2.types import Document as FirecrawlDocument
    from firecrawl.v2.types import DocumentMetadata as FirecrawlDocumentMetadata
except ImportError:  # pragma: no cover - exercised only without optional firecrawl package
    FirecrawlDocument = None
    FirecrawlDocumentMetadata = None


class FakeFirecrawlDocumentMetadata:
    def __init__(
        self,
        *,
        og_title: str | None = None,
        og_description: str | None = None,
        og_image: str | None = None,
        title: str | None = None,
        description: str | None = None,
    ):
        self.og_title = og_title
        self.og_description = og_description
        self.og_image = og_image
        self.title = title
        self.description = description

    def model_dump(self, *, exclude_none: bool = False):
        data = {
            "og_title": self.og_title,
            "og_description": self.og_description,
            "og_image": self.og_image,
            "title": self.title,
            "description": self.description,
        }
        if exclude_none:
            return {key: value for key, value in data.items() if value is not None}
        return data


class FakeFirecrawlDocument:
    def __init__(self, *, markdown: str, html: str, metadata):
        self.markdown = markdown
        self.html = html
        self.metadata = metadata


def _firecrawl_document(*, markdown: str = "", html: str = "", metadata):
    if FirecrawlDocument is not None and FirecrawlDocumentMetadata is not None:
        return FirecrawlDocument(
            markdown=markdown,
            html=html,
            metadata=FirecrawlDocumentMetadata(**metadata),
        )
    return FakeFirecrawlDocument(
        markdown=markdown,
        html=html,
        metadata=FakeFirecrawlDocumentMetadata(**metadata),
    )


def test_coupang_url_validation_accepts_coupang_product_url():
    assert (
        _require_coupang_url(" https://www.coupang.com/vp/products/7946666048?itemId=1 ")
        == "https://www.coupang.com/vp/products/7946666048?itemId=1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://example.com/vp/products/1",
        "not-a-url",
    ],
)
def test_coupang_url_validation_rejects_invalid_or_non_coupang_urls(url):
    with pytest.raises(ValueError, match="Coupang URL"):
        _require_coupang_url(url)


def test_akamai_detection_reads_markdown_html_and_metadata():
    assert _akamai_blocked(
        {
            "markdown": "Powered and protected by\n![Akamai](https://akamai.com/logo.svg)",
            "html": "",
            "metadata": {},
        }
    )
    assert _akamai_blocked({"markdown": "", "html": "<img src='akamai-logo1.svg'>", "metadata": {}})
    assert not _akamai_blocked({"markdown": "", "html": "", "metadata": {"title": "Akamai"}})
    assert not _akamai_blocked(
        {
            "markdown": "필수 표기 정보\n![](https://thumbnail.coupangcdn.com/image.jpg)",
            "html": "",
            "metadata": {"title": "페스룸 상품"},
        }
    )


def test_akamai_detection_handles_firecrawl_document_metadata_object():
    document = _firecrawl_document(
        markdown="필수 표기 정보\n상품 상세",
        html="",
        metadata={
            "og_title": "페스룸 상품",
            "og_description": "강아지용 상품 상세 설명",
            "og_image": "https://thumbnail.coupangcdn.com/product.jpg",
        },
    )

    assert not _akamai_blocked(document)


def test_compact_metadata_prefers_firecrawl_metadata_fields():
    title, description, metadata_image = _compact_metadata(
        {
            "metadata": {
                "ogTitle": "OG title",
                "title": "Plain title",
                "ogDescription": "OG description",
                "description": "Plain description",
                "ogImage": "http://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/product.jpg",
            }
        }
    )

    assert title == "OG title"
    assert description == "OG description"
    assert metadata_image == "https://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/product.jpg"


def test_compact_metadata_reads_firecrawl_snake_case_metadata_object():
    document = _firecrawl_document(
        metadata={
            "og_title": "Snake OG title",
            "title": "Plain title",
            "og_description": "Snake OG description",
            "description": "Plain description",
            "og_image": "http://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/product.jpg",
        },
    )

    title, description, metadata_image = _compact_metadata(document)

    assert title == "Snake OG title"
    assert description == "Snake OG description"
    assert metadata_image == "https://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/product.jpg"


def test_extract_image_candidates_uses_images_after_required_info_anchor():
    markdown = """
![](https://thumbnail.coupangcdn.com/before.jpg)

필수 표기 정보

|     |     |
| --- | --- |
| 품명 및 모델명 | 상품 |

![](https://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/retail/images/first.jpg)
![second](http://image1.coupangcdn.com/image/vendor_inventory/second.png)
![](https://image1.coupangcdn.com/image/vendor_inventory/third.webp)
![](https://image1.coupangcdn.com/image/vendor_inventory/fourth.jpg)
"""

    candidates = _extract_image_candidates(markdown)

    assert [candidate.url for candidate in candidates] == [
        "https://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/retail/images/first.jpg",
        "https://image1.coupangcdn.com/image/vendor_inventory/second.png",
        "https://image1.coupangcdn.com/image/vendor_inventory/third.webp",
    ]


def test_extract_image_candidates_excludes_recommendation_section_and_bad_assets():
    markdown = """
필수 표기 정보

![](https://www.akamai.com/site/ko/images/logo/akamai-logo1.svg)
![](data:image/png;base64,abc)
![](https://image1.coupangcdn.com/video/detail.mp4)
![](https://example.com/ad.jpg)
![](https://image1.coupangcdn.com/image/vendor_inventory/detail.jpeg)

## 다른 고객이 함께 본 상품

![](https://thumbnail.coupangcdn.com/thumbnails/remote/recommendation.jpg)
"""

    candidates = _extract_image_candidates(markdown)

    assert [candidate.url for candidate in candidates] == [
        "https://image1.coupangcdn.com/image/vendor_inventory/detail.jpeg"
    ]


def test_extract_image_candidates_returns_empty_without_required_info_anchor():
    markdown = "![](https://thumbnail.coupangcdn.com/product.jpg)"

    assert _extract_image_candidates(markdown) == []


def test_extract_image_candidates_parses_markdown_titles_and_angle_destinations():
    markdown = """
필수 표기 정보

![](https://thumbnail.coupangcdn.com/image/detail.jpg "title")
![](<https://thumbnail.coupangcdn.com/image/detail.png>)
"""

    candidates = _extract_image_candidates(markdown)

    assert [candidate.url for candidate in candidates] == [
        "https://thumbnail.coupangcdn.com/image/detail.jpg",
        "https://thumbnail.coupangcdn.com/image/detail.png",
    ]


def test_extract_image_candidates_keeps_balanced_parentheses_in_urls():
    markdown = """
필수 표기 정보

![](https://thumbnail.coupangcdn.com/image/detail(1).jpg)
"""

    candidates = _extract_image_candidates(markdown)

    assert [candidate.url for candidate in candidates] == [
        "https://thumbnail.coupangcdn.com/image/detail(1).jpg"
    ]


def test_extract_image_candidates_only_cuts_on_recommendation_headings_or_standalone_lines():
    markdown = """
필수 표기 정보

이 문장은 관련 상품 안내가 아니라 상세 설명입니다.
![](https://thumbnail.coupangcdn.com/image/detail.jpg)

## 관련 상품

![](https://thumbnail.coupangcdn.com/image/recommendation.jpg)
"""

    candidates = _extract_image_candidates(markdown)

    assert [candidate.url for candidate in candidates] == [
        "https://thumbnail.coupangcdn.com/image/detail.jpg"
    ]


def test_extract_image_candidate_position_is_absolute_url_position():
    markdown = """
![](https://thumbnail.coupangcdn.com/before.jpg)

필수 표기 정보

![](https://thumbnail.coupangcdn.com/image/detail.jpg)
"""

    candidates = _extract_image_candidates(markdown)

    assert candidates[0].position == markdown.index(
        "https://thumbnail.coupangcdn.com/image/detail.jpg"
    )


class FakeFirecrawlClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def scrape(self, url: str):
        self.urls.append(url)
        if not self.responses:
            raise AssertionError("unexpected Firecrawl scrape call")
        return self.responses.pop(0)


class FakeJudgeClient:
    def __init__(self, selected_index=1):
        self.selected_index = selected_index
        self.calls = []

    def select_image_index(self, *, image_urls: list[str], title: str, description: str) -> int:
        self.calls.append(
            {"image_urls": image_urls, "title": title, "description": description}
        )
        return self.selected_index


def _document(markdown: str, *, image: str = ""):
    metadata = {
        "ogTitle": "페스룸 상품",
        "ogDescription": "강아지용 상품 상세 설명",
    }
    if image:
        metadata["ogImage"] = image
    return {"markdown": markdown, "html": "", "metadata": metadata}


def _document_with_metadata(markdown: str, metadata: dict[str, str]):
    return {"markdown": markdown, "html": "", "metadata": metadata}


def test_tool_returns_single_candidate_without_judge_call():
    firecrawl = FakeFirecrawlClient(
        [
            _document(
                """
필수 표기 정보

![](https://image1.coupangcdn.com/image/vendor_inventory/detail.jpg)
"""
            )
        ]
    )
    judge = FakeJudgeClient(selected_index=1)
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=judge,
    )

    result = tool._run(url="https://www.coupang.com/vp/products/1")

    assert result == {
        "og_title": "페스룸 상품",
        "og_image": "https://image1.coupangcdn.com/image/vendor_inventory/detail.jpg",
        "og_description": "강아지용 상품 상세 설명",
    }
    assert firecrawl.urls == ["https://www.coupang.com/vp/products/1"]
    assert judge.calls == []


def test_tool_uses_judge_selected_index_for_multiple_candidates():
    firecrawl = FakeFirecrawlClient(
        [
            _document(
                """
필수 표기 정보

![](https://thumbnail.coupangcdn.com/first.jpg)
![](https://thumbnail.coupangcdn.com/second.jpg)
![](https://thumbnail.coupangcdn.com/third.jpg)
"""
            )
        ]
    )
    judge = FakeJudgeClient(selected_index=2)
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=judge,
    )

    result = tool._run(url="https://www.coupang.com/vp/products/1")

    assert result["og_image"] == "https://thumbnail.coupangcdn.com/second.jpg"
    assert judge.calls == [
        {
            "image_urls": [
                "https://thumbnail.coupangcdn.com/first.jpg",
                "https://thumbnail.coupangcdn.com/second.jpg",
                "https://thumbnail.coupangcdn.com/third.jpg",
            ],
            "title": "페스룸 상품",
            "description": "강아지용 상품 상세 설명",
        }
    ]


def test_tool_falls_back_to_first_candidate_for_invalid_judge_index():
    firecrawl = FakeFirecrawlClient(
        [
            _document(
                """
필수 표기 정보

![](https://thumbnail.coupangcdn.com/first.jpg)
![](https://thumbnail.coupangcdn.com/second.jpg)
"""
            )
        ]
    )
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=FakeJudgeClient(selected_index=99),
    )

    result = tool._run(url="https://www.coupang.com/vp/products/1")

    assert result["og_image"] == "https://thumbnail.coupangcdn.com/first.jpg"


def test_tool_retries_once_on_akamai_then_succeeds():
    firecrawl = FakeFirecrawlClient(
        [
            {"markdown": "Powered and protected by Akamai", "html": "", "metadata": {}},
            _document(
                """
필수 표기 정보

![](https://image1.coupangcdn.com/image/vendor_inventory/detail.jpg)
"""
            ),
        ]
    )
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=FakeJudgeClient(),
    )

    result = tool._run(url="https://www.coupang.com/vp/products/1")

    assert result["og_image"] == "https://image1.coupangcdn.com/image/vendor_inventory/detail.jpg"
    assert firecrawl.urls == [
        "https://www.coupang.com/vp/products/1",
        "https://www.coupang.com/vp/products/1",
    ]


def test_tool_fails_when_akamai_retry_is_also_blocked():
    firecrawl = FakeFirecrawlClient(
        [
            {"markdown": "Powered and protected by Akamai", "html": "", "metadata": {}},
            {"markdown": "![Akamai](https://akamai.com/akamai-logo1.svg)", "html": "", "metadata": {}},
        ]
    )
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=FakeJudgeClient(),
    )

    with pytest.raises(ValueError, match="Akamai"):
        tool._run(url="https://www.coupang.com/vp/products/1")


def test_tool_falls_back_to_metadata_image_when_no_detail_candidate_exists():
    firecrawl = FakeFirecrawlClient(
        [
            _document(
                "필수 표기 정보\n상품 표기 테이블만 있음",
                image="https://thumbnail.coupangcdn.com/fallback.jpg",
            )
        ]
    )
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=FakeJudgeClient(),
    )

    result = tool._run(url="https://www.coupang.com/vp/products/1")

    assert result["og_image"] == "https://thumbnail.coupangcdn.com/fallback.jpg"


def test_tool_output_stays_compact():
    firecrawl = FakeFirecrawlClient(
        [
            _document(
                """
필수 표기 정보

![](https://image1.coupangcdn.com/image/vendor_inventory/detail.jpg)
"""
            )
        ]
    )
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=FakeJudgeClient(),
    )

    result = tool._run(url="https://www.coupang.com/vp/products/1")

    assert set(result) == {"og_title", "og_image", "og_description"}


def test_tool_requires_title_metadata():
    firecrawl = FakeFirecrawlClient(
        [
            _document_with_metadata(
                """
필수 표기 정보

![](https://image1.coupangcdn.com/image/vendor_inventory/detail.jpg)
""",
                {"ogDescription": "강아지용 상품 상세 설명"},
            )
        ]
    )
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=FakeJudgeClient(),
    )

    with pytest.raises(ValueError, match="og_title"):
        tool._run(url="https://www.coupang.com/vp/products/1")


def test_tool_requires_description_metadata():
    firecrawl = FakeFirecrawlClient(
        [
            _document_with_metadata(
                """
필수 표기 정보

![](https://image1.coupangcdn.com/image/vendor_inventory/detail.jpg)
""",
                {"ogTitle": "페스룸 상품"},
            )
        ]
    )
    tool = AXCoupangProductScraperTool(
        firecrawl_client=firecrawl,
        judge_client=FakeJudgeClient(),
    )

    with pytest.raises(ValueError, match="og_description"):
        tool._run(url="https://www.coupang.com/vp/products/1")


class FakeGenAIModels:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def generate_content(self, *, model: str, contents):
        self.calls.append({"model": model, "contents": contents})
        return type("FakeResponse", (), {"text": self.text})()


class FakeGenAIClient:
    def __init__(self, text: str):
        self.models = FakeGenAIModels(text)


def test_gemini_judge_uses_byte_parts_and_parses_surrounded_fenced_json():
    fetched = []
    built_parts = []

    def image_fetcher(url: str):
        fetched.append(url)
        return b"image bytes for " + url.encode(), "image/jpeg"

    def part_factory(*, data: bytes, mime_type: str):
        part = {"data": data, "mime_type": mime_type}
        built_parts.append(part)
        return part

    genai = FakeGenAIClient(
        'Here is my choice:\n```json\n{"selected_index": 2}\n```.'
    )
    judge = GeminiImageJudgeClient(
        genai,
        image_fetcher=image_fetcher,
        part_factory=part_factory,
    )

    selected = judge.select_image_index(
        image_urls=[
            "https://thumbnail.coupangcdn.com/first.jpg",
            "https://thumbnail.coupangcdn.com/second.jpg",
        ],
        title="페스룸 상품",
        description="강아지용 상품 상세 설명",
    )

    assert selected == 2
    assert fetched == [
        "https://thumbnail.coupangcdn.com/first.jpg",
        "https://thumbnail.coupangcdn.com/second.jpg",
    ]
    assert built_parts == [
        {
            "data": b"image bytes for https://thumbnail.coupangcdn.com/first.jpg",
            "mime_type": "image/jpeg",
        },
        {
            "data": b"image bytes for https://thumbnail.coupangcdn.com/second.jpg",
            "mime_type": "image/jpeg",
        },
    ]
    assert genai.models.calls[0]["contents"][1:] == built_parts


def test_gemini_judge_uses_first_json_object_containing_selected_index():
    def image_fetcher(url: str):
        return b"image bytes", "image/jpeg"

    def part_factory(*, data: bytes, mime_type: str):
        return {"data": data, "mime_type": mime_type}

    genai = FakeGenAIClient(
        'Context object: {"reason": "skip"}\nChoice object: {"selected_index": 2}'
    )
    judge = GeminiImageJudgeClient(
        genai,
        image_fetcher=image_fetcher,
        part_factory=part_factory,
    )

    selected = judge.select_image_index(
        image_urls=[
            "https://thumbnail.coupangcdn.com/first.jpg",
            "https://thumbnail.coupangcdn.com/second.jpg",
        ],
        title="페스룸 상품",
        description="강아지용 상품 상세 설명",
    )

    assert selected == 2


class FakeHTTPHeaders:
    def __init__(self, content_type: str, content_length: str | None = None):
        self.content_type = content_type
        self.content_length = content_length

    def get_content_type(self):
        return self.content_type

    def get(self, name: str, default=None):
        if name.lower() == "content-length":
            return self.content_length
        return default


class FakeHTTPResponse:
    def __init__(self, body: bytes, *, content_type: str = "image/jpeg", status: int = 200):
        self.body = body
        self.status = status
        self.headers = FakeHTTPHeaders(content_type, str(len(body)))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int):
        return self.body[:size]


def test_fetch_image_bytes_uses_timeout_and_returns_supported_image(monkeypatch):
    calls = []

    def fake_urlopen(request, *, timeout: float):
        calls.append({"request": request, "timeout": timeout})
        return FakeHTTPResponse(b"abc", content_type="image/webp")

    monkeypatch.setattr(
        "api.tools.coupang_product_scraper_tool.request.urlopen",
        fake_urlopen,
    )

    image = _fetch_image_bytes("https://thumbnail.coupangcdn.com/image.webp")

    assert image == (b"abc", "image/webp")
    assert calls[0]["timeout"] == 10.0


def test_fetch_image_bytes_rejects_unsupported_or_oversized_image(monkeypatch):
    def fake_urlopen_bad_type(request, *, timeout: float):
        return FakeHTTPResponse(b"abc", content_type="text/html")

    monkeypatch.setattr(
        "api.tools.coupang_product_scraper_tool.request.urlopen",
        fake_urlopen_bad_type,
    )

    with pytest.raises(ValueError, match="content type"):
        _fetch_image_bytes("https://thumbnail.coupangcdn.com/image.jpg")

    def fake_urlopen_too_large(request, *, timeout: float):
        return FakeHTTPResponse(
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )

    monkeypatch.setattr(
        "api.tools.coupang_product_scraper_tool.request.urlopen",
        fake_urlopen_too_large,
    )

    with pytest.raises(ValueError, match="too large"):
        _fetch_image_bytes("https://thumbnail.coupangcdn.com/image.jpg")
