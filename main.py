import asyncio
import os
import json
import html
import shutil
import tempfile
import textwrap
import httpx
import sys
import threading
import uuid
import logging
from dotenv import load_dotenv

# Load variables from .env into os.environ
load_dotenv()

import pandas as pd
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Request, Depends, HTTPException, File, UploadFile, Form, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.background import BackgroundTasks
from pydantic import BaseModel
from openai import AsyncOpenAI
from psycopg2 import Error as PostgresError

# Core Architecture Imports
from new_architecture.app.config import Config
from new_architecture.app.services.history.database import DatabaseManager, ChatManager
from new_architecture.app.services.history.rewriting import HistoryRewritingService
from new_architecture.app.services.db_connection import DatabaseConnections
from new_architecture.app.services.authentication import AuthenticationService

# AI & Domain Service Layers
from utils.RagSystem import RAGSystem
from intent_classifier import IntentClassifier
from agent_service import AgentService
from answering_service import AnsweringService, AnswerRequestContext
from mass_answer_service import MassAnswerProcessor
from mass_answer_jobs import MassAnswerJobManager
from mass_answer_files import (
    MassAnswerFileError,
    parse_mass_answer_file,
    read_upload_limited,
    write_safe_output,
)
from kb_manager import router as kb_router

from utils.persian_hybrid_search import PersianTextProcessor
from utils.concurrency import BoundedBlockingRunner, run_with_limit
from utils.service_errors import ServiceError, ServiceUnavailableError
from utils.client_lifecycle import SerializedClient
from utils.performance_config import PERFORMANCE_SETTINGS

class Config:
    """Configuration"""

    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = os.getenv("QDRANT_PORT", 6333)
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hihelp_embeddings")
    QDRANT_VECTOR_SIZE = os.getenv("QDRANT_VECTOR_SIZE", 1024)
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_HTTPS = os.getenv("QDRANT_HTTPS", "false").lower() == "true"

# Optional OCR Fallback Integration
try:
    from ocr_service import OCRService
except ImportError:
    OCRService = None

# Mobile Integration Modules
from mobile_api import mobile_router

REQUEST_TIMEOUT_SECONDS = (
    PERFORMANCE_SETTINGS.application_request_timeout_seconds
)
REQUEST_ADMISSION_TIMEOUT_SECONDS = (
    PERFORMANCE_SETTINGS.request_admission_timeout_seconds
)
REQUEST_CONCURRENCY_LIMIT = PERFORMANCE_SETTINGS.request_concurrency_limit
BLOCKING_CONCURRENCY_LIMIT = PERFORMANCE_SETTINGS.blocking_concurrency_limit

# ----------------------------------------------------------------------
# Banking Custom Exception Standards (Compliance: Chatbot.pdf)
# ----------------------------------------------------------------------
class BankException(Exception):
    """Custom exception class to enforce uniform banking error schemas."""

    def __init__(self, error_code: str, error_desc: str, status_code: int = 400):
        self.error_code = error_code
        self.error_desc = error_desc
        self.status_code = status_code


# ----------------------------------------------------------------------
# Config & Vector Client Initialization
# ----------------------------------------------------------------------


QDRANT_HOST = Config.QDRANT_HOST
QDRANT_PORT = Config.QDRANT_PORT
QDRANT_COLLECTION = Config.QDRANT_COLLECTION

qdrant_client = None

#QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=os.getenv("QDRANT_API_KEY"), https=os.getenv("QDRANT_HTTPS"))


# ----------------------------------------------------------------------
# Pydantic Data Models (Web Interface API)
# ----------------------------------------------------------------------
class SessionCreateRequest(BaseModel):
    title: str = "New Chat"


class MessageRequest(BaseModel):
    role: str
    content: str


class LoginRequest(BaseModel):
    username: str
    password: str


class QueryRequest(BaseModel):
    query: str
    documents: List[str] = []
    top_k: int = 10
    alpha: float = 0.3
    session_id: Optional[int] = None
    uploaded_text: Optional[str] = None


class InitRequest(BaseModel):
    directory_path: str


class FeedbackRequest(BaseModel):
    is_helpful: Optional[int] = None


class CommentRequest(BaseModel):
    comment: str


class SatisfactionRequest(BaseModel):
    satisfied: bool


# ----------------------------------------------------------------------
# Global App State & Global References
# ----------------------------------------------------------------------
rag_system = None
available_documents = []
chunker = None
ocr_service = None
history_rewriting_service = None
user = None

agent_service = None
answering_service = None
mass_answer_processor = None
mass_answer_job_manager = None
mass_answer_logger = logging.getLogger("mass_answer")
intent_classifier = None
scenarios_db = None
chat_manager = None
authentication_service = None
db_connections = None
text_processor = None
blocking_runner = None
request_limiter = None
tei_http_client = None
tei_sync_http_client = None
llm_client = None
ocr_inference_lock = threading.Lock()

# db_manager = DatabaseManager(host="localhost", port=5432, dbname="hihelp_db", user="postgres", password="postgres")
db_manager = DatabaseManager(host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"), dbname=os.getenv("POSTGRES_DB"),
                             user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"))


def get_document_category(doc_name: str) -> str:
    """Categorizes documents to guide downstream domain-specific RAG prompts."""
    if "قرارداد" in doc_name:
        return "قرارداد ها"
    elif "ابلاغیه" in doc_name:
        return "ابلاغیه ها"
    elif "FAQ" in doc_name:
        return "FAQ"
    else:
        import hashlib
        h = hashlib.md5(doc_name.encode()).hexdigest()
        return "قرارداد ها" if int(h[0], 16) < 8 else "ابلاغیه ها"


# ----------------------------------------------------------------------
# Modern Lifespan Event Context Manager (FastAPI Best Practice)
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_connections, authentication_service
    global rag_system, available_documents, chunker, history_rewriting_service, ocr_service
    global intent_classifier, scenarios_db, agent_service, answering_service, mass_answer_processor, mass_answer_job_manager, chat_manager
    global text_processor, qdrant_client, blocking_runner, request_limiter
    global tei_http_client, tei_sync_http_client, llm_client

    blocking_runner = BoundedBlockingRunner(BLOCKING_CONCURRENCY_LIMIT)
    request_limiter = asyncio.Semaphore(REQUEST_CONCURRENCY_LIMIT)
    app.state.ready = False
    try:
        text_processor = await blocking_runner.run(
            PersianTextProcessor, use_stemming=False
        )

        db_connections = DatabaseConnections()
        connected = await blocking_runner.run(
            db_connections.connect_all,
            wait_for_completion_on_cancel=True,
        )
        if not connected:
            raise RuntimeError("Failed to initialize required database services")
        qdrant_client = SerializedClient(db_connections.qdrant_client)
        db_connections.qdrant_client = qdrant_client
        authentication_service = AuthenticationService(db_manager)

        await blocking_runner.run(
            db_manager.init_db, wait_for_completion_on_cancel=True
        )
        chat_manager = ChatManager(db_manager)

        documents = await blocking_runner.run(
            db_manager.get_available_documents
        )
        available_documents = [doc["title"] for doc in documents]

        from utils.rag_utils import chunk_fetcher_factory
        chunk_fetcher = chunk_fetcher_factory(db_manager)

        tei_timeout = httpx.Timeout(
            connect=PERFORMANCE_SETTINGS.tei_http_connect_timeout_seconds,
            read=PERFORMANCE_SETTINGS.tei_http_read_timeout_seconds,
            write=PERFORMANCE_SETTINGS.tei_http_write_timeout_seconds,
            pool=PERFORMANCE_SETTINGS.tei_http_pool_timeout_seconds,
        )
        tei_limits = httpx.Limits(
            max_connections=PERFORMANCE_SETTINGS.tei_http_max_connections,
            max_keepalive_connections=(
                PERFORMANCE_SETTINGS.tei_http_max_keepalive_connections
            ),
            keepalive_expiry=(
                PERFORMANCE_SETTINGS.tei_http_keepalive_expiry_seconds
            ),
        )
        tei_http_client = httpx.AsyncClient(
            timeout=tei_timeout, limits=tei_limits
        )
        tei_sync_http_client = httpx.Client(
            timeout=tei_timeout, limits=tei_limits
        )
        vllm_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=(
                    PERFORMANCE_SETTINGS.vllm_http_connect_timeout_seconds
                ),
                read=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds,
                write=PERFORMANCE_SETTINGS.vllm_http_write_timeout_seconds,
                pool=PERFORMANCE_SETTINGS.vllm_http_pool_timeout_seconds,
            ),
            limits=httpx.Limits(
                max_connections=(
                    PERFORMANCE_SETTINGS.vllm_http_max_connections
                ),
                max_keepalive_connections=(
                    PERFORMANCE_SETTINGS.vllm_http_max_keepalive_connections
                ),
                keepalive_expiry=(
                    PERFORMANCE_SETTINGS.vllm_http_keepalive_expiry_seconds
                ),
            ),
        )
        llm_client = AsyncOpenAI(
            base_url=os.getenv("VLLM_URL", "http://localhost:8000/v1"),
            api_key="vllm-token-not-needed",
            timeout=httpx.Timeout(
                connect=(
                    PERFORMANCE_SETTINGS.vllm_http_connect_timeout_seconds
                ),
                read=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds,
                write=PERFORMANCE_SETTINGS.vllm_http_write_timeout_seconds,
                pool=PERFORMANCE_SETTINGS.vllm_http_pool_timeout_seconds,
            ),
            max_retries=0,
            http_client=vllm_http_client,
        )

        rag_system = await blocking_runner.run(
            RAGSystem,
            qdrant_client=qdrant_client,
            chunk_fetcher=chunk_fetcher,
            llm_client=llm_client,
            tei_http_client=tei_http_client,
            tei_sync_http_client=tei_sync_http_client,
            blocking_runner=blocking_runner,
        )
        history_rewriting_service = HistoryRewritingService(
            rag_system, db_manager
        )

        try:
            if OCRService:
                ocr_service = await blocking_runner.run(OCRService)
        except Exception:
            ocr_service = None

        def load_scenarios():
            with open("scenarios.json", "r", encoding="utf-8") as stream:
                return {
                    scenario["id"]: scenario
                    for scenario in json.load(stream)["scenarios"]
                }

        scenarios_db = await blocking_runner.run(load_scenarios)
        intent_classifier = await blocking_runner.run(
            IntentClassifier,
            embedding_model=rag_system.search_engine._encode_query,
            scenarios_path="scenarios.json",
            blocking_runner=blocking_runner,
        )

        agent_service = await blocking_runner.run(
            AgentService,
            rag_system=rag_system,
            intent_classifier=intent_classifier,
            scenarios_db=scenarios_db,
            db_manager=db_manager,
            chat_manager=chat_manager,
            blocking_runner=blocking_runner,
            category_resolver=get_document_category,
        )

        answering_service = AnsweringService(
            agent_service=agent_service,
            intent_classifier=intent_classifier,
            history_rewriting_service=history_rewriting_service,
            text_processor=text_processor,
            blocking_runner=blocking_runner,
            category_resolver=get_document_category,
        )
        mass_answer_processor = MassAnswerProcessor(
            answering_service=answering_service,
            row_concurrency=(
                PERFORMANCE_SETTINGS.mass_answer_row_concurrency
            ),
            row_timeout_seconds=(
                PERFORMANCE_SETTINGS.mass_answer_row_timeout_seconds
            ),
        )
        mass_answer_job_manager = MassAnswerJobManager()

        app.state.agent_service = agent_service
        app.state.answering_service = answering_service
        app.state.mass_answer_processor = mass_answer_processor
        app.state.mass_answer_job_manager = mass_answer_job_manager
        app.state.chat_manager = chat_manager
        app.state.authentication_service = authentication_service
        app.state.intent_classifier = intent_classifier
        app.state.history_rewriting_service = history_rewriting_service
        app.state.blocking_runner = blocking_runner
        app.state.request_limiter = request_limiter
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        active_exception = sys.exc_info()[1]
        cleanup_errors = []

        async def cleanup(operation):
            try:
                await operation()
            except Exception as exc:
                cleanup_errors.append(exc)

        if mass_answer_job_manager is not None:
            await cleanup(mass_answer_job_manager.aclose)
        if rag_system is not None:
            await cleanup(rag_system.aclose)
        if llm_client is not None:
            await cleanup(llm_client.close)
        if tei_http_client is not None:
            await cleanup(tei_http_client.aclose)
        if tei_sync_http_client is not None and blocking_runner is not None:
            await cleanup(
                lambda: blocking_runner.run(tei_sync_http_client.close)
            )
        if db_connections is not None and blocking_runner is not None:
            await cleanup(
                lambda: blocking_runner.run(
                    db_connections.close_all,
                    wait_for_completion_on_cancel=True,
                )
            )
        if blocking_runner is not None:
            await cleanup(blocking_runner.aclose)

        for name in (
            "agent_service",
            "answering_service",
            "mass_answer_processor",
            "mass_answer_job_manager",
            "chat_manager",
            "authentication_service",
            "intent_classifier",
            "history_rewriting_service",
            "blocking_runner",
            "request_limiter",
        ):
            if hasattr(app.state, name):
                delattr(app.state, name)

        qdrant_client = None
        rag_system = None
        llm_client = None
        tei_http_client = None
        tei_sync_http_client = None
        db_connections = None
        blocking_runner = None
        request_limiter = None
        agent_service = None
        answering_service = None
        mass_answer_processor = None
        mass_answer_job_manager = None
        chat_manager = None
        authentication_service = None
        intent_classifier = None
        history_rewriting_service = None
        ocr_service = None
        text_processor = None
        if cleanup_errors and active_exception is None:
            raise RuntimeError("One or more resources failed to close") from (
                cleanup_errors[0]
            )


# ----------------------------------------------------------------------
# FastAPI App Engine Instance Setup
# ----------------------------------------------------------------------
app = FastAPI(
    title="Persian RAG + Agent System (Hi Bank Edition)",
    version="2.2.0",
    lifespan=lifespan
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# Mount API Routers
app.include_router(kb_router)
app.include_router(mobile_router)


# --- GLOBAL BUSINESS RECOVERY EXCEPTION HANDLER FOR BANK STANDARDS ---
@app.exception_handler(BankException)
async def bank_exception_handler(request: Request, exc: BankException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "errorCode": exc.error_code,
            "errorDesc": exc.error_desc,
            "errorDetails": {
                "timestamp": datetime.utcnow().isoformat(),
                "requestId": request.headers.get("X-Request-Id", "unknown_request"),
                "message": str(exc.error_desc),
                "exception": "BankException",
                "details": None
            }
        }
    )


@app.exception_handler(ServiceError)
async def service_exception_handler(request: Request, exc: ServiceError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "errorCode": exc.error_code,
            "errorDesc": exc.public_message,
            "errorDetails": {
                "timestamp": datetime.utcnow().isoformat(),
                "requestId": request.headers.get(
                    "X-Request-Id", "unknown_request"
                ),
                "message": exc.public_message,
                "exception": type(exc).__name__,
                "details": None,
            },
        },
    )


# ----------------------------------------------------------------------
# Mobile API Endpoint - Secure Token Exchange via National Code
# ----------------------------------------------------------------------
from pydantic import BaseModel


class MobileLoginRequest(BaseModel):
    national_code: str  # Varchar2(20)



# ----------------------------------------------------------------------
# Web Interface Endpoints - Administration & Portal Authentication
# ----------------------------------------------------------------------
@app.post("/api/login")
async def login(req: LoginRequest):
    global user
    user = await blocking_runner.run(
        authentication_service.authenticate,
        req.username,
        req.password,
        wait_for_completion_on_cancel=True,
    )
    if user:
        user["success"] = True
        return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})


# ----------------------------------------------------------------------
# Document Directory Processing & Index Discovery
# ----------------------------------------------------------------------
@app.post("/api/initialize")
async def initialize_system(init_req: InitRequest):
    global available_documents
    try:
        documents = await blocking_runner.run(
            db_manager.get_available_documents
        )
        available_documents = [doc["title"] for doc in documents]
        return {
            "status": "success",
            "message": f"Initialized with {len(available_documents)} docs",
            "documents": available_documents,
            "total_chunks": await blocking_runner.run(
                db_manager.get_number_of_chunks
            )
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/api/documents")
async def get_documents():
    if not available_documents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System not initialized")
    docs_with_category = [{"name": doc, "category": get_document_category(doc)} for doc in available_documents]
    categories = list(set(c["category"] for c in docs_with_category))
    return {"documents": docs_with_category, "count": len(docs_with_category), "categories": categories}


# ----------------------------------------------------------------------
# Core AI Query Cognitive Engine Execution (Web Version Flow)
# ----------------------------------------------------------------------
@app.post("/api/query")
async def query_documents(query_req: QueryRequest, request: Request):
    async def operation():
        try:
            return await asyncio.wait_for(
                _query_documents(query_req), timeout=REQUEST_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            from utils.service_errors import ServiceTimeoutError
            raise ServiceTimeoutError(
                "AI request exceeded the 50-second deadline"
            ) from exc

    return await run_with_limit(
        request.app.state.request_limiter,
        operation,
        acquire_timeout=REQUEST_ADMISSION_TIMEOUT_SECONDS,
    )


async def _query_documents(query_req: QueryRequest):
    global answering_service, chat_manager
    if agent_service is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent not initialized")

    session_id = str(query_req.session_id)
    
    original_query = str(query_req.query).strip()

    # Log incoming user message interaction
    user_msg = await blocking_runner.run(
        chat_manager.add_message,
        session_id,
        "user",
        original_query,
        wait_for_completion_on_cancel=True,
    )


    if not user_msg:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to save user transaction message")

    # Send optimized state to LangGraph engine turn layer
    result = await answering_service.answer(
        AnswerRequestContext(
            original_query=original_query,
            session_id=session_id,
            selected_documents=tuple(query_req.documents),
            channel="web",
            use_history=True,
            persist_agent_state=True,
            include_related_questions=True,
        )
    )
    normalized_query = result.normalized_query
    answer = result.answer

    if answer is None:
        answer = "متاسفانه پاسخی دریافت نشد. لطفاً دوباره تلاش کنید."

    ai_msg = await blocking_runner.run(
        chat_manager.add_message,
        session_id,
        "assistant",
        answer,
        query_id=int(user_msg["id"]),
        wait_for_completion_on_cancel=True,
    )

    query_id = ai_msg["id"] if ai_msg else None

    # Sync and build updated frontend notification states from conversation context metadata
    current_category = get_document_category(query_req.documents[0]) if query_req.documents else "general"

    # FAQ related questions are already reranked once by the agent graph.
    related_questions = (
        result.related_questions
        if current_category == "FAQ"
        else []
    )

    feedback_needed = result.feedback_needed

    return {
        "status": "success",
        "query": original_query,
        "answer": answer,
        "query_id": query_id,
        "related_questions": related_questions,
        "feedback_needed": feedback_needed,
    }


# ----------------------------------------------------------------------
# Session Management & Interaction History Subsystem
# ----------------------------------------------------------------------
@app.get("/api/sessions")
async def get_sessions():
    global user
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    sessions_dict = await blocking_runner.run(
        chat_manager.get_user_sessions, user["id"]
    )
    if not sessions_dict:
        new_session = await blocking_runner.run(
            chat_manager.create_new_chat,
            user["id"],
            model_name="",
            temperature=0.7,
            wait_for_completion_on_cancel=True,
        )
        sessions_dict = {new_session["id"]: new_session}
    return {"sessions": list(sessions_dict.values())}


@app.post("/api/sessions")
async def create_session(req: SessionCreateRequest):
    global user
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return await blocking_runner.run(
        chat_manager.create_new_chat,
        user["id"],
        model_name="",
        temperature=0.7,
        wait_for_completion_on_cancel=True,
    )


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = await blocking_runner.run(
        chat_manager.get_session, session_id
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@app.post("/api/sessions/{session_id}/message")
async def add_message(session_id: str, req: MessageRequest):
    msg = await blocking_runner.run(
        chat_manager.add_message,
        session_id,
        req.role,
        req.content,
        wait_for_completion_on_cancel=True,
    )
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return msg


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    msgs = await blocking_runner.run(
        chat_manager.get_messages, session_id
    )
    return {"messages": msgs if msgs else []}


@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str):
    try:
        await blocking_runner.run(
            chat_manager.delete_chat,
            session_id,
            wait_for_completion_on_cancel=True,
        )
        return {"success": True, "message": "Session deleted"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.patch("/api/sessions/{session_id}/pin")
async def toggle_pin_session(session_id: str):
    try:
        updated = await blocking_runner.run(
            chat_manager.toggle_pin,
            session_id,
            wait_for_completion_on_cancel=True,
        )
        return {"success": True, "message": "Pin status updated", "session": updated}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ----------------------------------------------------------------------
# Automated HTML Exporter & Responsive Session Downloader
# ----------------------------------------------------------------------
@app.get("/api/sessions/{session_id}/download")
async def download_session_html(session_id: str):
    session = await blocking_runner.run(
        chat_manager.get_session, session_id
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages = await blocking_runner.run(
        chat_manager.get_messages, session_id
    )

    def escape_text(text: str) -> str:
        return html.escape(text)

    title = escape_text(session.get("title", f"Session {session_id}"))
    created = session.get("created_at", "")
    if created:
        try:
            dt = datetime.fromisoformat(str(created))
            created_display = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            created_display = str(created)
    else:
        created_display = ""

    msg_rows = ""
    for m in messages:
        role = escape_text(m.get("role", "unknown"))
        content = escape_text(m.get("content", ""))
        timestamp = m.get("created_at", "")
        if timestamp:
            try:
                ts = datetime.fromisoformat(str(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts = str(timestamp)
        else:
            ts = ""
        msg_rows += f"""
        <div class="message message--{role}">
            <div class="role">{role}</div>
            <div class="content">{content}</div>
            <div class="timestamp">{ts}</div>
        </div>"""

    html_content = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Chat History – {title}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #f9fafb; margin: 2rem; color: #111827; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
  .meta {{ color: #6b7280; font-size: 0.9rem; margin-bottom: 2rem; }}
  .chat-history {{ display: flex; flex-direction: column; gap: 1rem; max-width: 800px; }}
  .message {{ padding: 1rem; border-radius: 0.75rem; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .message--user {{ background: #eff6ff; }}
  .message--assistant {{ background: #ecfdf5; }}
  .role {{ font-weight: 600; text-transform: uppercase; font-size: 0.75rem; margin-bottom: 0.25rem; color: #6b7280; }}
  .content {{ white-space: pre-wrap; word-break: break-word; font-size: 0.95rem; line-height: 1.6; }}
  .timestamp {{ font-size: 0.7rem; color: #9ca3af; margin-top: 0.5rem; }}
</style>
</head>
<body>
<h1>Chat History – {title}</h1>
<div class="meta">Created: {created_display}</div>
<div class="chat-history">
{msg_rows}
</div>
</body>
</html>"""

    headers = {"Content-Disposition": f"attachment; filename=session_{session_id}.html"}
    return HTMLResponse(content=html_content, headers=headers)


# ----------------------------------------------------------------------
# Quality Feedback & Support Ticket Dispatch Control Layers
# ----------------------------------------------------------------------
@app.patch("/api/queries/{query_id}/feedback")
async def submit_feedback(query_id: int, req: FeedbackRequest):
    result = await blocking_runner.run(
        db_manager.update_query_feedback,
        query_id,
        req.is_helpful,
        wait_for_completion_on_cancel=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query transaction record not found")
    return {"status": "success", "query_id": result["id"], "is_helpful": result["is_helpful"]}


@app.patch("/api/queries/{query_id}/comment")
async def submit_comment(query_id: int, req: CommentRequest):
    result = await blocking_runner.run(
        db_manager.update_query_comment,
        query_id,
        req.comment,
        wait_for_completion_on_cancel=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query transaction record not found")
    return {"status": "success", "query_id": result["id"], "meta_data": result["meta_data"]}


@app.post("/api/sessions/{session_id}/satisfaction")
async def session_satisfaction(session_id: str, req: SatisfactionRequest):
    global agent_service, db_manager
    session_pk = int(session_id)

    meta = await blocking_runner.run(
        db_manager.get_session_metadata, session_pk
    )
    state = meta.get("agent_state")
    if not state or not state.get("feedback_needed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No pending satisfaction verification loops active")

    user_id = state.get("user_id")
    if not user_id:
        session_row = await blocking_runner.run(
            db_manager.get_session_by_id, session_pk
        )
        if not session_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target session reference missing")
        user_id = session_row["user_id"]

    if req.satisfied:
        confirmation_text = "خوشحالیم که تونستیم کمک کنیم."
    else:
        confirmation_text = "متاسفیم. درخواست شما ثبت شد و کارشناسان ما در اسرع وقت با شما تماس می‌گیرند."
        await blocking_runner.run(
            agent_service._create_ticket,
            user_id,
            session_id,
            wait_for_completion_on_cancel=True,
        )

    state["feedback_needed"] = False
    state["asked_feedback"] = True
    state.setdefault("messages", []).append({
        "role": "assistant",
        "content": confirmation_text
    })
    state["messages"] = state["messages"][-10:]
    meta["agent_state"] = state
    await blocking_runner.run(
        db_manager.update_session_metadata,
        session_pk,
        meta,
        wait_for_completion_on_cancel=True,
    )

    return {"status": "success", "confirmation": confirmation_text}


# ----------------------------------------------------------------------
# Optical Character Recognition (OCR) Engine Routing Layer
# ----------------------------------------------------------------------
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif', '.webp'}
SUPPORTED_PDF_EXTENSION = '.pdf'


@app.get("/api/ocr/status")
async def ocr_status():
    return {
        "available": ocr_service is not None,
        "supported_image_formats": list(SUPPORTED_IMAGE_EXTENSIONS),
        "supported_document_formats": [SUPPORTED_PDF_EXTENSION],
        "message": "OCR service is ready" if ocr_service else "OCR service not initialized"
    }


@app.post("/api/ocr/extract")
async def extract_text_ocr(file: UploadFile = File(...)):
    if ocr_service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OCR service not available")

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in SUPPORTED_IMAGE_EXTENSIONS and file_ext != SUPPORTED_PDF_EXTENSION:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported payload format: {file_ext}")

    content = await file.read()

    def extract_in_worker():
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        try:
            with open(temp_path, "wb") as buffer:
                buffer.write(content)
            with ocr_inference_lock:
                if file_ext == SUPPORTED_PDF_EXTENSION:
                    return ocr_service.pdf2image(temp_path), "PDF"
                return ocr_service.predict(temp_path), "Image"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        text, file_type = await blocking_runner.run(extract_in_worker)

        if text is None:
            text = ""
        if isinstance(text, list):
            text = "\n\n".join(str(item) for item in text)

        text = str(text)
        return {
            "status": "success",
            "filename": file.filename,
            "file_type": file_type,
            "extracted_text": text,
            "statistics": {"word_count": len(text.split()), "character_count": len(text)}
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OCR extraction failed",
        ) from exc


# ----------------------------------------------------------------------
# Asynchronous Mass Batch Processing Pipeline Engine
# ----------------------------------------------------------------------
@app.post("/api/mass-answer")
async def process_mass_answer(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        selected_docs: str = Form("[]")
):
    df, question_col, docs_list, ext, filename = await _read_mass_answer_input(
        file, selected_docs
    )
    if len(df.index) > PERFORMANCE_SETTINGS.mass_answer_direct_max_rows:
        return await _create_mass_answer_job(
            df=df,
            question_col=question_col,
            docs_list=docs_list,
            ext=ext,
            filename=filename,
        )
    return await _process_mass_answer(
        background_tasks,
        df=df,
        question_col=question_col,
        docs_list=docs_list,
        ext=ext,
        filename=filename,
    )


async def _read_mass_answer_input(file: UploadFile, selected_docs: str):
    if mass_answer_processor is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RAG engine array not configured")

    try:
        raw_docs = json.loads(selected_docs)
        docs_list = []
        for doc in raw_docs:
            if isinstance(doc, dict):
                title = doc.get("title", doc.get("name", ""))
                if title:
                    docs_list.append(title.strip())
            elif isinstance(doc, str):
                docs_list.append(doc.strip())
    except Exception:
        docs_list = []

    if not docs_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No documents selected. Please select at least one document in the chat page before uploading the batch file."
        )

    filename = os.path.basename(file.filename or "batch")
    try:
        contents = await read_upload_limited(
            file,
            max_bytes=PERFORMANCE_SETTINGS.mass_answer_max_upload_mb
            * 1024
            * 1024,
        )
        parsed = await blocking_runner.run(
            parse_mass_answer_file,
            contents=contents,
            filename=filename,
            max_rows=PERFORMANCE_SETTINGS.mass_answer_max_rows,
        )
    except MassAnswerFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return (
        parsed.dataframe,
        parsed.question_column,
        docs_list,
        parsed.output_extension,
        filename,
    )


async def _process_mass_answer(
        background_tasks: BackgroundTasks,
        *,
        df,
        question_col,
        docs_list: list[str],
        ext: str,
        filename: str,
):
    batch_id = str(uuid.uuid4())
    mass_answer_logger.info(
        "mass-answer direct batch started",
        extra={"batch_id": batch_id, "input_filename": filename, "total_rows": len(df.index)},
    )
    path, rows = await _process_mass_dataframe(
        df=df,
        question_col=question_col,
        docs_list=docs_list,
        ext=ext,
        batch_id=batch_id,
    )
    mass_answer_logger.info(
        "mass-answer direct batch completed",
        extra={
            "batch_id": batch_id,
            "total_rows": len(rows),
            "successful_rows": sum(row.status == "success" for row in rows),
            "failed_rows": sum(row.status != "success" for row in rows),
        },
    )
    background_tasks.add_task(os.remove, path)
    return FileResponse(
        path,
        filename=f"Answered_{filename}",
        media_type=_mass_answer_media_type(ext),
    )


async def _process_mass_dataframe(
    *, df, question_col, docs_list: list[str], ext: str,
    output_path: str | None = None, batch_id: str = "direct",
    progress_callback=None,
):
    queries = [
        None if pd.isna(value) else str(value)
        for value in df[question_col].tolist()
    ]
    row_results = await mass_answer_processor.process(
        queries,
        selected_documents=docs_list,
        batch_id=batch_id,
        progress_callback=progress_callback,
    )
    df['Answer (پاسخ)'] = [row.answer for row in row_results]
    df['status'] = [row.status for row in row_results]
    df['error_code'] = [row.error_code for row in row_results]
    df['error_message'] = [row.error_message for row in row_results]
    df['processing_time_ms'] = [
        round(row.processing_time_ms, 3) for row in row_results
    ]
    df['intent'] = [row.intent for row in row_results]
    df['rewritten_query'] = [row.rewritten_query for row in row_results]
    df['related_questions'] = [row.related_questions for row in row_results]

    def write_result_file():
        return write_safe_output(
            df, extension=ext, output_path=output_path
        )

    path = await blocking_runner.run(
        write_result_file, wait_for_completion_on_cancel=True
    )
    return path, row_results


async def _create_mass_answer_job(*, df, question_col, docs_list, ext, filename):
    job_id = str(uuid.uuid4())
    artifact_directory = tempfile.mkdtemp(prefix=f"mass-answer-{job_id}-")
    output_path = os.path.join(
        artifact_directory, f"Answered_{os.path.splitext(filename)[0]}{ext}"
    )
    now = datetime.utcnow()
    valid_rows = sum(
        1 for value in df[question_col].tolist()
        if not pd.isna(value) and str(value).strip()
    )
    job = {
        "id": job_id,
        "input_filename": filename,
        "input_format": ext,
        "selected_documents": docs_list,
        "artifact_directory": artifact_directory,
        "total_rows": len(df.index),
        "valid_rows": valid_rows,
        "created_at": now,
        "expires_at": now + timedelta(
            hours=PERFORMANCE_SETTINGS.mass_answer_job_retention_hours
        ),
    }
    try:
        created = await blocking_runner.run(
            db_manager.create_mass_answer_job,
            job,
            wait_for_completion_on_cancel=True,
        )
        if not created:
            raise RuntimeError("job record was not created")
    except Exception:
        await blocking_runner.run(shutil.rmtree, artifact_directory, True)
        raise

    mass_answer_job_manager.start(
        job_id,
        lambda: _run_mass_answer_job(
            job_id=job_id,
            df=df,
            question_col=question_col,
            docs_list=docs_list,
            ext=ext,
            output_path=output_path,
        ),
    )
    mass_answer_logger.info(
        "mass-answer job queued",
        extra={"batch_id": job_id, "input_filename": filename, "total_rows": len(df.index)},
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job_id,
            "status": "queued",
            "total_rows": len(df.index),
            "status_url": f"/api/mass-answer/jobs/{job_id}",
            "result_url": f"/api/mass-answer/jobs/{job_id}/result",
        },
    )


async def _run_mass_answer_job(
    *, job_id, df, question_col, docs_list, ext, output_path
):
    started = datetime.utcnow()
    started_monotonic = asyncio.get_running_loop().time()
    try:
        await blocking_runner.run(
            db_manager.update_mass_answer_job,
            job_id,
            {"status": "running", "started_at": started},
            wait_for_completion_on_cancel=True,
        )
        path, rows = await _process_mass_dataframe(
            df=df,
            question_col=question_col,
            docs_list=docs_list,
            ext=ext,
            output_path=output_path,
            batch_id=job_id,
            progress_callback=lambda progress: (
                mass_answer_job_manager.set_progress(job_id, progress)
            ),
        )
        successful = sum(row.status == "success" for row in rows)
        timed_out = sum(row.status == "timeout" for row in rows)
        completed = datetime.utcnow()
        durations = sorted(row.processing_time_ms for row in rows)
        total_duration_ms = (
            asyncio.get_running_loop().time() - started_monotonic
        ) * 1000
        await blocking_runner.run(
            db_manager.update_mass_answer_job,
            job_id,
            {
                "status": "completed",
                "result_path": path,
                "completed_rows": len(rows),
                "successful_rows": successful,
                "failed_rows": len(rows) - successful,
                "timed_out_rows": timed_out,
                "completed_at": completed,
                "total_duration_ms": total_duration_ms,
                "average_row_ms": (
                    sum(durations) / len(durations) if durations else 0.0
                ),
                "p50_row_ms": _percentile(durations, 0.50),
                "p95_row_ms": _percentile(durations, 0.95),
                "p99_row_ms": _percentile(durations, 0.99),
            },
            wait_for_completion_on_cancel=True,
        )
        mass_answer_logger.info(
            "mass-answer job completed",
            extra={
                "batch_id": job_id,
                "total_rows": len(rows),
                "successful_rows": successful,
                "failed_rows": len(rows) - successful,
                "duration_ms": round(total_duration_ms, 3),
            },
        )
    except asyncio.CancelledError:
        await blocking_runner.run(
            db_manager.update_mass_answer_job,
            job_id,
            {
                "status": "failed",
                "error_message": "Worker stopped before completion",
                "completed_at": datetime.utcnow(),
            },
            wait_for_completion_on_cancel=True,
        )
        raise
    except Exception:
        await blocking_runner.run(
            db_manager.update_mass_answer_job,
            job_id,
            {
                "status": "failed",
                "error_message": "Batch processing failed",
                "completed_at": datetime.utcnow(),
            },
            wait_for_completion_on_cancel=True,
        )


def _mass_job_public(job: dict) -> dict:
    total = int(job.get("total_rows") or 0)
    completed = int(job.get("completed_rows") or 0)
    live_progress = mass_answer_job_manager.get_progress(job["id"])
    if live_progress is not None:
        completed = live_progress.completed_rows
    response = {
        "job_id": job["id"],
        "status": job["status"],
        "input_filename": job["input_filename"],
        "total_rows": total,
        "valid_rows": int(job.get("valid_rows") or 0),
        "completed_rows": completed,
        "successful_rows": int(job.get("successful_rows") or 0),
        "failed_rows": int(job.get("failed_rows") or 0),
        "timed_out_rows": int(job.get("timed_out_rows") or 0),
        "queued_rows": max(0, total - completed),
        "active_rows": 0,
        "error_message": job.get("error_message") or "",
        "created_at": job["created_at"].isoformat() if job.get("created_at") else None,
        "started_at": job["started_at"].isoformat() if job.get("started_at") else None,
        "completed_at": job["completed_at"].isoformat() if job.get("completed_at") else None,
        "expires_at": job["expires_at"].isoformat() if job.get("expires_at") else None,
        "result_url": (
            f"/api/mass-answer/jobs/{job['id']}/result"
            if job["status"] == "completed" else None
        ),
    }
    if live_progress is not None:
        response.update({
            "successful_rows": live_progress.successful_rows,
            "failed_rows": live_progress.failed_rows,
            "timed_out_rows": live_progress.timed_out_rows,
            "queued_rows": live_progress.queued_rows,
            "active_rows": live_progress.active_rows,
        })
    for field in (
        "total_duration_ms", "average_row_ms", "p50_row_ms",
        "p95_row_ms", "p99_row_ms",
    ):
        response[field] = job.get(field)
    return response


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


@app.post("/api/mass-answer/jobs/cleanup")
async def cleanup_expired_mass_answer_jobs():
    jobs = await blocking_runner.run(
        db_manager.get_expired_mass_answer_jobs, datetime.utcnow()
    )
    removed = 0
    for job in jobs:
        if job["id"] in mass_answer_job_manager.active_job_ids:
            continue
        await blocking_runner.run(
            shutil.rmtree, job["artifact_directory"], True,
            wait_for_completion_on_cancel=True,
        )
        await blocking_runner.run(
            db_manager.delete_mass_answer_job,
            job["id"],
            wait_for_completion_on_cancel=True,
        )
        removed += 1
    return {"status": "success", "removed_jobs": removed}


@app.get("/api/mass-answer/jobs/{job_id}")
async def get_mass_answer_job(job_id: str):
    job = await blocking_runner.run(db_manager.get_mass_answer_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Mass-answer job not found")
    return _mass_job_public(job)


@app.get("/api/mass-answer/jobs/{job_id}/result")
async def download_mass_answer_job(job_id: str):
    job = await blocking_runner.run(db_manager.get_mass_answer_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Mass-answer job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="Mass-answer job is not complete")
    path = job.get("result_path")
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=410, detail="Mass-answer result has expired")
    ext = str(job["input_format"])
    return FileResponse(
        path,
        filename=os.path.basename(path),
        media_type=_mass_answer_media_type(ext),
    )


@app.delete("/api/mass-answer/jobs/{job_id}")
async def delete_mass_answer_job(job_id: str):
    job = await blocking_runner.run(db_manager.get_mass_answer_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Mass-answer job not found")
    await mass_answer_job_manager.cancel(job_id)
    await blocking_runner.run(
        shutil.rmtree, job["artifact_directory"], True,
        wait_for_completion_on_cancel=True,
    )
    await blocking_runner.run(
        db_manager.delete_mass_answer_job,
        job_id,
        wait_for_completion_on_cancel=True,
    )
    return {"status": "deleted", "job_id": job_id}


def _mass_answer_media_type(ext: str) -> str:
    if ext == ".csv":
        return "text/csv; charset=utf-8"
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ----------------------------------------------------------------------
# Metrics, KPI Real-time Engine & Monitoring Health Overlays
# ----------------------------------------------------------------------
# @app.get("/api/analytics")
# async def get_analytics():
#     import random
#     from datetime import timedelta
#     now = datetime.now()
#     days = [(now - timedelta(days=i)).strftime("%m/%d") for i in range(29, -1, -1)]
#     hours = [f"{h:02d}:00" for h in range(24)]
#     weekdays = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]
#     subjects = available_documents[:8] if available_documents else ["Risk", "Lending", "AML", "HR", "IT", "Compliance",
#                                                                     "Treasury", "Audit"]
#     return {
#         "kpis": {
#             "total_queries": random.randint(8000, 15000),
#             "active_users": random.randint(120, 400),
#             "avg_response_ms": random.randint(180, 600),
#             "satisfaction": round(random.uniform(3.5, 4.9), 1),
#             "documents_indexed": len(available_documents) or random.randint(20, 80),
#             "uptime_pct": round(random.uniform(99.0, 99.99), 2),
#         },
#         "queries_per_day": {"labels": days, "data": [random.randint(50, 300) for _ in days]},
#         "users_per_day": {"labels": days, "data": [random.randint(10, 80) for _ in days]},
#         "heatmap": {"subjects": subjects, "hours": hours,
#                     "matrix": [[random.randint(0, 40) for _ in hours] for _ in subjects]},
#         "top_documents": [{"name": s, "count": random.randint(50, 500)} for s in subjects],
#         "satisfaction_dist": {
#             "labels": ["1 ★", "2 ★", "3 ★", "4 ★", "5 ★"],
#             "data": [random.randint(5, 30), random.randint(10, 40), random.randint(30, 80), random.randint(80, 200),
#                      random.randint(100, 300)],
#         },
#         "response_time_buckets": {
#             "labels": ["<200ms", "200-500ms", "500ms-1s", "1-2s", ">2s"],
#             "data": [random.randint(100, 400), random.randint(80, 300), random.randint(30, 150), random.randint(10, 60),
#                      random.randint(2, 20)],
#         },
#         "hourly_traffic": {"labels": hours, "data": [random.randint(5, 120) for _ in hours]},
#         "weekly_comparison": {
#             "labels": weekdays,
#             "this_week": [random.randint(80, 300) for _ in weekdays],
#             "last_week": [random.randint(60, 280) for _ in weekdays],
#         },
#     }

from fastapi import Query, HTTPException


@app.get("/api/analytics")
async def get_analytics(days: int = Query(default=30, ge=7, le=30)):
    return await blocking_runner.run(_get_analytics_sync, days)


def _get_analytics_sync(days: int):
    import json

    # Enforce allowed filter windows to match UI dropdown values
    if days not in [7, 14, 30]:
        days = 30

    time_window = f"{days} days"
    conn = None
    cursor = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        # ---------------------------------------------------------
        # 1. KPI Aggregations (Scoped to date filter)
        # ---------------------------------------------------------
        cursor.execute("SELECT COUNT(id) FROM queries WHERE created_at >= NOW() - CAST(%s AS INTERVAL);",
                       (time_window,))
        total_queries = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            "SELECT COUNT(DISTINCT user_id) FROM chat_sessions WHERE created_at >= NOW() - CAST(%s AS INTERVAL);",
            (time_window,))
        active_users = int(cursor.fetchone()[0] or 0)

        # Using your exact working timestamp delta logic, filtered by selected time window
        cursor.execute("""
                       SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at)))
                       FROM queries
                       WHERE updated_at > created_at
                         AND created_at >= NOW() - CAST(%s AS INTERVAL);
                       """, (time_window,))
        avg_resp = cursor.fetchone()[0]
        avg_response_val = round(float(avg_resp), 2) if avg_resp is not None else 0.0

        cursor.execute(
            "SELECT AVG(rating) FROM feedbacks WHERE rating IS NOT NULL AND created_at >= NOW() - CAST(%s AS INTERVAL);",
            (time_window,))
        avg_sat = cursor.fetchone()[0]
        satisfaction = round(float(avg_sat), 1) if avg_sat is not None else 0.0

        # Total documents indexed remains a global system KPI
        cursor.execute("SELECT COUNT(id) FROM documents WHERE processing_status = 'completed';")
        documents_indexed = int(cursor.fetchone()[0] or 0)

        # ---------------------------------------------------------
        # 2. Daily Traffic
        # ---------------------------------------------------------
        cursor.execute("""
                       SELECT TO_CHAR(DATE(created_at), 'MM/DD'), COUNT(id)
                       FROM queries
                       WHERE created_at >= NOW() - CAST(%s AS INTERVAL)
                       GROUP BY DATE (created_at)
                       ORDER BY DATE (created_at) ASC;
                       """, (time_window,))
        qpd_rows = cursor.fetchall()
        qpd_labels = [row[0] for row in qpd_rows]
        qpd_data = [int(row[1]) for row in qpd_rows]

        if not qpd_labels:
            qpd_labels, qpd_data = ["Today"], [0]

        cursor.execute("""
                       SELECT TO_CHAR(DATE(created_at), 'MM/DD'), COUNT(DISTINCT user_id)
                       FROM chat_sessions
                       WHERE created_at >= NOW() - CAST(%s AS INTERVAL)
                       GROUP BY DATE (created_at)
                       ORDER BY DATE (created_at) ASC;
                       """, (time_window,))
        upd_rows = cursor.fetchall()
        upd_labels = [row[0] for row in upd_rows]
        upd_data = [int(row[1]) for row in upd_rows]

        if not upd_labels:
            upd_labels, upd_data = ["Today"], [0]

        # ---------------------------------------------------------
        # 3. Satisfaction Distribution
        # ---------------------------------------------------------
        cursor.execute("""
                       SELECT rating, COUNT(id)
                       FROM feedbacks
                       WHERE rating IS NOT NULL
                         AND created_at >= NOW() - CAST(%s AS INTERVAL)
                       GROUP BY rating;
                       """, (time_window,))
        sat_dist_dict = {int(row[0]): int(row[1]) for row in cursor.fetchall()}
        sat_data = [sat_dist_dict.get(i, 0) for i in range(1, 6)]

        # ---------------------------------------------------------
        # 4. Response Time Buckets (In seconds, scoped to filter)
        # ---------------------------------------------------------
        cursor.execute("""
                       WITH times AS (SELECT EXTRACT(EPOCH FROM (updated_at - created_at)) AS duration
                                      FROM queries
                                      WHERE updated_at > created_at
                                        AND created_at >= NOW() - CAST(%s AS INTERVAL))
                       SELECT COALESCE(SUM(CASE WHEN duration < 0.2 THEN 1 ELSE 0 END), 0),
                              COALESCE(SUM(CASE WHEN duration >= 0.2 AND duration < 0.5 THEN 1 ELSE 0 END), 0),
                              COALESCE(SUM(CASE WHEN duration >= 0.5 AND duration < 1.0 THEN 1 ELSE 0 END), 0),
                              COALESCE(SUM(CASE WHEN duration >= 1.0 AND duration < 2.0 THEN 1 ELSE 0 END), 0),
                              COALESCE(SUM(CASE WHEN duration >= 2.0 THEN 1 ELSE 0 END), 0)
                       FROM times;
                       """, (time_window,))
        rt_row = cursor.fetchone()
        rt_data = [int(val) for val in rt_row] if rt_row else [0, 0, 0, 0, 0]

        # ---------------------------------------------------------
        # 5. Hourly Traffic Patterns
        # ---------------------------------------------------------
        cursor.execute("""
                       SELECT EXTRACT(HOUR FROM created_at), COUNT(id)
                       FROM queries
                       WHERE created_at >= NOW() - CAST(%s AS INTERVAL)
                       GROUP BY EXTRACT(HOUR FROM created_at);
                       """, (time_window,))
        hourly_dict = {int(row[0]): int(row[1]) for row in cursor.fetchall()}
        hourly_labels = [f"{h:02d}:00" for h in range(24)]
        hourly_data = [hourly_dict.get(h, 0) for h in range(24)]

        # ---------------------------------------------------------
        # 6. Top Documents & Subject/Hour Heatmap Logic
        # ---------------------------------------------------------
        cursor.execute("SELECT id, title FROM documents;")
        doc_map = {str(row[0]): row[1] for row in cursor.fetchall()}

        cursor.execute("""
                       SELECT retrieved_documents, EXTRACT(HOUR FROM created_at)
                       FROM queries
                       WHERE retrieved_documents IS NOT NULL
                         AND created_at >= NOW() - CAST(%s AS INTERVAL);
                       """, (time_window,))
        doc_counts = {}
        hourly_doc_counts = []

        for row in cursor.fetchall():
            retrieved = row[0]
            hour = int(row[1] if row[1] is not None else 0)

            if isinstance(retrieved, str):
                try:
                    retrieved = json.loads(retrieved)
                except:
                    retrieved = []

            if isinstance(retrieved, list):
                for d_id in retrieved:
                    doc_id_str = str(d_id)
                    doc_counts[doc_id_str] = doc_counts.get(doc_id_str, 0) + 1
                    hourly_doc_counts.append((doc_id_str, hour))

        top_docs_sorted = sorted(doc_counts.items(), key=lambda x: x[1], reverse=True)[:8]
        top_docs = [{"name": doc_map.get(d_id, f"Doc {d_id}"), "count": count} for d_id, count in top_docs_sorted]

        heatmap_subjects = [doc["name"] for doc in top_docs]
        heatmap_matrix = [[0 for _ in range(24)] for _ in range(len(heatmap_subjects))]

        doc_to_subj_idx = {d_id: idx for idx, (d_id, _) in enumerate(top_docs_sorted)}

        for d_id, hour in hourly_doc_counts:
            if d_id in doc_to_subj_idx:
                heatmap_matrix[doc_to_subj_idx[d_id]][hour] += 1

        if not top_docs:
            top_docs = [{"name": "No documents queried yet", "count": 0}]
            heatmap_subjects = ["N/A"]
            heatmap_matrix = [[0 for _ in range(24)]]

        # ---------------------------------------------------------
        # 7. Weekly Comparison
        # ---------------------------------------------------------
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        cursor.execute("""
                       SELECT EXTRACT(ISODOW FROM created_at), COUNT(id)
                       FROM queries
                       WHERE created_at >= NOW() - INTERVAL '7 days'
                       GROUP BY EXTRACT (ISODOW FROM created_at);
                       """)
        tw_dict = {int(row[0]): int(row[1]) for row in cursor.fetchall()}
        this_week_data = [tw_dict.get(i, 0) for i in range(1, 8)]

        cursor.execute("""
                       SELECT EXTRACT(ISODOW FROM created_at), COUNT(id)
                       FROM queries
                       WHERE created_at >= NOW() - INTERVAL '14 days' AND created_at < NOW() - INTERVAL '7 days'
                       GROUP BY EXTRACT (ISODOW FROM created_at);
                       """)
        lw_dict = {int(row[0]): int(row[1]) for row in cursor.fetchall()}
        last_week_data = [lw_dict.get(i, 0) for i in range(1, 8)]

        return {
            "kpis": {
                "total_queries": total_queries,
                "active_users": active_users,
                "avg_response_ms": avg_response_val,  # Required by analytics.js line 169
                "avg_response_sec": avg_response_val,  # Semantic fallback
                "satisfaction": satisfaction,
                "documents_indexed": documents_indexed,
                "uptime_pct": 99.9,
            },
            "queries_per_day": {"labels": qpd_labels, "data": qpd_data},
            "users_per_day": {"labels": upd_labels, "data": upd_data},
            "satisfaction_dist": {
                "labels": ["1 ★", "2 ★", "3 ★", "4 ★", "5 ★"],
                "data": sat_data
            },
            "response_time_buckets": {
                "labels": ["<0.2s", "0.2-0.5s", "0.5-1.0s", "1.0-2.0s", ">2.0s"],
                "data": rt_data
            },
            "hourly_traffic": {"labels": hourly_labels, "data": hourly_data},
            "heatmap": {
                "subjects": heatmap_subjects,
                "hours": hourly_labels,
                "matrix": heatmap_matrix
            },
            "top_documents": top_docs,
            "weekly_comparison": {
                "labels": weekdays,
                "this_week": this_week_data,
                "last_week": last_week_data
            }
        }

    except ServiceError:
        raise
    except PostgresError as exc:
        raise ServiceUnavailableError(
            "PostgreSQL operation failed"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Analytics failed to process"
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "system_initialized": rag_system is not None,
        "documents_available": len(available_documents),
        "ocr_available": ocr_service is not None
    }


if __name__ == "__main__":
    import uvicorn


    uvicorn.run("main:app", host=os.getenv("API_HOST","0.0.0.0"), port=os.getenv("API_PORT", "8080"), reload=False)
