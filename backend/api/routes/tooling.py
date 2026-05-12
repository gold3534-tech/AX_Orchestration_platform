from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.schemas.capabilities import (
    SkillCatalogCreate,
    SkillCatalogResponse,
    ToolCatalogCreate,
    ToolCatalogResponse,
    VersionSkillAttachCreate,
    VersionSkillAttachmentResponse,
    VersionSkillAttachmentReadResponse,
    VersionToolAttachCreate,
    VersionToolAttachmentResponse,
    VersionToolAttachmentReadResponse,
    VersionToolAttachmentUpdate,
    VersionCapabilitiesBatchResponse,
)
from api.services.tooling import (
    ToolingConflictError,
    attach_skill_to_version,
    attach_tool_to_version,
    create_tool_catalog_entry,
    delete_tool_attachment,
    ensure_version_exists,
    get_tool_catalog_entry_by_key,
    list_skill_catalog_entries,
    list_tool_catalog_entries,
    list_version_skill_attachments,
    list_version_tool_attachments,
    update_tool_attachment,
)

router = APIRouter(prefix="/api", tags=["tooling"])


@router.get("/tool-catalog", response_model=list[ToolCatalogResponse])
def get_tool_catalog(db: Session = Depends(get_db)):
    return list_tool_catalog_entries(db)


@router.get("/tool-catalog/{tool_key}", response_model=ToolCatalogResponse)
def get_tool_catalog_entry(tool_key: str, db: Session = Depends(get_db)):
    try:
        return get_tool_catalog_entry_by_key(db, tool_key=tool_key)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/tool-catalog", response_model=ToolCatalogResponse, status_code=status.HTTP_201_CREATED)
def create_tool_catalog(payload: ToolCatalogCreate, db: Session = Depends(get_db)):
    try:
        return create_tool_catalog_entry(db, payload)
    except ToolingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/skill-catalog", response_model=list[SkillCatalogResponse])
def get_skill_catalog(db: Session = Depends(get_db)):
    return list_skill_catalog_entries(db)


@router.post("/skill-catalog", response_model=SkillCatalogResponse, status_code=status.HTTP_201_CREATED)
def create_skill_catalog(payload: SkillCatalogCreate, db: Session = Depends(get_db)):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Skill catalog creation is not available under the current schema.",
    )


@router.post("/versions/{version_id}/tools", response_model=VersionToolAttachmentResponse, status_code=status.HTTP_201_CREATED)
def attach_tool(version_id: str, payload: VersionToolAttachCreate, db: Session = Depends(get_db)):
    try:
        attached = attach_tool_to_version(
            db,
            version_id=version_id,
            tool_key=payload.tool_key,
            tool_config_json=payload.tool_config_json,
        )
    except ToolingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return VersionToolAttachmentResponse(
        id=attached.version_tool.id,
        version_id=attached.version_tool.version_id,
        tool_key=attached.version_tool.tool_key,
        tool_config_json=attached.version_tool.tool_config_json,
        sort_order=attached.version_tool.sort_order,
        created_at=attached.version_tool.created_at,
    )


@router.patch("/versions/{version_id}/tools/{tool_key}", response_model=VersionToolAttachmentResponse)
def update_attached_tool(
    version_id: str,
    tool_key: str,
    payload: VersionToolAttachmentUpdate,
    db: Session = Depends(get_db),
):
    try:
        attached = update_tool_attachment(
            db,
            version_id=version_id,
            tool_key=tool_key,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return VersionToolAttachmentResponse(
        id=attached.version_tool.id,
        version_id=attached.version_tool.version_id,
        tool_key=attached.version_tool.tool_key,
        tool_config_json=attached.version_tool.tool_config_json,
        sort_order=attached.version_tool.sort_order,
        created_at=attached.version_tool.created_at,
    )


@router.delete("/versions/{version_id}/tools/{tool_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attached_tool(version_id: str, tool_key: str, db: Session = Depends(get_db)):
    try:
        delete_tool_attachment(db, version_id=version_id, tool_key=tool_key)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/versions/{version_id}/tools", response_model=list[VersionToolAttachmentReadResponse])
def list_attached_tools(version_id: str, db: Session = Depends(get_db)):
    try:
        ensure_version_exists(db, version_id=version_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return list_version_tool_attachments(db, version_ids=[version_id])


@router.post("/versions/{version_id}/skills", response_model=VersionSkillAttachmentResponse, status_code=status.HTTP_201_CREATED)
def attach_skill(version_id: str, payload: VersionSkillAttachCreate, db: Session = Depends(get_db)):
    try:
        attached = attach_skill_to_version(
            db,
            version_id=version_id,
            skill_key=payload.skill_key,
        )
    except ToolingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return VersionSkillAttachmentResponse(
        id=attached.version_skill.id,
        version_id=attached.version_skill.version_id,
        skill_key=attached.version_skill.skill_key,
        skill_source=attached.version_skill.skill_source,
        sort_order=attached.version_skill.sort_order,
        created_at=attached.version_skill.created_at,
    )


@router.get("/versions/{version_id}/skills", response_model=list[VersionSkillAttachmentReadResponse])
def list_attached_skills(version_id: str, db: Session = Depends(get_db)):
    try:
        ensure_version_exists(db, version_id=version_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return list_version_skill_attachments(db, version_ids=[version_id])


@router.get("/version-capabilities", response_model=VersionCapabilitiesBatchResponse)
def list_version_capabilities(version_ids: list[str] = Query(...), db: Session = Depends(get_db)):
    return VersionCapabilitiesBatchResponse(
        tools=list_version_tool_attachments(db, version_ids=version_ids),
        skills=list_version_skill_attachments(db, version_ids=version_ids),
    )
