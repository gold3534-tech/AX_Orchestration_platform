from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from api.runtime.credential_providers import tool_credential_requirements


DEFAULT_CREWAI_TOOL_TIMESTAMP = datetime(2026, 4, 25, tzinfo=timezone.utc)


@dataclass(frozen=True)
class DefaultCrewAITool:
    tool_key: str
    name: str
    description: str
    class_name: str
    module_path_value: str = "crewai_tools"
    tool_type_value: str = "crewai_tool"
    default_config_json: dict = field(default_factory=dict)
    config_schema_json: dict = field(default_factory=dict)
    input_schema_json: dict = field(default_factory=dict)
    ui_schema_json: dict = field(default_factory=dict)
    required_env_vars: list[dict] = field(default_factory=list)
    credential_requirements: list[dict] = field(default_factory=list)

    @property
    def module_path(self) -> str:
        return self.module_path_value

    @property
    def tool_type(self) -> str:
        return self.tool_type_value

    @property
    def entrypoint(self) -> str:
        return f"{self.module_path}:{self.class_name}"

    def to_response(self) -> dict:
        return {
            "id": self.tool_key,
            "tool_key": self.tool_key,
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type,
            "module_path": self.module_path,
            "class_name": self.class_name,
            "default_config_json": deepcopy(self.default_config_json),
            "config_schema_json": deepcopy(self.config_schema_json),
            "input_schema_json": deepcopy(self.input_schema_json),
            "ui_schema_json": deepcopy(self.ui_schema_json),
            "required_env_vars": deepcopy(self.required_env_vars),
            "credential_requirements": deepcopy(self.credential_requirements),
            "enabled": True,
            "created_at": DEFAULT_CREWAI_TOOL_TIMESTAMP,
            "updated_at": DEFAULT_CREWAI_TOOL_TIMESTAMP,
        }


SERPER_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "base_url": {"type": "string", "default": "https://google.serper.dev"},
        "n_results": {"type": "integer", "default": 10, "minimum": 1},
        "save_file": {"type": "boolean", "default": False},
        "search_type": {"type": "string", "enum": ["search", "news"], "default": "search"},
        "country": {"type": "string", "default": ""},
        "location": {"type": "string", "default": ""},
        "locale": {"type": "string", "default": ""},
    },
    "additionalProperties": False,
}

SERPER_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "search_query": {
            "type": "string",
            "description": "Mandatory search query you want to use to search the internet",
        }
    },
    "required": ["search_query"],
}

SERPER_UI_SCHEMA = {
    "fields": {
        "search_type": {"widget": "select", "options": ["search", "news"]},
        "n_results": {"widget": "number", "min": 1},
        "country": {"advanced": True},
        "location": {"advanced": True},
        "locale": {"advanced": True},
        "base_url": {"advanced": True},
        "save_file": {"advanced": True},
    }
}

SERPER_REQUIRED_ENV_VARS = [
    {"name": "SERPER_API_KEY", "description": "API key for Serper", "required": True}
]

GOOGLE_SHEETS_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "read_range_enabled": {"type": "boolean", "default": True},
        "append_rows_enabled": {"type": "boolean", "default": True},
        "update_values_enabled": {"type": "boolean", "default": True},
    },
    "additionalProperties": False,
}

GOOGLE_SHEETS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": ["read_range", "append_rows", "update_values"],
        },
        "spreadsheet_id": {"type": "string"},
        "range_name": {"type": "string"},
        "values": {"type": "array"},
    },
    "required": ["operation", "spreadsheet_id", "range_name"],
    "additionalProperties": True,
}

GOOGLE_SHEETS_UI_SCHEMA = {
    "fields": {
        "read_range_enabled": {"widget": "checkbox"},
        "append_rows_enabled": {"widget": "checkbox"},
        "update_values_enabled": {"widget": "checkbox"},
    }
}

GOOGLE_SHEETS_DEFAULT_CONFIG = {
    "read_range_enabled": True,
    "append_rows_enabled": True,
    "update_values_enabled": True,
}

NANO_BANANA_MODEL_OPTIONS = [
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
]
NANO_BANANA_ASPECT_RATIO_OPTIONS = ["1:1", "9:16", "16:9"]
NANO_BANANA_IMAGE_SIZE_OPTIONS = ["1K", "2K", "4K"]

NANO_BANANA_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {
            "type": "string",
            "enum": NANO_BANANA_MODEL_OPTIONS,
            "default": "gemini-3.1-flash-image-preview",
        },
        "aspect_ratio": {
            "type": "string",
            "enum": NANO_BANANA_ASPECT_RATIO_OPTIONS,
            "default": "1:1",
        },
        "image_size": {
            "type": "string",
            "enum": NANO_BANANA_IMAGE_SIZE_OPTIONS,
            "default": "1K",
        },
    },
    "additionalProperties": False,
}

NANO_BANANA_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "Single image prompt."},
        "image_prompts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "Batch image prompts. Use either prompt or image_prompts.",
        },
        "delay_seconds": {
            "type": "number",
            "minimum": 0,
            "maximum": 30,
            "default": 10,
            "description": "Seconds to wait between batch image generations.",
        },
        "artifact_storage_mode": {
            "type": "string",
            "enum": ["temporary_only"],
            "default": "temporary_only",
        },
    },
    "additionalProperties": False,
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "artifact_storage_mode": {
                    "type": "string",
                    "enum": ["temporary_only"],
                    "default": "temporary_only",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "image_prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "delay_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 10,
                },
                "artifact_storage_mode": {
                    "type": "string",
                    "enum": ["temporary_only"],
                    "default": "temporary_only",
                },
            },
            "required": ["image_prompts"],
            "additionalProperties": False,
        },
    ],
}

NANO_BANANA_UI_SCHEMA = {
    "fields": {
        "model": {
            "widget": "select",
            "label": "Model",
            "help": "Choose the Gemini image model for this tool attachment.",
        },
        "aspect_ratio": {
            "widget": "select",
            "label": "Output ratio",
            "help": "Choose the generated image composition.",
            "prominent": True,
        },
        "image_size": {
            "widget": "select",
            "label": "Image size",
            "help": "Gemini 3 image models support 1K, 2K, and 4K output sizes.",
        },
    }
}

NANO_BANANA_DEFAULT_CONFIG = {
    "model": "gemini-3.1-flash-image-preview",
    "aspect_ratio": "1:1",
    "image_size": "1K",
}

COUPANG_PRODUCT_SCRAPER_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Single Coupang product page URL.",
        }
    },
    "required": ["url"],
    "additionalProperties": False,
}

INSTAGRAM_PUBLISH_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "publish_mode": {
            "type": "integer",
            "enum": [1, 3],
            "default": 3,
        },
        "poll_timeout_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": 300,
            "default": 60,
            "description": "Maximum seconds to wait for Meta media processing before publishing.",
        },
        "poll_interval_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": 60,
            "default": 3,
            "description": "Seconds between Meta container status checks.",
        },
    },
    "additionalProperties": False,
}

INSTAGRAM_PUBLISH_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "artifact_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
        "caption": {"type": "string"},
    },
    "required": ["artifact_ids", "caption"],
    "additionalProperties": False,
}

INSTAGRAM_PUBLISH_UI_SCHEMA = {
    "fields": {
        "publish_mode": {
            "widget": "select",
            "label": "Publish preference",
            "help": "The tool publishes 1 unique artifact as a single post and 3 unique artifacts as a carousel.",
            "options": [1, 3],
        },
        "poll_timeout_seconds": {
            "widget": "number",
            "label": "Publish wait timeout",
            "help": "Maximum seconds to wait for Meta media processing before publishing.",
        },
        "poll_interval_seconds": {
            "widget": "number",
            "label": "Status check interval",
            "help": "Seconds between Meta container status checks.",
        },
    }
}

INSTAGRAM_PUBLISH_DEFAULT_CONFIG = {
    "publish_mode": 3,
    "poll_timeout_seconds": 60,
    "poll_interval_seconds": 3,
}


DEFAULT_CREWAI_TOOLS = (
    DefaultCrewAITool(
        tool_key="crewai.directory_read",
        name="Directory Read",
        description="Read directory contents.",
        class_name="DirectoryReadTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.file_read",
        name="File Read",
        description="Read file contents.",
        class_name="FileReadTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.csv_search",
        name="CSV Search",
        description="Search CSV files.",
        class_name="CSVSearchTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.json_search",
        name="JSON Search",
        description="Search JSON files.",
        class_name="JSONSearchTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.pdf_search",
        name="PDF Search",
        description="Search PDF files.",
        class_name="PDFSearchTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.website_search",
        name="Website Search",
        description="Search website content.",
        class_name="WebsiteSearchTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.scrape_website",
        name="Scrape Website",
        description="Scrape website content.",
        class_name="ScrapeWebsiteTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.serper_dev",
        name="Serper Dev Search",
        description="Search the web with Serper Dev.",
        class_name="SerperDevTool",
        config_schema_json=SERPER_CONFIG_SCHEMA,
        input_schema_json=SERPER_INPUT_SCHEMA,
        ui_schema_json=SERPER_UI_SCHEMA,
        required_env_vars=SERPER_REQUIRED_ENV_VARS,
        credential_requirements=tool_credential_requirements("crewai.serper_dev"),
    ),
    DefaultCrewAITool(
        tool_key="crewai.github_search",
        name="GitHub Search",
        description="Search GitHub content.",
        class_name="GithubSearchTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.dalle",
        name="DALL-E Tool",
        description="Generate images from text prompts.",
        class_name="DallETool",
        credential_requirements=tool_credential_requirements("crewai.dalle"),
    ),
    DefaultCrewAITool(
        tool_key="crewai.firecrawl_scrape_website",
        name="Firecrawl Scrape Website",
        description="Scrape website content with Firecrawl.",
        class_name="FirecrawlScrapeWebsiteTool",
        credential_requirements=tool_credential_requirements("crewai.firecrawl_scrape_website"),
    ),
    DefaultCrewAITool(
        tool_key="ax.coupang_product_scraper",
        name="AX Coupang Product Scraper",
        description=(
            "Scrape one Coupang product page and return compact product metadata "
            "with a selected product detail image."
        ),
        class_name="AXCoupangProductScraperTool",
        module_path_value="api.tools.coupang_product_scraper_tool",
        tool_type_value="python_class",
        input_schema_json=COUPANG_PRODUCT_SCRAPER_INPUT_SCHEMA,
        credential_requirements=tool_credential_requirements("ax.coupang_product_scraper"),
    ),
    DefaultCrewAITool(
        tool_key="crewai.youtube_video_search",
        name="YouTube Video Search",
        description="Search YouTube video content.",
        class_name="YoutubeVideoSearchTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.youtube_channel_search",
        name="YouTube Channel Search",
        description="Search YouTube channel content.",
        class_name="YoutubeChannelSearchTool",
    ),
    DefaultCrewAITool(
        tool_key="crewai.vision",
        name="Vision Tool",
        description="Analyze images with OpenAI vision capabilities.",
        class_name="VisionTool",
        credential_requirements=tool_credential_requirements("crewai.vision"),
    ),
    DefaultCrewAITool(
        tool_key="ax.google_sheets",
        name="AX Google Sheets",
        description="Read and update Google Sheets through the connected user's Google Workspace account.",
        class_name="AXGoogleSheetsTool",
        module_path_value="api.tools.google_sheets_tool",
        tool_type_value="python_class",
        default_config_json=GOOGLE_SHEETS_DEFAULT_CONFIG,
        config_schema_json=GOOGLE_SHEETS_CONFIG_SCHEMA,
        input_schema_json=GOOGLE_SHEETS_INPUT_SCHEMA,
        ui_schema_json=GOOGLE_SHEETS_UI_SCHEMA,
        credential_requirements=tool_credential_requirements("ax.google_sheets"),
    ),
    DefaultCrewAITool(
        tool_key="ax.nano_banana_image",
        name="AX Nano Banana Image",
        description="Generate images with Google Nano Banana 2 and stage them as AX artifacts.",
        class_name="AXNanoBananaImageTool",
        module_path_value="api.tools.nano_banana_image_tool",
        tool_type_value="python_class",
        default_config_json=NANO_BANANA_DEFAULT_CONFIG,
        config_schema_json=NANO_BANANA_CONFIG_SCHEMA,
        input_schema_json=NANO_BANANA_INPUT_SCHEMA,
        ui_schema_json=NANO_BANANA_UI_SCHEMA,
        credential_requirements=tool_credential_requirements("ax.nano_banana_image"),
    ),
    DefaultCrewAITool(
        tool_key="ax.instagram_publish_tool",
        name="AX Instagram Publish",
        description="Publish AX image artifacts to Instagram as a single image post or a 3-image carousel.",
        class_name="AXInstagramPublishTool",
        module_path_value="api.tools.instagram_publish_tool",
        tool_type_value="python_class",
        default_config_json=INSTAGRAM_PUBLISH_DEFAULT_CONFIG,
        config_schema_json=INSTAGRAM_PUBLISH_CONFIG_SCHEMA,
        input_schema_json=INSTAGRAM_PUBLISH_INPUT_SCHEMA,
        ui_schema_json=INSTAGRAM_PUBLISH_UI_SCHEMA,
        credential_requirements=tool_credential_requirements("ax.instagram_publish_tool"),
    ),
)

DEFAULT_CREWAI_TOOL_BY_KEY = {tool.tool_key: tool for tool in DEFAULT_CREWAI_TOOLS}
