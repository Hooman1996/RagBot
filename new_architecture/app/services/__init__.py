# # app/services/__init__.py
#
# """
# Services module
# Provides business logic and service layer for the RAG application
# """
#
from .authentication import AuthenticationService
from .chunking import ChunkingService
from .db_connection import DatabaseConnections
from .document import DocumentUploadService
from .embedding import EmbeddingService
from .feedback import FeedbackService
# from .llm import LLMService
# from .ocr import OCRService
# from .preprocessing import PreprocessingService
# from .retrieval import RetrievalService

#
__all__ = [
    # Core RAG services
    "ChunkingService",
    "EmbeddingService",
    # "LLMService",
    # "PreprocessingService",
    # "RetrievalService",

    # User and authentication
    "AuthenticationService",

    # Document processing
    "DatabaseConnections",
    "DocumentUploadService",
    # "OCRService",

    # Feedback
    "FeedbackService",


]
#
