"""
LangGraph agent graph for the Persian banking assistant.

Nodes:
  - add_user_message       : appends incoming user input to the conversation
  - router                 : decides which logic to invoke based on current state
  - classify_intent        : uses IntentClassifier to decide general vs personal vs chitchat
  - handle_general         : calls RAGSystem.retrieve() + LLM for general Q&A
  - handle_personal        : manages slot‑filling for personal scenarios
  - handle_chitchat        : bypasses retrieval and uses a conversational prompt
  - validate_slot          : checks user input against a regex defined in the scenario
  - add_assistant_message  : appends the assistant's reply to the message history
"""

import re
from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator
from utils.rag_utils import clean_llm_answer
from langgraph.graph import StateGraph, END
from utils.rag_utils import aggregate_results
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.service_errors import InvalidRequestError
from utils.request_instrumentation import current_trace
from conversation_history import (
    MAX_STATE_MESSAGES,
    format_answer_prompt_history,
    select_answer_prompt_history,
    trim_agent_messages,
)
from pipeline_observer import (
    PipelineStage,
    PipelineStageResult,
    emit_pipeline_stage_lazy,
    stable_hash,
)
import time


FAQ_FALLBACK_FRAGMENT = (
    "متاسفانه اطلاعات دقیقی در این زمینه ندارم. لطفا اقدام به ثبت تیکت کنید."
)

# ---------- State definition ----------
class AgentState(TypedDict):
    # messages: Annotated[List[Dict[str, str]], operator.add]
    messages: List[Dict[str, str]]
    latest_user_input: str
    retrieval_query: str
    intent: Dict[str, Optional[str]]
    current_scenario: Optional[Dict[str, Any]]
    slots: Dict[str, str]
    remaining_slots: List[str]
    pending_question: Optional[Dict[str, Any]]
    answer: Optional[str]
    last_answer: Optional[str]
    feedback_needed: bool
    asked_feedback: bool
    ticket_submitted: bool
    related_questions: List[Dict[str, str]]
    allowed_docs: List[str]
    doc_category: Optional[str]
    preclassified_intent: Optional[Dict[str, Optional[str]]]
    fallback_reason: Optional[str]


def extract_slots_from_text(text: str, slot_defs: List[Dict]) -> Dict[str, str]:
    extracted = {}
    for slot in slot_defs:
        slot_name = slot["slot_name"]
        pattern = slot.get("validation_regex")
        if not pattern:
            continue
        match = re.search(pattern, text)
        if match:
            extracted[slot_name] = match.group(0)
    return extracted


def trim_messages(messages: list) -> list:
    return trim_agent_messages(messages)


# ---------- Node factory functions ----------
def make_add_user_message():
    async def node(state: AgentState) -> AgentState:
        user_text = state.get("latest_user_input", "").strip()
        if user_text:
            state["messages"].append({"role": "user", "content": user_text})
            state["messages"] = state["messages"][-MAX_STATE_MESSAGES:]
            state["latest_user_input"] = ""
            state["related_questions"] = []
        return state
    return node


def make_router():
    def route(state: AgentState) -> str:
        if state.get("pending_question"):
            return "validate_slot"
        return "classify_intent"
    return route


def make_classify_intent(intent_classifier, scenarios_db):
    async def node(state: AgentState) -> AgentState:
        query = state["messages"][-1]["content"] if state["messages"] else ""
        result = state.pop("preclassified_intent", None)
        if not result:
            result = await intent_classifier.classify(query)
        state["intent"] = result

        if result["type"] == "personal" and result.get("scenario_id"):
            scenario = scenarios_db.get(result["scenario_id"])
            state["current_scenario"] = scenario
            slot_defs = scenario.get("required_slots", [])

            slot_names = [s["slot_name"] for s in slot_defs]
            state["slots"] = {name: "" for name in slot_names}
            state["remaining_slots"] = slot_names.copy()

            pre_filled = extract_slots_from_text(query, slot_defs)
            for slot_name, value in pre_filled.items():
                if slot_name in state["remaining_slots"]:
                    state["slots"][slot_name] = value
                    state["remaining_slots"].remove(slot_name)

            state["pending_question"] = None
        else:
            state["current_scenario"] = None
            state["slots"] = {}
            state["remaining_slots"] = []
        return state
    return node


def make_handle_general(rag_system):
    def prepare_context(search_results, recent):
        aggregated = rag_system.generate_context(search_results)
        related = []
        for candidate_index, result in enumerate(search_results[:5]):
            q_match = re.search(
                r'question\s*:\s*(.+?)(?=answer\s*\d*\s*:|question category\s*:|$)',
                result.content,
                re.DOTALL,
            )
            question = q_match.group(1).strip() if q_match else ""
            answers = re.findall(
                r'answer\s*\d*\s*:\s*(.+?)(?=answer\s*\d*\s*:|question category\s*:|$)',
                result.content,
                re.DOTALL,
            )
            related.append(
                {
                    "question": question,
                    "answer": "\n".join(answer.strip() for answer in answers),
                    "_trace_id": getattr(
                        result, "doc_id", str(candidate_index)
                    ),
                }
            )
        return aggregated, related, recent_history_to_text(recent)

    async def node(state: AgentState) -> AgentState:
        original_query = state["messages"][-1]["content"]
        query = state.get("retrieval_query") or original_query

        allowed = state.get("allowed_docs", [])
        if not allowed:
            raise InvalidRequestError(
                "No current datasource is selected for retrieval"
            )

        # Retrieve once
        search_results = await rag_system.retrieve(
            query,
            top_k=PERFORMANCE_SETTINGS.rag_retrieval_top_k,
            allowed_docs=allowed,
        )
        state["fallback_reason"] = (
            None if search_results else "NO_RETRIEVAL_RESULTS"
        )
        trace = current_trace()
        if trace is not None:
            trace.set_diagnostic(
                "selected_context_ids",
                [result.doc_id for result in search_results],
            )
        recent = select_answer_prompt_history(state["messages"])
        context_started = time.perf_counter()
        if hasattr(rag_system, "blocking_runner"):
            aggregated, related, recent_text = (
                await rag_system.blocking_runner.run(
                    prepare_context, search_results, recent
                )
            )
        else:
            aggregated, related, recent_text = prepare_context(
                search_results, recent
            )

        state["related_questions"] = related
        category = state.get("doc_category")
        if category == "FAQ" and related:
            reranked_related = await rag_system.search_engine.rerank(
                query,
                related,
                threshold=(
                    PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold
                ),
            )
            state["related_questions"] = [
                {
                    key: value
                    for key, value in candidate.items()
                    if not key.startswith("_")
                }
                for candidate in reranked_related
            ]
        else:
            state["related_questions"] = [
                {
                    key: value
                    for key, value in candidate.items()
                    if not key.startswith("_")
                }
                for candidate in related
            ]
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.RERANK,
                status="SKIPPED",
                input_data={
                    "query": query,
                    "candidates": related,
                },
                output_data={"candidates": related},
                metrics={"reason": "NON_FAQ_OR_NO_CANDIDATES"},
                duration_ms=0.0,
            ))
        selected_results = search_results if category == "FAQ" else search_results[:3]
        selected_context = aggregated if category == "FAQ" else selected_results
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.CONTEXT_SELECTION,
            input_data={
                "category": category,
                "candidate_chunk_ids": [
                    str(getattr(item, "doc_id", index))
                    for index, item in enumerate(search_results)
                ],
                "history_messages": recent,
                "recent_history_text": recent_text,
            },
            output_data={
                "selected_chunk_ids": [
                    str(getattr(item, "doc_id", index))
                    for index, item in enumerate(selected_results)
                ],
                "selected_context": selected_context,
            },
            metrics={"selected_context_hash": stable_hash(selected_context)},
            duration_ms=(time.perf_counter() - context_started) * 1000,
        ))
        answer = await rag_system.answer(
            user_question=query,
            context=aggregated if category == "FAQ" else search_results[:3],
            recent_history=recent_text,
            current_summary="", tone="friendly", response_type="normal",
            enable_history=False, category=category,
        )
        if FAQ_FALLBACK_FRAGMENT in (answer or ""):
            state["fallback_reason"] = (
                state.get("fallback_reason") or "LLM_CONTEXT_REFUSAL"
            )
        if trace is not None:
            trace.set_diagnostic(
                "fallback_reason", state.get("fallback_reason")
            )
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.GENERATION,
            output_data={"answer": answer},
            metrics={
                "fallback_used": bool(state.get("fallback_reason")),
                "fallback_reason": state.get("fallback_reason"),
            },
        ))

        state["last_answer"] = answer
        state["answer"] = None
        state["feedback_needed"] = True
        return state
    return node


def make_handle_chitchat(rag_system):
    """
    Handles conversational intents bypassing RAG retrieval.
    Passes an empty context and a specific 'chitchat' category to the RAG System.
    """
    async def node(state: AgentState) -> AgentState:
        query = state["messages"][-1]["content"]
        # recent = state["messages"][-6:]
        recent = select_answer_prompt_history(state["messages"])

        # Generate answer using empty context to let the LLM talk freely
        answer = await rag_system.answer(
            user_question=query,
            context=[], # No retrieved documents
            recent_history=recent_history_to_text(recent),
            current_summary="",
            tone="friendly",
            response_type="normal",
            enable_history=False,
            category="chitchat"  # Used by RAGSystem to apply a conversational prompt
        )

        state["last_answer"] = answer
        state["answer"] = None
        state["feedback_needed"] = False # Chitchat doesn't usually need a helpfulness rating
        state["related_questions"] = []
        return state
    return node


def make_handle_personal():
    def node(state: AgentState) -> AgentState:
        if not state["remaining_slots"]:
            return generate_personal_answer(state)

        next_slot_name = state["remaining_slots"][0]
        scenario = state["current_scenario"]
        slot_def = next(
            s for s in scenario["required_slots"] if s["slot_name"] == next_slot_name
        )
        state["pending_question"] = {
            "slot_name": next_slot_name,
            "text": slot_def["question"],
            "hint": slot_def.get("hint", ""),
            "validation_regex": slot_def["validation_regex"]
        }
        state["answer"] = slot_def["question"]
        state["feedback_needed"] = False
        return state
    return node


def generate_personal_answer(state: AgentState) -> AgentState:
    scenario = state["current_scenario"]
    slots = state["slots"]
    if scenario["id"] == "blocked":
        answer = f"ما مشکل شما را بررسی کردیم. {slots['entity_type']} با کد {slots['entity_code']} در حال حاضر مسدود است. لطفاً با پشتیبانی تماس بگیرید."
    elif scenario["id"] == "loan_status":
        answer = f"وضعیت وام با کد پیگیری {slots['tracking_code']} در حال بررسی است. نتیجه تا ۲۴ ساعت آینده اعلام می‌شود."
    elif scenario["id"] == "card_activation":
        answer = f"کارت با شماره {slots['card_number']} فعال‌سازی شد. لطفاً از آن استفاده کنید."
    else:
        answer = "اطلاعات شما ثبت شد. به زودی پیگیری خواهد شد."
    state["last_answer"] = answer
    state["answer"] = None
    state["feedback_needed"] = True
    return state


def make_validate_slot():
    async def node(state: AgentState) -> AgentState:
        inp = state["messages"][-1]["content"].strip()
        pq = state["pending_question"]
        if not pq:
            return state
        if re.fullmatch(pq["validation_regex"], inp):
            state["slots"][pq["slot_name"]] = inp
            state["remaining_slots"].remove(pq["slot_name"])
            state["pending_question"] = None
        else:
            state["answer"] = f'{pq["hint"]} لطفاً مجدداً تلاش کنید.'
        return state
    return node


def make_add_assistant_message():
    async def node(state: AgentState) -> AgentState:
        if state.get("answer"):
            text = state["answer"]
        elif state.get("last_answer"):
            text = state["last_answer"]
        else:
            text = None

        if text:
            state["messages"].append({"role": "assistant", "content": text})
            state["messages"] = state["messages"][-MAX_STATE_MESSAGES:]
            state["answer"] = None
            state["last_answer"] = None
        return state
    return node


# ---------- Helpers ----------
def recent_history_to_text(messages: List[Dict[str, str]], max_chars: int = 3000) -> str:
    return format_answer_prompt_history(messages, max_chars=max_chars)


# ---------- Graph builder ----------
def build_graph(intent_classifier, scenarios_db, rag_system, chat_manager=None):
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("add_user_message", make_add_user_message())
    graph.add_node("classify_intent", make_classify_intent(intent_classifier, scenarios_db))
    graph.add_node("handle_general", make_handle_general(rag_system))
    graph.add_node("handle_chitchat", make_handle_chitchat(rag_system))
    graph.add_node("handle_personal", make_handle_personal())
    graph.add_node("validate_slot", make_validate_slot())
    graph.add_node("add_assistant_message", make_add_assistant_message())

    # Edges
    graph.set_entry_point("add_user_message")

    graph.add_conditional_edges(
        "add_user_message",
        make_router(),
        {
            "classify_intent": "classify_intent",
            "validate_slot": "validate_slot"
        }
    )

    # Route based on classifier output
    graph.add_conditional_edges(
        "classify_intent",
        lambda s: s["intent"]["type"],
        {
            "general": "handle_general",
            "personal": "handle_general", # Based on your previous setup routing personal to general
            "chitchat": "handle_chitchat" # New explicit route
        }
    )

    graph.add_edge("handle_general", "add_assistant_message")
    graph.add_edge("handle_chitchat", "add_assistant_message")

    graph.add_conditional_edges(
        "handle_personal",
        lambda s: "all_slots_filled" if not s["remaining_slots"] else "missing_slots",
        {
            "all_slots_filled": "add_assistant_message",
            "missing_slots": "add_assistant_message"
        }
    )

    graph.add_edge("validate_slot", "handle_personal")
    graph.add_edge("add_assistant_message", END)

    return graph.compile()
