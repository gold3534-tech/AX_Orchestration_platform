from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.dependencies import get_current_user
from api.schemas.knowledge import (
    KnowledgeCreate,
    KnowledgeResponse,
    VersionKnowledgeResponse,
    VersionKnowledgeUpdate,
)
from api.services.knowledge import (
    KnowledgeValidationError,
    create_knowledge_item,
    create_knowledge_item_from_pdf_upload,
    delete_knowledge_item,
    list_version_knowledge,
    list_knowledge_items,
    replace_version_knowledge,
)

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/knowledge", response_model=list[KnowledgeResponse])
def list_knowledge(db: Session = Depends(get_db)):
    return list_knowledge_items(db)


@router.post("/knowledge", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge(payload: KnowledgeCreate, db: Session = Depends(get_db)):
    try:
        return create_knowledge_item(db, payload)
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/knowledge/upload", response_model=KnowledgeResponse, status_code=status.HTTP_201_CREATED)
async def upload_knowledge(
    file: Annotated[UploadFile, File()],
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    file_bytes = await file.read()
    try:
        return create_knowledge_item_from_pdf_upload(
            db,
            file_bytes=file_bytes,
            source_file_name=file.filename or "document.pdf",
            source_file_size=len(file_bytes),
            source_mime_type=file.content_type or "",
            name=name,
            description=description,
            owner_user_id=current_user["id"],
        )
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/versions/{version_id}/knowledge", response_model=list[VersionKnowledgeResponse])
def get_version_knowledge(version_id: str, db: Session = Depends(get_db)):
    try:
        return list_version_knowledge(db, version_id=version_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.put("/versions/{version_id}/knowledge", response_model=list[VersionKnowledgeResponse])
def put_version_knowledge(version_id: str, payload: VersionKnowledgeUpdate, db: Session = Depends(get_db)):
    try:
        return replace_version_knowledge(db, version_id=version_id, knowledge_item_ids=payload.knowledge_item_ids)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except KnowledgeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.delete("/knowledge/{knowledge_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(knowledge_item_id: str, db: Session = Depends(get_db)):
    try:
        delete_knowledge_item(db, knowledge_item_id=knowledge_item_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
