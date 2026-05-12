from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.schemas.llm_catalog import LLMCatalogResponse
from api.services.llm_catalog import get_enabled_llm_catalog

router = APIRouter(prefix="/api/llm-catalog", tags=["llm-catalog"])


@router.get("", response_model=LLMCatalogResponse)
def get_llm_catalog(db: Session = Depends(get_db)):
    return get_enabled_llm_catalog(db)
