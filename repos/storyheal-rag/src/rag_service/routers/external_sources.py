"""Internal Storyblok ingestion API used by the signed webhook worker."""

from datetime import datetime, timezone
import secrets
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db_session_dependency
from ..models import Collection, FileDocument, StoryblokExternalSource
from ..schemas.external_sources import StoryblokSourceUpsert, StoryblokSourceView
from ..services.embedding import get_embedding_service_for_project
from ..services.vector_store import get_vector_store_service

router = APIRouter()


def require_internal_key(x_internal_key: str = Header(..., alias="X-Internal-Key")) -> None:
    expected = get_settings().rag_internal_api_key
    if not expected or not secrets.compare_digest(x_internal_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal key")


async def _delete_vector(document_id: UUID, project_id: UUID) -> None:
    embedding = await get_embedding_service_for_project(project_id)
    await get_vector_store_service().delete_document_embedding_for_project(
        document_id, str(project_id), embedding.embeddings_client
    )


@router.put(
    "/{collection_id}/external-sources/storyblok/{story_uuid}",
    response_model=StoryblokSourceView,
    dependencies=[Depends(require_internal_key)],
)
async def upsert_storyblok_source(
    collection_id: UUID,
    story_uuid: str,
    payload: StoryblokSourceUpsert,
    db: AsyncSession = Depends(get_db_session_dependency),
) -> StoryblokSourceView:
    collection = (
        await db.execute(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.project_id == payload.project_id,
                Collection.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="RAG collection not found")

    source = (
        await db.execute(
            select(StoryblokExternalSource).where(
                StoryblokExternalSource.project_id == payload.project_id,
                StoryblokExternalSource.collection_id == collection_id,
                StoryblokExternalSource.story_uuid == story_uuid,
                StoryblokExternalSource.locale == payload.locale,
            )
        )
    ).scalar_one_or_none()
    if source and source.content_hash == payload.content_hash and source.status == "indexed":
        view = StoryblokSourceView.model_validate(source)
        return view.model_copy(update={"unchanged": True})

    if source and source.document_id:
        await _delete_vector(source.document_id, payload.project_id)
        old_document = await db.get(FileDocument, source.document_id)
        if old_document:
            await db.delete(old_document)

    document = FileDocument(
        id=uuid4(),
        project_id=payload.project_id,
        collection_id=collection_id,
        file_id=None,
        document_title=payload.title,
        content=payload.content,
        content_length=len(payload.content),
        token_count=len(payload.content.split()),
        chunk_index=0,
        content_type="storyblok",
        language=payload.locale,
        tags={
            **payload.metadata,
            "source_type": "storyblok",
            "story_uuid": story_uuid,
            "slug": payload.slug,
            "locale": payload.locale,
            "published_at": payload.published_at.isoformat() if payload.published_at else None,
            "content_hash": payload.content_hash,
            "citations": payload.citations,
            "source_url": payload.source_url,
            "channel_variants": payload.channel_variants,
        },
    )
    db.add(document)

    if source is None:
        source = StoryblokExternalSource(
            project_id=payload.project_id,
            collection_id=collection_id,
            story_uuid=story_uuid,
            locale=payload.locale,
            title=payload.title,
            slug=payload.slug,
            content_type=payload.content_type,
            content=payload.content,
            content_hash=payload.content_hash,
        )
        db.add(source)

    source.document_id = document.id
    source.title = payload.title
    source.slug = payload.slug
    source.content_type = payload.content_type
    source.source_url = payload.source_url
    source.content = payload.content
    source.content_hash = payload.content_hash
    source.published_at = payload.published_at
    source.citations = payload.citations
    source.channel_variants = payload.channel_variants
    source.source_metadata = payload.metadata
    source.status = "indexing"
    source.last_error = None
    await db.flush()

    try:
        embedding = await get_embedding_service_for_project(payload.project_id)
        await get_vector_store_service().add_documents_batch_for_project(
            documents=[(document.id, document.content, document.tags)],
            project_key=str(payload.project_id),
            embedding_client=embedding.embeddings_client,
        )
    except Exception as exc:
        source.status = "failed"
        source.last_error = str(exc)[:2000]
        await db.commit()
        raise HTTPException(status_code=503, detail="Embedding failed; retry is safe") from exc

    source.status = "indexed"
    source.indexed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(source)
    return StoryblokSourceView.model_validate(source)


@router.delete(
    "/{collection_id}/external-sources/storyblok/{story_uuid}",
    status_code=204,
    dependencies=[Depends(require_internal_key)],
)
async def delete_storyblok_source(
    collection_id: UUID,
    story_uuid: str,
    project_id: UUID = Query(...),
    locale: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session_dependency),
) -> Response:
    query = select(StoryblokExternalSource).where(
        and_(
            StoryblokExternalSource.collection_id == collection_id,
            StoryblokExternalSource.story_uuid == story_uuid,
            StoryblokExternalSource.project_id == project_id,
        )
    )
    if locale:
        query = query.where(StoryblokExternalSource.locale == locale)
    sources = list((await db.execute(query)).scalars().all())
    for source in sources:
        if source.document_id:
            await _delete_vector(source.document_id, project_id)
            document = await db.get(FileDocument, source.document_id)
            if document:
                await db.delete(document)
        await db.delete(source)
    await db.commit()
    return Response(status_code=204)
