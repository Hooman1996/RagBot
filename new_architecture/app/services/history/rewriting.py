from typing import List, Dict, Optional
import json
from ...config import Config
import torch
import re
from transformers import AutoModelForCausalLM, AutoTokenizer
import time
from utils.persian_normalization import normalize_persian_text

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

        print("Current summary: ", current_summary)

        new_summary = await self.rag_system.generate_text(prompt)

        print("new summary:", new_summary)

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
        if not messages:
            return "[بدون مکالمه قبلی]"

        # 1. Global Deduplication
        unique_messages = []
        seen_texts = set()

        for msg in messages:
            role = msg.get("role", "").lower()
            text = msg.get("content", "").strip()

            if not text or role not in ["user", "assistant", "ai", "model"]:
                continue

            # If we have EVER seen this exact text in this session, skip it completely.
            # This fixes LangGraph/LangChain cumulative state duplication.
            if text in seen_texts:
                continue

            seen_texts.add(text)
            speaker = "AI" if role in ["assistant", "ai", "model"] else "User"
            unique_messages.append(f"{speaker}: {text}")

        if not unique_messages:
            return "[بدون مکالمه قبلی]"

        # 2. Fix Database Reversal (If your DB returns Newest-First)
        # If the very first unique message in the list is an AI message,
        # it usually means the database returned the list backwards (ORDER BY DESC).
        if unique_messages[0].startswith("AI:"):
            unique_messages.reverse()

        # 3. Slice for the last N turns (1 turn = User + AI = 2 messages)
        message_limit = max_turns * 2

        # We slice from the end to get the most recent valid history
        recent_lines = unique_messages[-message_limit:]

        # 4. Return the final string (Oldest at top, Newest at bottom)
        return "\n".join(recent_lines)


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
        current_query = normalize_persian_text(current_query)
        if not current_summary or current_summary == "[بدون مکالمه قبلی]":
            return current_query
        rewrite_prompt = self.config.QUERY_REWRITE_PROMPT.format(
            current_history=current_summary, current_query=current_query
        )
        final_query = await self.rag_system.generate_text(rewrite_prompt)
        return normalize_persian_text(
            extract_rewritten_query(final_query, current_query)
        )

    

def extract_rewritten_query(llm_output: str, original_query: str) -> str:
    """
    Extracts the clean query from inside the <rewrite> tags.
    Falls back to the original query if the LLM failed to use tags.
    """
    # Regex to find everything between <rewrite> and </rewrite>
    match = re.search(r'<rewrite>(.*?)</rewrite>', llm_output, re.DOTALL | re.IGNORECASE)

    if match:
        cleaned_query = match.group(1).strip()
        return cleaned_query

    # Fallback: If the LLM hallucinated or forgot the tags, check if it wrote text after </thought_process>
    if "</thought_process>" in llm_output:
        parts = llm_output.split("</thought_process>")
        fallback_text = parts[-1].replace("<rewrite>", "").replace("</rewrite>", "").strip()
        if fallback_text:
            return fallback_text

    # Ultimate Fallback: Return original query so the RAG pipeline doesn't crash
    return original_query.strip()
