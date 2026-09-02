from typing import List, Dict, Optional
import json
from ...config import Config
import torch
import re
from transformers import AutoModelForCausalLM, AutoTokenizer
import time
from utils.persian_normalization import normalize_persian_text
from conversation_history import format_rewrite_history
from pipeline_observer import (
    PipelineStage,
    PipelineStageResult,
    emit_pipeline_stage_lazy,
)

class HistoryRewritingService:

    def __init__(self, rag_system, db_manager):

        self.rag_system = rag_system
        self.db_manager = db_manager

        config = Config()
        self.config = config

        # print("HistoryRewritingService initialized successfully")
        #
        # model_name = "/home/hooman/.cache/huggingface/hub/models--deepseek-ai--DeepSeek-R1-0528-Qwen3-8B/snapshots/6e8885a6ff5c1dc5201574c8fd700323f23c25fa"
        #
        # # model_name = "/home/hooman/.cache/huggingface/hub/models--Qwen--Qwen3-30B-A3B-Thinking-2507/snapshots/144afc2f379b542fdd4e85a1fcd5e1f79112d95d"
        #
        # self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        #
        # self.history_model = AutoModelForCausalLM.from_pretrained(
        #     model_name,
        #     torch_dtype="auto",
        #     device_map="cpu"
        # )
        #
        # print("qwen loaded successfully on cpu")

    async def summarize_history(self, current_summary: str, dropped_user_msg: str, dropped_ai_msg: str) -> str:
        """
        Updates the running summary ONLY with the turn that is falling out of the window.
        """

        current_summary = current_summary if current_summary else "[بدون مکالمه قبلی]"

        prompt = self.config.SESSION_SUMMARY_PROMPT.format(
            current_summary=current_summary,
            dropped_user_msg=dropped_user_msg,
            dropped_ai_msg=dropped_ai_msg
        )

        new_summary = await self.rag_system.generate_text(prompt)

        return new_summary


    def format_history(self, history: List[Dict], n: int = 5) -> str:
            """Helper to format recent history into text"""

            # print("format_history called")
            if len(history)==0:
                return "[بدون مکالمه اخیر]"

            else:
                # Get the last n turns (or all if history length is less than n)
                recent_history = history[-n:] if len(history) > n else history

                formatted = ""
                for turn in recent_history:
                    formatted += f"User: {turn['user']}\nAI: {turn['ai']}\n"

                # print("format history: finished")
                return formatted.strip()


    from typing import Optional

    import json
    from typing import Optional

    def get_formatted_history_string(self, current_chat_id: Optional[int] = None, max_turns: int = 3) -> str:
        """
        Retrieves history, uses a global set to obliterate cumulative DB duplicates,
        and ensures correct Oldest -> Newest chronological order.
        """
        if not current_chat_id:
            return "[بدون مکالمه قبلی]"

        session_row = self.db_manager.get_session_by_id(int(current_chat_id))
        if not session_row:
            return "[بدون مکالمه قبلی]"

        meta_raw = session_row.get("meta_data", {})
        if isinstance(meta_raw, str):
            try:
                meta = json.loads(meta_raw)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        else:
            meta = meta_raw

        messages = meta.get("agent_state", {}).get("messages", [])
        return format_rewrite_history(messages, max_turns=max_turns)


    def get_user_query_summary(self, session_id: str, max_queries: int = 5) -> str:
        """
        Returns a comma‑separated string of up to the last N user queries,
        without duplication if the total message count is less than N.
        """
        if not session_id:
            return ""
        session_row = self.db_manager.get_session_by_id(int(session_id))
        if not session_row:
            return ""

        meta_raw = session_row.get("meta_data", {})
        if isinstance(meta_raw, str):
            try:
                meta = json.loads(meta_raw)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        else:
            meta = meta_raw

        agent_state = meta.get("agent_state", {})
        messages = agent_state.get("messages", [])

        # Filter out empty or non-string queries to keep data clean
        user_queries = [
            msg["content"] for msg in messages
            if msg.get("role", "").lower() == "user" and msg.get("content")
        ]

        if not user_queries:
            return ""

        # Slice the last max_queries (if less than 5 exist, it safely returns all existing ones)
        recent = user_queries[-max_queries:]
        return "، ".join(recent)

    def get_history(self, current_chat_id: Optional[int] = None, n: int = 3) -> tuple:
        """
        Retrieve interleaved conversation history (User and Assistant) from meta_data.
        Returns a formatted string matching the prompt's <history> tags, along with meta.
        """
        if not current_chat_id:
            return "", [], {}

        session_row = self.db_manager.get_session_by_id(int(current_chat_id))
        if not session_row:
            return "", [], {}

        meta_raw = session_row.get("meta_data", {})
        if isinstance(meta_raw, str):
            try:
                meta = json.loads(meta_raw)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        else:
            meta = meta_raw

        agent_state = meta.get("agent_state", {})
        messages = agent_state.get("messages", [])

        # 1. Properly pair chronologically instead of flattening blindly
        formatted_turns = []
        current_turn = {"user": None, "ai": None}

        for msg in messages:
            role = msg.get("role", "").lower()
            content = msg.get("content", "")

            if role == "user":
                # If a user message comes in before an AI response to the last one, wrap up the last one
                if current_turn["user"] is not None:
                    formatted_turns.append(current_turn)
                    current_turn = {"user": None, "ai": None}
                current_turn["user"] = content
            elif role in ["assistant", "ai"]:
                current_turn["ai"] = content
                formatted_turns.append(current_turn)
                current_turn = {"user": None, "ai": None}

        # Append any remaining un-replied user message (or edge cases)
        if current_turn["user"] is not None:
            formatted_turns.append(current_turn)

        # 2. Slice only the last `n` pairs safely (no artificial padding)
        recent_turns = formatted_turns[-n:] if n else formatted_turns

        # 3. Build a clean, highly readable string representation for the LLM context block
        history_string_list = []
        for turn in recent_turns:
            if turn["user"]:
                history_string_list.append(f"User: {turn['user']}")
            if turn["ai"]:
                history_string_list.append(f"AI: {turn['ai']}")

        history_prompt_string = "\n".join(history_string_list) if history_string_list else "[بدون مکالمه قبلی]"
        summary = meta.get("summary", "")

        return summary, history_prompt_string, meta

    async def rewrite_query(self, current_query: str, current_summary: str) -> str:
        started = time.perf_counter()
        current_query = normalize_persian_text(current_query)
        if not current_summary or current_summary == "[بدون مکالمه قبلی]":
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.REWRITE,
                input_data={
                    "history_used": current_summary or "",
                    "original_query": current_query,
                },
                output_data={"rewritten_query": current_query},
                metrics={
                    "model": getattr(self.rag_system, "model_id", None),
                    "temperature": 0.0,
                    "top_p": None,
                    "seed": None,
                    "max_tokens": getattr(
                        __import__(
                            "utils.performance_config",
                            fromlist=["PERFORMANCE_SETTINGS"],
                        ).PERFORMANCE_SETTINGS,
                        "rag_rewrite_max_tokens",
                    ),
                    "generation_skipped": True,
                    "fallback_used": False,
                },
                duration_ms=(time.perf_counter() - started) * 1000,
            ))
            return current_query
        rewrite_prompt = self.config.QUERY_REWRITE_PROMPT.format(
            current_history=current_summary, current_query=current_query
        )
        final_query = await self.rag_system.generate_text(rewrite_prompt)
        extracted, fallback_mode = extract_rewritten_query_detailed(
            final_query, current_query
        )
        rewritten = normalize_persian_text(extracted)
        from utils.performance_config import PERFORMANCE_SETTINGS
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.REWRITE,
            input_data={
                "history_used": current_summary,
                "original_query": current_query,
                "prompt": rewrite_prompt,
            },
            output_data={
                "raw_model_output": final_query,
                "rewritten_query": rewritten,
            },
            metrics={
                "model": getattr(self.rag_system, "model_id", None),
                "system_message": "You are a helpful assistant.",
                "temperature": 0.0,
                "top_p": None,
                "seed": None,
                "max_tokens": PERFORMANCE_SETTINGS.rag_rewrite_max_tokens,
                "fallback_used": fallback_mode is not None,
                "fallback_reason": fallback_mode,
            },
            duration_ms=(time.perf_counter() - started) * 1000,
        ))
        return rewritten

    

def extract_rewritten_query(llm_output: str, original_query: str) -> str:
    """
    Extracts the clean query from inside the <rewrite> tags.
    Falls back to the original query if the LLM failed to use tags.
    """
    # Regex to find everything between <rewrite> and </rewrite>
    return extract_rewritten_query_detailed(llm_output, original_query)[0]


def extract_rewritten_query_detailed(
    llm_output: str, original_query: str
) -> tuple[str, str | None]:
    match = re.search(r'<rewrite>(.*?)</rewrite>', llm_output, re.DOTALL | re.IGNORECASE)

    if match:
        cleaned_query = match.group(1).strip()
        return cleaned_query, None

    # Fallback: If the LLM hallucinated or forgot the tags, check if it wrote text after </thought_process>
    if "</thought_process>" in llm_output:
        parts = llm_output.split("</thought_process>")
        fallback_text = parts[-1].replace("<rewrite>", "").replace("</rewrite>", "").strip()
        if fallback_text:
            return fallback_text, "THOUGHT_PROCESS_FALLBACK"

    # Ultimate Fallback: Return original query so the RAG pipeline doesn't crash
    return original_query.strip(), "REWRITE_PARSE_FALLBACK"
