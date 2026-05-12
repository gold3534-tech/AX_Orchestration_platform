from typing import Literal

from pydantic import BaseModel, Field


class LLMModelResponse(BaseModel):
    model_key: str
    provider_key: str
    display_name: str
    enabled: bool
    sort_order: int
    llm_metadata_json: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class LLMProviderResponse(BaseModel):
    provider_key: str
    display_name: str
    provider_type: Literal["hosted", "local"]
    credential_provider: str | None = None
    enabled: bool
    sort_order: int
    metadata_json: dict = Field(default_factory=dict)
    models: list[LLMModelResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class LLMCatalogResponse(BaseModel):
    providers: list[LLMProviderResponse] = Field(default_factory=list)
