from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_COUPANG_HOST_SUFFIX = "coupang.com"
_AKAMAI_MARKERS = ("powered and protected by", "akamai-logo")
_DETAIL_ANCHOR = "필수 표기 정보"
_EXCLUSION_MARKERS = (
    "다른 고객이 함께 본 상품",
    "관련 상품",
    "추천 상품",
    "함께 구매한 상품",
)
_SUPPORTED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
_COUPANG_CDN_HOST_SUFFIX = "coupangcdn.com"
_SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_IMAGE_FETCH_TIMEOUT_SECONDS = 10.0
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ImageCandidate:
    url: str
    position: int


class CoupangProductScraperInput(BaseModel):
    url: str = Field(description="A single Coupang product page URL.")


class FirecrawlScrapeClient:
    def __init__(self, firecrawl_client: Any) -> None:
        self._client = firecrawl_client

    def scrape(self, url: str) -> Any:
        return self._client.scrape(
            url,
            formats=["markdown"],
            only_main_content=True,
            remove_base64_images=True,
            block_ads=True,
            proxy="auto",
            store_in_cache=True,
        )


def build_firecrawl_scrape_client_from_env() -> FirecrawlScrapeClient:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("FIRECRAWL_API_KEY is required for Coupang product scraping.")

    try:
        from firecrawl import Firecrawl
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise ValueError("firecrawl-py is required for Coupang product scraping.") from exc

    return FirecrawlScrapeClient(Firecrawl(api_key=api_key.strip()))


class GeminiImageJudgeClient:
    def __init__(
        self,
        genai_client: Any,
        *,
        model: str = "gemini-2.5-flash",
        image_fetcher: Any | None = None,
        part_factory: Any | None = None,
    ) -> None:
        self._client = genai_client
        self._model = model
        self._image_fetcher = image_fetcher or _fetch_image_bytes
        self._part_factory = part_factory or _genai_part_from_bytes

    def select_image_index(self, *, image_urls: list[str], title: str, description: str) -> int:
        prompt = (
            "Choose the single best representative product-detail image for this Coupang "
            "product. Prefer the detailed product image over logos, icons, ads, thumbnails, "
            "recommendations, and unrelated assets. Reply only as JSON with a 1-based "
            'integer field named "selected_index".\n\n'
            f"Title: {title or ''}\n"
            f"Description: {description or ''}\n"
            f"Candidate image count: {len(image_urls)}"
        )
        contents: list[Any] = [prompt]
        for image_url in image_urls:
            image_bytes, mime_type = self._image_fetcher(image_url)
            contents.append(self._part_factory(data=image_bytes, mime_type=mime_type))
        response = self._client.models.generate_content(model=self._model, contents=contents)
        return _selected_index_from_text(_response_text(response))


def _genai_part_from_bytes(*, data: bytes, mime_type: str) -> Any:
    try:
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise ValueError("google-genai is required for Coupang image judging.") from exc

    return types.Part.from_bytes(data=data, mime_type=mime_type)


def _fetch_image_bytes(
    url: str,
    *,
    timeout_seconds: float = _IMAGE_FETCH_TIMEOUT_SECONDS,
    max_bytes: int = _MAX_IMAGE_BYTES,
) -> tuple[bytes, str]:
    normalized_url = _normalize_image_url(url)
    if not _image_url_supported(normalized_url):
        raise ValueError(f"Unsupported image URL: {url}")

    image_request = request.Request(
        normalized_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with request.urlopen(image_request, timeout=float(timeout_seconds)) as response:
            status = _response_status(response)
            if status != 200:
                raise ValueError(f"Image fetch returned non-200 status: {status}")
            mime_type = _response_content_type(response)
            if mime_type not in _SUPPORTED_IMAGE_MIME_TYPES:
                raise ValueError(f"Unsupported image content type: {mime_type}")
            content_length = _response_content_length(response)
            if content_length is not None and content_length > max_bytes:
                raise ValueError("Fetched image is too large")
            data = response.read(max_bytes + 1)
    except ValueError:
        raise
    except (error.URLError, OSError) as exc:
        raise ValueError(f"Failed to fetch image bytes: {url}") from exc

    if len(data) > max_bytes:
        raise ValueError("Fetched image is too large")
    return data, mime_type


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    try:
        return int(status)
    except (TypeError, ValueError):
        raise ValueError("Image fetch response did not include a valid status code") from None


def _response_content_type(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    content_type = ""
    if hasattr(headers, "get_content_type"):
        content_type = headers.get_content_type()
    if not content_type and hasattr(headers, "get"):
        content_type = (headers.get("Content-Type") or "").split(";", 1)[0]
    return content_type.strip().lower()


def _response_content_length(response: Any) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    raw_value = headers.get("Content-Length")
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _selected_index_from_text(text: str) -> int:
    for payload in _json_values_from_text(text):
        selected_index = _selected_index_from_payload(payload)
        if selected_index is not None:
            return selected_index
    raise ValueError("Gemini image judge response did not include selected_index.")


def _selected_index_from_payload(payload: Any) -> int | None:
    if isinstance(payload, int):
        return payload
    if isinstance(payload, dict):
        selected = payload.get("selected_index")
        if isinstance(selected, int):
            return selected
        if isinstance(selected, str) and selected.strip().isdigit():
            return int(selected.strip())
    return None


def _json_values_from_text(text: str):
    stripped = _strip_json_fence(text)
    try:
        yield json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload


def build_gemini_image_judge_from_env() -> GeminiImageJudgeClient:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("GOOGLE_API_KEY is required for Coupang image judging.")

    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise ValueError("google-genai is required for Coupang image judging.") from exc

    return GeminiImageJudgeClient(genai.Client(api_key=api_key.strip()))


def _mime_type_for_url(url: str) -> str:
    extension = PurePosixPath(urlparse(url).path).suffix.lower()
    if extension in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if extension == ".png":
        return "image/png"
    if extension == ".webp":
        return "image/webp"
    return "image/jpeg"


def _response_text(response: Any) -> str:
    direct_text = getattr(response, "text", None)
    if isinstance(direct_text, str) and direct_text.strip():
        return _strip_json_fence(direct_text.strip())

    parts_text: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                parts_text.append(text.strip())
    if parts_text:
        return _strip_json_fence("\n".join(parts_text))
    raise ValueError("Gemini image judge response did not include text.")


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _valid_output_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _require_coupang_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Coupang URL must not be empty")
    normalized = url.strip()
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        hostname == _COUPANG_HOST_SUFFIX or hostname.endswith(f".{_COUPANG_HOST_SUFFIX}")
    ):
        raise ValueError("Coupang URL is required")
    return normalized


def _document_text(document: Any) -> str:
    if isinstance(document, dict):
        parts = [
            document.get("markdown"),
            document.get("html"),
            _metadata_json_for_detection(document.get("metadata")),
        ]
        return "\n".join(str(part) for part in parts if part is not None)
    parts = [
        getattr(document, "markdown", None),
        getattr(document, "html", None),
        _metadata_json_for_detection(getattr(document, "metadata", None)),
    ]
    return "\n".join(str(part) for part in parts if part is not None)


def _document_mapping(document: Any) -> dict[str, Any]:
    if isinstance(document, dict):
        return document
    return {
        "markdown": getattr(document, "markdown", ""),
        "html": getattr(document, "html", ""),
        "metadata": getattr(document, "metadata", {}) or {},
    }


def _metadata_mapping(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata

    try:
        model_dump = getattr(metadata, "model_dump", None)
    except Exception:
        model_dump = None
    if callable(model_dump):
        try:
            dumped = model_dump(exclude_none=True)
        except TypeError:
            try:
                dumped = model_dump()
            except Exception:
                dumped = None
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            return dumped

    try:
        dict_method = getattr(metadata, "dict", None)
    except Exception:
        dict_method = None
    if callable(dict_method):
        try:
            dumped = dict_method(exclude_none=True)
        except TypeError:
            try:
                dumped = dict_method()
            except Exception:
                dumped = None
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            return dumped

    attributes: dict[str, Any] = {}
    try:
        names = dir(metadata)
    except Exception:
        names = []
    for name in names:
        if name.startswith("_"):
            continue
        try:
            value = getattr(metadata, name)
        except Exception:
            continue
        if callable(value):
            continue
        attributes[name] = value
    return attributes


def _metadata_json_for_detection(metadata: Any) -> str:
    try:
        return json.dumps(_metadata_mapping(metadata), ensure_ascii=False, default=str)
    except Exception:
        return str(metadata or "")


def _akamai_blocked(document: Any) -> bool:
    normalized = _document_text(document).lower()
    return any(marker in normalized for marker in _AKAMAI_MARKERS)


def _metadata_value(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _compact_metadata(document: Any) -> tuple[str, str, str]:
    mapping = _document_mapping(document)
    metadata = _metadata_mapping(mapping.get("metadata"))
    title = _metadata_value(metadata, "ogTitle", "og:title", "og_title", "title")
    description = _metadata_value(
        metadata,
        "ogDescription",
        "og:description",
        "og_description",
        "description",
    )
    image = _metadata_value(metadata, "ogImage", "og:image", "og_image", "image")
    return title, description, _normalize_image_url(image)


def _normalize_image_url(url: str) -> str:
    if not isinstance(url, str):
        return ""
    value = url.strip().strip("'\"")
    if not value:
        return ""
    if value.startswith("//"):
        value = f"https:{value}"
    if value.startswith("http://") and "coupangcdn.com" in value:
        value = f"https://{value[len('http://'):]}"
    return value


def _markdown_body(document: Any) -> str:
    mapping = _document_mapping(document)
    markdown = mapping.get("markdown")
    return markdown if isinstance(markdown, str) else ""


def _exclusion_heading(line: str) -> bool:
    stripped = line.strip()
    if stripped in _EXCLUSION_MARKERS:
        return True
    if not stripped.startswith("#"):
        return False
    heading = stripped.lstrip("#").strip()
    return heading in _EXCLUSION_MARKERS


def _candidate_scan_region(markdown: str) -> tuple[str, int]:
    anchor_index = markdown.find(_DETAIL_ANCHOR)
    if anchor_index < 0:
        return "", 0
    region_start = anchor_index + len(_DETAIL_ANCHOR)
    region = markdown[region_start:]
    offset = 0
    for line in region.splitlines(keepends=True):
        if _exclusion_heading(line):
            return region[:offset], region_start
        offset += len(line)
    return region, region_start


def _image_url_supported(url: str) -> bool:
    normalized = url.lower()
    if not normalized or normalized.startswith("data:image"):
        return False
    if "akamai" in normalized:
        return False
    if any(fragment in normalized for fragment in (".mp4", ".mov", ".webm", ".m3u8")):
        return False
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"}:
        return False
    if not (
        hostname == _COUPANG_CDN_HOST_SUFFIX
        or hostname.endswith(f".{_COUPANG_CDN_HOST_SUFFIX}")
    ):
        return False
    path = parsed.path
    return path.endswith(_SUPPORTED_IMAGE_EXTENSIONS)


def _markdown_image_destination(markdown: str, start: int) -> tuple[str, int] | None:
    alt_end = markdown.find("]", start + 2)
    if alt_end < 0 or alt_end + 1 >= len(markdown) or markdown[alt_end + 1] != "(":
        return None

    destination_start = alt_end + 2
    while destination_start < len(markdown) and markdown[destination_start].isspace():
        destination_start += 1
    if destination_start >= len(markdown):
        return None

    if markdown[destination_start] == "<":
        url_start = destination_start + 1
        url_end = markdown.find(">", url_start)
        if url_end < 0:
            return None
        return markdown[url_start:url_end], url_start

    url_start = destination_start
    index = url_start
    depth = 0
    while index < len(markdown):
        char = markdown[index]
        if char.isspace() and depth == 0:
            break
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        index += 1
    if index == url_start:
        return None
    return markdown[url_start:index], url_start


def _iter_markdown_image_destinations(markdown: str, *, offset: int = 0):
    search_start = 0
    while True:
        image_start = markdown.find("![", search_start)
        if image_start < 0:
            return
        destination = _markdown_image_destination(markdown, image_start)
        if destination is None:
            search_start = image_start + 2
            continue
        url, url_start = destination
        yield url, offset + url_start
        search_start = url_start + len(url)


def _extract_image_candidates(markdown: str, *, limit: int = 3) -> list[ImageCandidate]:
    if not isinstance(markdown, str) or not markdown:
        return []
    region, region_start = _candidate_scan_region(markdown)
    if not region:
        return []

    candidates: list[ImageCandidate] = []
    seen: set[str] = set()
    for raw_url, position in _iter_markdown_image_destinations(region, offset=region_start):
        url = _normalize_image_url(raw_url)
        if not _image_url_supported(url) or url in seen:
            continue
        seen.add(url)
        candidates.append(ImageCandidate(url=url, position=position))
        if len(candidates) >= limit:
            break
    return candidates


class AXCoupangProductScraperTool(BaseTool):
    name: str = "AX Coupang Product Scraper"
    description: str = (
        "Scrape a Coupang product URL and return compact Open Graph-style product metadata."
    )
    args_schema: type[BaseModel] = CoupangProductScraperInput

    firecrawl_client: Any | None = None
    judge_client: Any | None = None

    def _run(self, url: str) -> dict[str, str]:
        normalized_url = _require_coupang_url(url)
        document = self._scrape_document(normalized_url)
        if _akamai_blocked(document):
            logger.info("Retrying Coupang scrape after Akamai block detection")
            document = self._scrape_document(normalized_url)
        if _akamai_blocked(document):
            raise ValueError("Coupang scrape was blocked by Akamai after retry.")

        title, description, metadata_image = _compact_metadata(document)
        title = _required_output_value(title, "og_title")
        description = _required_output_value(description, "og_description")
        candidates = _extract_image_candidates(_markdown_body(document))
        image = self._select_image(
            candidates=candidates,
            metadata_image=metadata_image,
            title=title,
            description=description,
        )
        return {
            "og_title": _valid_output_value(title),
            "og_image": _valid_output_value(image),
            "og_description": _valid_output_value(description),
        }

    def _scrape_document(self, url: str) -> Any:
        return self._firecrawl_client().scrape(url)

    def _firecrawl_client(self) -> Any:
        if self.firecrawl_client is None:
            self.firecrawl_client = build_firecrawl_scrape_client_from_env()
        return self.firecrawl_client

    def _judge_client(self) -> Any:
        if self.judge_client is None:
            self.judge_client = build_gemini_image_judge_from_env()
        return self.judge_client

    def _select_image(
        self,
        *,
        candidates: list[ImageCandidate],
        metadata_image: str,
        title: str,
        description: str,
    ) -> str:
        if len(candidates) == 1:
            return candidates[0].url
        if len(candidates) >= 2:
            image_urls = [candidate.url for candidate in candidates]
            try:
                selected_index = self._judge_client().select_image_index(
                    image_urls=image_urls,
                    title=title,
                    description=description,
                )
                if isinstance(selected_index, int) and 1 <= selected_index <= len(image_urls):
                    return image_urls[selected_index - 1]
            except Exception:
                logger.exception("Coupang image judge failed; falling back to first candidate")
            return image_urls[0]
        if _image_url_supported(metadata_image):
            return metadata_image
        raise ValueError("Coupang scrape did not include a supported product image.")


def _required_output_value(value: Any, field_name: str) -> str:
    output_value = _valid_output_value(value)
    if not output_value:
        raise ValueError(f"{field_name} is required in Coupang scrape metadata.")
    return output_value
