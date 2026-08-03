from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from utils.concurrency import run_with_limit
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.service_errors import ServiceError, ServiceTimeoutError
from answering_service import AnswerRequestContext

mobile_router = APIRouter(prefix="/api/mobile", tags=["Gateway API (Internal)"])
REQUEST_TIMEOUT_SECONDS = (
    PERFORMANCE_SETTINGS.application_request_timeout_seconds
)


# ==========================================
# SAFE DATABASE AUXILIARY LOOKUP
# ==========================================


# ==========================================
# STREAMLINED SCHEMA DEFINITIONS
# ==========================================
class TalkRequest(BaseModel):
    session_id: str
    query: str
    national_code: str  # Mandatory identifier provided by the Gateway
    documents: List[str] = ["General_FAQ"]


class TalkResponse(BaseModel):
    query_id: str
    session_id: str
    query: str
    answer: str
    related_questions: List[Dict[str, str]]
    feedback_needed: bool


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: Optional[str]
    is_helpful: Optional[int] = None


class FeedbackRequest(BaseModel):
    is_helpful: Optional[int] = None


class CommentRequest(BaseModel):
    comment: str


class SatisfactionRequest(BaseModel):
    satisfied: bool


# ==========================================
# DEPENDENCY INJECTION
# ==========================================
def get_services(request: Request):
    app = request.app
    if not hasattr(app.state, 'agent_service'):
        raise HTTPException(status_code=503, detail="AI Core Services are currently unavailable.")
    return (
        app.state.agent_service,
        app.state.chat_manager,
        app.state.intent_classifier,
        app.state.history_rewriting_service
    )


# ==========================================
# CORE GATEWAY ENDPOINTS (No Auth Required)
# ==========================================

@mobile_router.post("/v1/talk", response_model=TalkResponse)
async def gateway_talk(req: TalkRequest, request: Request):
    async def operation():
        return await _gateway_talk(req, request)

    try:
        return await asyncio.wait_for(
            run_with_limit(
                request.app.state.request_limiter,
                operation,
                acquire_timeout=(
                    PERFORMANCE_SETTINGS.request_admission_timeout_seconds
                ),
            ),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise ServiceTimeoutError(
            f"AI request exceeded the {REQUEST_TIMEOUT_SECONDS:g}-second "
            "total deadline"
        ) from exc


async def _gateway_talk(req: TalkRequest, request: Request):
    if not req.query or not req.session_id or not req.national_code:
        raise HTTPException(status_code=400, detail="session_id, query, and national_code are required.")

    agent_service, chat_manager, intent_classifier, history_rewriting_service = get_services(request)
    answering_service = request.app.state.answering_service
    blocking_runner = request.app.state.blocking_runner

    # JIT Provisioning Lookup: Automatically handles new users seamlessly
    user_row = await blocking_runner.run(
        chat_manager.db.get_or_create_user_by_national_code, req.national_code
    )
    if not user_row:
        raise HTTPException(status_code=500, detail="Database failure: Could not provision user profile.")
    user_id = user_row["id"]

    try:
        # Resolve mobile UUID to internal integer session ID
        session_obj = await blocking_runner.run(
            chat_manager.resolve_mobile_session,
            user_id,
            req.session_id,
            wait_for_completion_on_cancel=True,
        )
        internal_session_id = session_obj["id"] if isinstance(session_obj, dict) else session_obj

        # Append Transaction Log
        user_msg = await blocking_runner.run(
            chat_manager.add_message,
            str(internal_session_id),
            "user",
            req.query,
            user_id=user_id,
            wait_for_completion_on_cancel=True,
        )
        if not user_msg:
            raise HTTPException(status_code=500, detail="Failed to save user transaction message")

        # Process via AI Agent System
        result = await answering_service.answer(
            AnswerRequestContext(
                original_query=req.query,
                session_id=str(internal_session_id),
                selected_documents=tuple(req.documents),
                channel="mobile",
                use_history=True,
                persist_agent_state=True,
                include_related_questions=True,
            )
        )
        answer = result.answer
        if not answer:
            answer = "متاسفانه پاسخی دریافت نشد."

        ai_msg = await blocking_runner.run(
            chat_manager.add_message,
            str(internal_session_id),
            "assistant",
            answer,
            user_id=user_id,
            query_id=int(user_msg["id"]),
            wait_for_completion_on_cancel=True,
        )

        # Extract Session Metadata Meta Attributes
        # FAQ related questions are already reranked once by the agent graph.
        import main
        current_category = (
            main.get_document_category(req.documents[0])
            if req.documents
            else "general"
        )
        related_questions = (
            result.related_questions
            if current_category == "FAQ"
            else []
        )

        feedback_needed = result.feedback_needed

        return TalkResponse(
            query_id=str(ai_msg["id"]) if ai_msg else "unknown",
            session_id=req.session_id,
            query=req.query,
            answer=answer,
            related_questions=related_questions,
            feedback_needed=feedback_needed
        )
    except (HTTPException, ServiceError):
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Internal AI Engine Error"
        ) from exc


@mobile_router.get("/v1/history")
async def gateway_history(
        request: Request,
        national_code: str,
        session_id: Optional[str] = None
):
    """Fetches history strictly via national code validation from the gateway."""
    _, chat_manager, _, _ = get_services(request)
    blocking_runner = request.app.state.blocking_runner

    user_row = await blocking_runner.run(
        chat_manager.db.get_or_create_user_by_national_code, national_code
    )
    if not user_row:
        raise HTTPException(status_code=500, detail="Database failure: Could not provision user profile.")
    user_id = user_row["id"]

    # SCENARIO A: Only national_code provided -> Return all active sessions
    if not session_id:
        sessions_dict = await blocking_runner.run(
            chat_manager.get_user_sessions, user_id
        )
        return {
            "national_code": national_code,
            "sessions": list(sessions_dict.values()) if sessions_dict else []
        }

    # SCENARIO B: session_id is provided -> Return specific message thread
    try:
        session_obj = await blocking_runner.run(
            chat_manager.resolve_mobile_session,
            user_id,
            session_id,
            wait_for_completion_on_cancel=True,
        )
        internal_session_id = session_obj["id"] if isinstance(session_obj, dict) else session_obj
        raw_messages = await blocking_runner.run(
            chat_manager.get_messages, internal_session_id
        )

        return {
            "session_id": session_id,
            "messages": [MessageItem(**msg) for msg in raw_messages] if raw_messages else []
        }
    except (HTTPException, ServiceError):
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Failed to retrieve history"
        ) from exc


@mobile_router.post("/v1/queries/{query_id}/feedback")
async def gateway_feedback(query_id: int, req: FeedbackRequest):
    from main import blocking_runner, db_manager
    result = await blocking_runner.run(
        db_manager.update_query_feedback,
        query_id,
        req.is_helpful,
        wait_for_completion_on_cancel=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Query not found")
    return {"status": "success", "query_id": result["id"], "is_helpful": result["is_helpful"]}


@mobile_router.post("/v1/queries/{query_id}/comment")
async def gateway_comment(query_id: int, req: CommentRequest):
    from main import blocking_runner, db_manager
    result = await blocking_runner.run(
        db_manager.update_query_comment,
        query_id,
        req.comment,
        wait_for_completion_on_cancel=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Query not found")
    return {"status": "success", "query_id": result["id"]}


@mobile_router.post("/v1/sessions/{session_id}/satisfaction")
async def gateway_satisfaction(session_id: str, req: SatisfactionRequest, request: Request):
    agent_service, chat_manager, _, _ = get_services(request)
    blocking_runner = request.app.state.blocking_runner

    # We resolve the DB session via UUID to locate the true owner user_id
    from main import db_manager
    session_row = await blocking_runner.run(
        db_manager.get_session_by_uuid, session_id
    )
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")

    internal_session_id = session_row["id"]
    user_id = session_row["user_id"]

    meta = await blocking_runner.run(
        chat_manager.db.get_session_metadata, int(internal_session_id)
    )
    state = meta.get("agent_state")

    if not state or not state.get("feedback_needed"):
        raise HTTPException(status_code=400, detail="No pending satisfaction request")

    if req.satisfied:
        confirmation_text = "خوشحالیم که تونستیم کمک کنیم."
    else:
        confirmation_text = "متاسفیم. درخواست شما ثبت شد و کارشناسان ما در اسرع وقت با شما تماس می‌گیرند."
        await blocking_runner.run(
            agent_service._create_ticket,
            user_id,
            internal_session_id,
            wait_for_completion_on_cancel=True,
        )

    state["feedback_needed"] = False
    state["asked_feedback"] = True
    state.setdefault("messages", []).append({
        "role": "assistant",
        "content": confirmation_text
    })
    meta["agent_state"] = state
    await blocking_runner.run(
        chat_manager.db.update_session_metadata,
        int(internal_session_id),
        meta,
        wait_for_completion_on_cancel=True,
    )

    return {"status": "success", "confirmation": confirmation_text}
