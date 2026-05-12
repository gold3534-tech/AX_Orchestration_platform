from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.schemas.capabilities import CapabilityCatalogResponse
from api.services.capabilities import list_capabilities, list_execution_actions

router = APIRouter(prefix="/api", tags=["capabilities"])


@router.get("/capabilities", response_model=list[CapabilityCatalogResponse])
def list_capabilities_route(db: Session = Depends(get_db)):
    return list_capabilities(db)


@router.get("/execution-actions", response_model=list[CapabilityCatalogResponse])
def list_execution_actions_route():
    return list_execution_actions()
