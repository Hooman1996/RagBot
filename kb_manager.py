# kb_manager.py
import re
import json
import os
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from qdrant_client.models import PointStruct, PointIdsList
import psycopg2
import psycopg2.extras
from parsivar import Normalizer

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base Management"])
templates = Jinja2Templates(directory="templates")
normalizer = Normalizer()

POSTGRES_ENVIRONMENT_VARIABLES = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)


def _postgres_connection_kwargs():
    missing = [
        variable
        for variable in POSTGRES_ENVIRONMENT_VARIABLES
        if not os.getenv(variable)
    ]
    if missing:
        raise RuntimeError(
            "Missing required PostgreSQL configuration: "
            + ", ".join(missing)
        )

    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ["POSTGRES_PORT"],
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def get_db_connection():
    conn = psycopg2.connect(
        **_postgres_connection_kwargs(),
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    # Ensure atomic automatic creation of version control tracking tables
    with conn.cursor() as cur:
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS chunk_versions
                    (
                        id
                        SERIAL
                        PRIMARY
                        KEY,
                        chunk_id
                        INT
                        NOT
                        NULL,
                        content
                        TEXT
                        NOT
                        NULL,
                        changed_by
                        VARCHAR
                    (
                        255
                    ) NOT NULL,
                        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                        CONSTRAINT fk_chunk_id FOREIGN KEY
                    (
                        chunk_id
                    ) REFERENCES chunks
                    (
                        id
                    )
                                             ON DELETE CASCADE
                        );
                    """)
        conn.commit()
    return conn


class ChunkCreatePayload(BaseModel):
    document_id: int
    question: Optional[str] = None
    answer: str
    is_qa: bool
    changed_by: Optional[str] = "Hooman (AI Engineer)"


class ChunkSyncPayload(BaseModel):
    chunk_id: int
    question: Optional[str] = None
    answer: str
    is_qa: bool
    changed_by: Optional[str] = "Hooman (AI Engineer)"


class RevertPayload(BaseModel):
    chunk_id: int
    version_id: int
    changed_by: Optional[str] = "Hooman (AI Engineer)"


def extract_qa_components(content: str) -> dict:
    """Parses text content safely, cleaning up residual bracket or quote anomalies."""
    content_clean = content.strip()

    if content_clean.startswith('[') and content_clean.endswith(']'):
        content_clean = content_clean[1:-1].strip()

    q_match = re.search(r'question\s*:\s*["\']?(.*?)["\']?(?=\s*answer\s*\d*\s*:|\s*question category|$)',
                        content_clean, re.DOTALL | re.IGNORECASE)
    a_match = re.search(r'answer\s*:\s*["\']?(.*?)["\']?$', content_clean, re.DOTALL | re.IGNORECASE)

    if q_match and a_match:
        return {
            "is_qa": True,
            "question": q_match.group(1).strip().strip('"\''),
            "answer": a_match.group(1).strip().strip('"\'')
        }

    return {"is_qa": False, "question": None, "answer": content}


@router.get("/", response_class=HTMLResponse)
async def serve_kb_page(request: Request):
    return templates.TemplateResponse("kb_manager.html", {"request": request})


@router.get("/api/documents")
def api_list_documents():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, title, filename FROM documents ORDER BY title ASC;")
        return {"documents": cursor.fetchall()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.get("/api/chunks/{document_id}")
def api_get_document_chunks(
        document_id: int,
        search: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0)
):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT id, content, chunk_index FROM chunks WHERE document_id = %s"
        params = [document_id]

        if search:
            query += " AND content ILIKE %s"
            params.append(f"%{search}%")

        query += " ORDER BY chunk_index ASC LIMIT %s OFFSET %s;"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        processed_chunks = []
        for row in rows:
            parsed = extract_qa_components(row["content"])
            processed_chunks.append({
                "id": row["id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "is_qa": parsed["is_qa"],
                "question": parsed["question"],
                "answer": parsed["answer"]
            })
        return {"chunks": processed_chunks, "has_more": len(processed_chunks) == limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.post("/api/chunks/create")
def api_create_chunk(payload: ChunkCreatePayload):
    import main
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if payload.is_qa and payload.question:
            reconstructed_content = f"question: {payload.question.strip()}\nanswer: {payload.answer.strip()}"
        else:
            reconstructed_content = payload.answer.strip()

        normalized_content = normalizer.normalize(reconstructed_content)

        if not main.rag_system:
            raise HTTPException(status_code=503, detail="RAG engine encoder is not active.")

        new_vector = main.rag_system.search_engine.embed_documents_sync(
            [normalized_content]
        )[0]

        # Fetch next chunk index safely
        cursor.execute("SELECT COALESCE(MAX(chunk_index), -1) + 1 as next_idx FROM chunks WHERE document_id = %s;",
                       (payload.document_id,))
        next_idx = cursor.fetchone()["next_idx"]

        cursor.execute("SELECT title FROM documents WHERE id = %s;", (payload.document_id,))
        doc_record = cursor.fetchone()
        if not doc_record:
            raise HTTPException(status_code=404, detail="Parent Document missing.")

        now = datetime.utcnow()
        char_count = len(reconstructed_content)
        token_count = len(normalized_content.split())

        # 1. Insert into PostgreSQL chunks
        cursor.execute("""
                       INSERT INTO chunks (document_id, content, chunk_index, char_count, token_count, created_at,
                                           updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                       """, (payload.document_id, reconstructed_content, next_idx, char_count, token_count, now, now))
        new_chunk_id = cursor.fetchone()["id"]

        # 2. Insert into PostgreSQL embeddings
        cursor.execute("""
                       INSERT INTO embeddings (chunk_id, vector, created_at, updated_at)
                       VALUES (%s, %s, %s, %s);
                       """, (new_chunk_id, json.dumps(new_vector), now, now))

        # 3. Create baseline Version 1 trace entry
        cursor.execute("""
                       INSERT INTO chunk_versions (chunk_id, content, changed_by, created_at)
                       VALUES (%s, %s, %s, %s);
                       """, (new_chunk_id, reconstructed_content, payload.changed_by, now))

        # 4. Push to Qdrant cluster vector pipeline
        point = PointStruct(
            id=int(new_chunk_id),
            vector=new_vector,
            payload={
                "chunk_id": int(new_chunk_id),
                "chunk_index": next_idx,
                "document_id": payload.document_id,
                "document": doc_record["title"],
                "content": reconstructed_content,
                "text": reconstructed_content
            }
        )
        main.qdrant_client.upsert(
            collection_name=main.QDRANT_COLLECTION,
            points=[point]
        )

        conn.commit()
        return {"status": "success", "chunk_id": new_chunk_id,
                "message": "Chunk injected successfully across all index layers."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Creation pipeline abort: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@router.put("/api/chunks/update")
def api_sync_chunk(payload: ChunkSyncPayload):
    import main

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if payload.is_qa and payload.question:
            reconstructed_content = f"question: {payload.question.strip()}\nanswer: {payload.answer.strip()}"
        else:
            reconstructed_content = payload.answer.strip()

        normalized_content = normalizer.normalize(reconstructed_content)

        if not main.rag_system:
            raise HTTPException(status_code=503, detail="RAG engine encoder is not active.")

        new_vector = main.rag_system.search_engine.embed_documents_sync(
            [normalized_content]
        )[0]

        cursor.execute("""
                       SELECT c.document_id, c.chunk_index, d.title as doc_title
                       FROM chunks c
                                JOIN documents d ON c.document_id = d.id
                       WHERE c.id = %s;
                       """, (payload.chunk_id,))
        chunk_record = cursor.fetchone()
        if not chunk_record:
            raise HTTPException(status_code=404, detail="Chunk target index missing.")

        now = datetime.utcnow()
        char_count = len(reconstructed_content)
        token_count = len(normalized_content.split())

        # 1. Update core tables
        cursor.execute("""
                       UPDATE chunks
                       SET content     = %s,
                           char_count  = %s,
                           token_count = %s,
                           updated_at  = %s
                       WHERE id = %s;
                       """, (reconstructed_content, char_count, token_count, now, payload.chunk_id))

        cursor.execute("""
                       UPDATE embeddings
                       SET vector     = %s,
                           updated_at = %s
                       WHERE chunk_id = %s;
                       """, (json.dumps(new_vector), now, payload.chunk_id))

        # 2. Append history transaction to versions table tracking matrix
        cursor.execute("""
                       INSERT INTO chunk_versions (chunk_id, content, changed_by, created_at)
                       VALUES (%s, %s, %s, %s);
                       """, (payload.chunk_id, reconstructed_content, payload.changed_by, now))

        # 3. Vector cluster state update
        point = PointStruct(
            id=int(payload.chunk_id),
            vector=new_vector,
            payload={
                "chunk_id": int(payload.chunk_id),
                "chunk_index": chunk_record["chunk_index"],
                "document_id": chunk_record["document_id"],
                "document": chunk_record["doc_title"],
                "content": reconstructed_content,
                "text": reconstructed_content
            }
        )
        main.qdrant_client.upsert(
            collection_name=main.QDRANT_COLLECTION,
            points=[point]
        )

        conn.commit()
        return {"status": "success", "message": "Updated successfully and log trace committed."}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Atomic execution error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@router.delete("/api/chunks/delete/{chunk_id}")
def api_delete_chunk(chunk_id: int):
    import main
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check existence
        cursor.execute("SELECT id FROM chunks WHERE id = %s;", (chunk_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Chunk requested for removal does not exist.")

        # 1. Purge from relational layer (Cascades versioning logs automatically if foreign key is set correctly)
        cursor.execute("DELETE FROM embeddings WHERE chunk_id = %s;", (chunk_id,))
        cursor.execute("DELETE FROM chunk_versions WHERE chunk_id = %s;", (chunk_id,))
        cursor.execute("DELETE FROM chunks WHERE id = %s;", (chunk_id,))

        # 2. Synchronize memory state with Qdrant collection cluster
        main.qdrant_client.delete(
            collection_name=main.QDRANT_COLLECTION,
            points_selector=PointIdsList(points=[int(chunk_id)])
        )

        conn.commit()
        return {"status": "success", "message": "Chunk completely expunged across all semantic indices."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Isolation Purge Failure: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@router.get("/api/chunks/{chunk_id}/versions")
def api_get_chunk_versions(chunk_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
                       SELECT id, content, changed_by, created_at
                       FROM chunk_versions
                       WHERE chunk_id = %s
                       ORDER BY created_at DESC;
                       """, (chunk_id,))
        versions = cursor.fetchall()

        # Parse text variants into readable UI components
        processed = []
        for v in versions:
            parsed = extract_qa_components(v["content"])
            processed.append({
                "id": v["id"],
                "content": v["content"],
                "changed_by": v["changed_by"],
                "created_at": v["created_at"].isoformat(),
                "is_qa": parsed["is_qa"],
                "question": parsed["question"],
                "answer": parsed["answer"]
            })
        return {"versions": processed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.post("/api/chunks/revert")
def api_revert_chunk(payload: RevertPayload):
    import main
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Fetch target version content state
        cursor.execute("SELECT content FROM chunk_versions WHERE id = %s AND chunk_id = %s;",
                       (payload.version_id, payload.chunk_id))
        version_rec = cursor.fetchone()
        if not version_rec:
            raise HTTPException(status_code=404, detail="Target historic state variant missing.")

        target_content = version_rec["content"]
        normalized_content = normalizer.normalize(target_content)

        if not main.rag_system:
            raise HTTPException(status_code=503, detail="RAG system vector module offline.")

        new_vector = main.rag_system.search_engine.embed_documents_sync(
            [normalized_content]
        )[0]

        cursor.execute("""
                       SELECT c.chunk_index, d.title as doc_title, c.document_id
                       FROM chunks c
                                JOIN documents d ON c.document_id = d.id
                       WHERE c.id = %s;
                       """, (payload.chunk_id,))
        chunk_record = cursor.fetchone()

        now = datetime.utcnow()
        char_count = len(target_content)
        token_count = len(normalized_content.split())

        # 1. Override state tracking nodes
        cursor.execute("""
                       UPDATE chunks
                       SET content     = %s,
                           char_count  = %s,
                           token_count = %s,
                           updated_at  = %s
                       WHERE id = %s;
                       """, (target_content, char_count, token_count, now, payload.chunk_id))

        cursor.execute("""
                       UPDATE embeddings
                       SET vector     = %s,
                           updated_at = %s
                       WHERE chunk_id = %s;
                       """, (json.dumps(new_vector), now, payload.chunk_id))

        # 2. Track revert event itself as a fresh historical version milestone entry
        cursor.execute("""
                       INSERT INTO chunk_versions (chunk_id, content, changed_by, created_at)
                       VALUES (%s, %s, %s, %s);
                       """, (payload.chunk_id, target_content, f"Reverted by {payload.changed_by}", now))

        # 3. Synchronize vector payload cluster state context
        point = PointStruct(
            id=int(payload.chunk_id),
            vector=new_vector,
            payload={
                "chunk_id": int(payload.chunk_id),
                "chunk_index": chunk_record["chunk_index"],
                "document_id": chunk_record["document_id"],
                "document": chunk_record["doc_title"],
                "content": target_content,
                "text": target_content
            }
        )
        main.qdrant_client.upsert(
            collection_name=main.QDRANT_COLLECTION,
            points=[point]
        )

        conn.commit()
        return {"status": "success", "message": "State successfully rolled back."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Reversion Pipeline Error: {str(e)}")
    finally:
        cursor.close()
        conn.close()
