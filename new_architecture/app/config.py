import os
from dotenv import load_dotenv

# Load variables from .env into os.environ
load_dotenv()
# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

class Config:
    """Configuration for all services"""
    # EMBEDDING_MODEL ="/storage/models/Embeddings/models--jinaai--jina-embeddings-v5-text-small-retrieval"
    # LLM_MODEL = "/storage/models/Engines/google--gemma-4-12B-it",
    # RERANKER_MODEL = "/home/hooman/.cache/huggingface/hub/BAAI--bge-reranker-v2-m3"

    EMBEDDING_MODEL=os.getenv("EMBEDDING_MODEL")
    LLM_MODEL=os.getenv("LLM_MODEL")
    RERANKER_MODEL=os.getenv("RERANKER_MODEL")


    # PostgreSQL
    # POSTGRES_HOST = "localhost"
    # POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_HOST=os.getenv("POSTGRES_HOST")
    # POSTGRES_PORT = 5432
    POSTGRES_PORT=os.getenv("POSTGRES_PORT", "5432")
    # POSTGRES_DB = "hihelp_db"
    POSTGRES_DB=os.getenv("POSTGRES_DB", "hihelp_db")
    # POSTGRES_USER = "postgres"
    POSTGRES_USER=os.getenv("POSTGRES_USER", "postgres")
    # POSTGRES_PASSWORD = "postgres"
    POSTGRES_PASSWORD=os.getenv("POSTGRES_PASSWORD", "postgres")

    # MinIO
    # MINIO_ENDPOINT = "localhost:9000"
    MINIO_ENDPOINT=os.getenv("MINIO_ENDPOINT", "localhost:9000")
    # MINIO_ACCESS_KEY = "minioadmin"
    MINIO_ACCESS_KEY=os.getenv("MINIO_ACCESS_KEY")
    # MINIO_SECRET_KEY = "minioadmin"
    MINIO_SECRET_KEY=os.getenv("MINIO_SECRET_KEY")
    MINIO_SECURE=False
    # MINIO_BUCKET = "hihelp-documents"
    MINIO_BUCKET=os.getenv("MINIO_BUCKET")

    # Qdrant
    # QDRANT_HOST = "localhost"
    QDRANT_HOST=os.getenv("QDRANT_HOST", "localhost")
    # QDRANT_PORT = 6333
    QDRANT_PORT=os.getenv("QDRANT_PORT", "6333")
    # QDRANT_COLLECTION = "hihelp_embeddings"
    QDRANT_COLLECTION=os.getenv("QDRANT_COLLECTION", "hihelp_embeddings")
    # QDRANT_VECTOR_SIZE = 1024
    QDRANT_VECTOR_SIZE=os.getenv("QDRANT_VECTOR_SIZE", "1024")

    # In your Config class
    QDRANT_HTTPS = os.getenv("QDRANT_HTTPS", "false").lower() == "true"

    # Chunking
    CHUNK_SIZE=500
    CHUNK_OVERLAP=50

    # Retrieval
    TOP_K=10 # in nist

    # OCR
    OCR_MODEL="/home/hooman/Downloads/dots_weights"
    OCR_PROMPT="""
    Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

    1. Bbox format: [x1, y1, x2, y2]
    
    2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].
    
    3. Text Extraction & Formatting Rules:
        - Picture: For the 'Picture' category, the text field should be omitted.
        - Formula: Format its text as LaTeX.
        - Table: Format its text as HTML.
        - All Others (Text, Title, etc.): Format their text as Markdown.
    
    4. Constraints:
        - The output text must be the original text from the image, with no translation.
        - All layout elements must be sorted according to human reading order.
    
    5. Final Output: The entire output must be a single JSON object.

    """


    # QUERY_REWRITE_PROMPT = """
    #   You are an expert NLP Query Rewriter for the *Karafarin Bank* (بانک کارآفرین) and *Hi Bank* (های بانک) chatbot ecosystem. Your sole task is to take a raw user query and rewrite it into a clean, standalone, formal Persian search query optimized for a RAG retrieval system.
    #
    # <rules>
    # 1. TOPIC SWITCHING (CRITICAL): If the `<query>` introduces a completely new banking topic that is semantically unrelated to the `<summary>`, you MUST IGNORE the summary completely. Do not force previous context onto a new subject.
    # 2. COREFERENCE RESOLUTION: If the `<query>` is a continuation containing pronouns (آن، این، همون، سقفش، سودش) or implicit references (e.g., "برای کارمندان چی؟"), identify the active subject from the `<summary>` and inject it into the rewritten query.
    # 3. REMOVE CHIT-CHAT & EMOTION: Strip away user frustration, complaints (e.g., "این چه وضعشه", "چرا کار نمیکنه"), greetings, or conversational filler. Extract only the core banking intent.
    # 4. GRAMMAR & CLARITY: Convert spoken/slang Persian into clear, formal, standard Persian (کتابی/رسمی) suitable for database searching.
    # 5. OUTPUT CONSTRAINT: Output strictly and ONLY the final rewritten Persian string. No explanations, no XML tags in your output.
    # </rules>
    #
    # <examples>
    # <example>
    #   <summary>User: شرایط وام مسکن چیست؟</summary>
    #   <query>سقفش چقدره؟</query>
    #   <rewrite>سقف مبلغ وام مسکن چقدر است؟</rewrite>
    # </example>
    #
    # <example>
    #   <summary>User: چرا باشگاه مشتریان قطعه این چه وضعشه؟</summary>
    #   <query>بیمه عمر چیه؟</query>
    #   <rewrite>بیمه عمر چیست؟</rewrite>
    # </example>
    #
    # <example>
    #   <summary>User: چرا نمی تونم ثبت نام کنم، هی می گه عدم تطبیق چهره</summary>
    #   <query>میخوام یه حساب جدید باز کنم غیر کوتاه مدت</query>
    #   <rewrite>چگونه حساب جدید غیر کوتاه مدت  افتتاح کنم؟</rewrite>
    # </example>
    #
    # <example>
    #   <summary>User: فرایند وام گرفتن</summary>
    #   <query>برای کارمندان بانک چطور؟</query>
    #   <rewrite>فرایند دریافت وام برای کارمندان بانک چگونه است؟</rewrite>
    # </example>
    #
    # <example>
    #   <summary>[بدون مکالمه قبلی]</summary>
    #   <query>رمز عبورم رو یادم رفته چیکار کنم</query>
    #   <rewrite>رمز عبورم رو یادم رفته چیکار کنم</rewrite>
    # </example>
    # </examples>
    #
    # Now, process the following:
    #
    # <summary>{current_summary}</summary>
    # <query>{current_query}</query>
    # <rewrite>

    QUERY_REWRITE_PROMPT="""You are an expert NLP Query Rewriter for the Karafarin Bank and Hi Bank chatbot ecosystem. Your sole task is to take a raw user query and rewrite it into a clean, standalone, formal Persian search question optimized for a RAG hybrid retrieval system.

<rules>
1. TOPIC SWITCHING (CRITICAL): Analyze if the `<query>` introduces a new banking topic. If it does, IGNORE the conversation history completely. Do not carry over previous subjects.
2. COREFERENCE RESOLUTION: If the `<query>` contains pronouns (آن، این، همون، سقفش، سودش) or implicit references, identify the active subject from the history and inject it.
3. IMPLICIT INTENT (STATEMENTS): If the user provides a status update or statement (e.g., "ثبت نام کردم", "انجام شد"), infer the next logical question based on the AI's previous instructions. Rewrite it as a question asking for the next step (e.g., "بعد از ثبت نام چه کار کنم؟").
4. HANDLE CHIT-CHAT & EMOTION: Strip away frustration, complaints, and filler to extract the core banking intent. IF the query is purely conversational (e.g., "سلام", "چطوری", "چه خبرا", "حالت چطوره") with ZERO banking intent, DO NOT fabricate a banking question. Sustained chit-chat across multiple turns remains chit-chat. Just output the exact original chit-chat string.
5. GRAMMAR & CLARITY: Convert spoken/slang Persian (or Finglish) into clear, formal, standard Persian (کتابی/رسمی) structured as a question.
6. OUTPUT CONSTRAINT: You must first output a brief <thought_process> analyzing the intent, followed strictly by the final rewritten Persian string inside <rewrite> tags.
</rules>

<examples>
<example>
  <history>
    User: میخوام یه حساب جدید باز کنم غیر کوتاه مدت
    AI: برای افتتاح حساب بلند مدت، پس از ثبت نام اقدام نمایید.
  </history>
  <query>من ثبت نام کردم افتتاح هم کردم</query>
  <thought_process>
    Topic is still account opening. User statement indicates completion of the previously mentioned step. Implicit intent: What happens next or how to proceed after opening the account?
  </thought_process>
  <rewrite>مراحل بعدی پس از ثبت‌نام و افتتاح حساب برای حساب های بلند مدت چیست؟</rewrite>
</example>

<example>
  <history>
    User: شرایط وام مسکن چیست؟
    AI: سقف وام مسکن بستگی به شهر دارد.
  </history>
  <query>چطوری چک ثبت کنم</query>
  <thought_process>
    Topic shift detected. User went from loans to registering checks. Ignore previous context entirely.
  </thought_process>
  <rewrite>چگونه ثبت چک را انجام دهم؟</rewrite>
</example>

<example>
  <history>
    [بدون مکالمه قبلی]
  </history>
  <query>سلام خسته نباشید</query>
  <thought_process>
    Query is purely a greeting and chit-chat. There is zero banking intent to extract. I must not fabricate a question. I will output the original conversational text.
  </thought_process>
  <rewrite>سلام خسته نباشید</rewrite>
</example>

<example>
  <history>
    User: سلام
    AI: سلام! خوش آمدید. چطور می‌توانم در امور بانکی به شما کمک کنم؟
    User: چطوری خوبی
    AI: ممنون! من دستیار هوشمند شما هستم. آیا سوالی درباره خدمات بانکی دارید؟
  </history>
  <query>چه خبرا چیکارا میکنی؟</query>
  <thought_process>
    The user is engaging in sustained, multi-turn chit-chat. Despite the length of the conversation, there is still absolutely no banking intent here. I must not hallucinate a banking topic. I will output the exact conversational text.
  </thought_process>
  <rewrite>چه خبرا چیکارا میکنی؟</rewrite>
</example>
</examples>

Now, process the following:

<history>{current_history}</history>
<query>{current_query}</query>"""