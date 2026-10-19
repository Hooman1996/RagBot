"""Synthetic P1 evidence with independent relevance/condition labels."""
class InlineRunner:
    async def run(self, function, *args, **kwargs):
        return function(*args)


def replay_search(case):
    """Run production fusion on frozen branches; do not contact data services."""
    from utils.persian_hybrid_search import PersianHybridSearch

    search = PersianHybridSearch.__new__(PersianHybridSearch)
    search._closed = False
    search._blocking_runner = InlineRunner()
    search._get_or_build_bm25 = lambda docs: (None, [], case["chunks"])
    search._process_query = lambda query: [query]
    search._normalise_query = lambda query: query
    sparse = [(r["id"], r["score"]) for r in case["sparse"]]
    search._score_bm25 = lambda *args: ([], sparse)

    async def dense(query, docs, top_k):
        return {r["id"]: r["score"] for r in case["dense"]}

    search._semantic_search = dense
    return search


def case_from_ids(sparse, dense, *, top_k=50):
    ids = dict.fromkeys(sparse + dense)
    return {
        "id": "synthetic-math", "query": "synthetic", "top_k": top_k,
        "sparse": [{"id": cid, "score": float(len(sparse)-i)} for i, cid in enumerate(sparse)],
        "dense": [{"id": cid, "score": float(len(dense)-i)} for i, cid in enumerate(dense)],
        "chunks": {cid: {"text": f"question: fixture {cid}\nanswer: full answer\nsecond sentence\nquestion category: synthetic. sub_category: test", "document_name": "synthetic-FAQ"} for cid in ids},
    }


def controlled_cases():
    """Two complementary relevant entries at rank 45/46 in both branches.

    Unrelated singleton hits are deliberately ranked high by first-stage
    providers. Correct fusion lets complementary evidence reach the 50-item
    reranker pool. Labels describe information needs, not calculated RRF scores.
    No real product facts or customer queries are used.
    """
    sparse = [f"sparse-{i:02}" for i in range(1, 49)]
    dense = [f"dense-{i:02}" for i in range(1, 49)]
    sparse[44:44] = ["fact-time", "fact-cutoff"]
    dense[44:44] = ["fact-time", "fact-cutoff"]
    case = case_from_ids(sparse, dense)
    for cid, chunk in case["chunks"].items():
        chunk["text"] = f"question: رنگ نشانگر آزمایشی شماره {cid} چیست؟\nanswer: نشانگر آزمایشی خاکستری است.\nquestion category: آزمایشی. sub_category: نشانگر"
    case["chunks"]["fact-time"]["text"] = (
        "question: رسیدگی به درخواست کارت آزمایشی چند روز کاری طول می کشد؟\n"
        "answer: در بانک آزمایشی رسیدگی به درخواست کارت آزمایشی دو روز کاری طول می کشد؛ این مدت روز تقویمی نیست.\n"
        "question category: آزمایشی. sub_category: کارت"
    )
    case["chunks"]["fact-cutoff"]["text"] = (
        "question: مهلت ثبت درخواست کارت آزمایشی و شرط شروع رسیدگی چیست؟\n"
        "answer: در بانک آزمایشی درخواست کارت آزمایشی باید پیش از ساعت ۱۴ ثبت شود. اگر پس از ساعت ۱۴ ثبت شود، رسیدگی از روز کاری بعد آغاز می شود.\n"
        "question category: آزمایشی. sub_category: کارت"
    )
    queries = [
        "در بانک آزمایشی رسیدگی به کارت چند روز کاری طول می کشد و اگر پس از ساعت ۱۴ درخواست بدهم از چه روزی شروع می شود؟",
        "در بانک آزمایشی مدت رسیدگی کارت چقدر است؟ ثبت بعد از ساعت ۱۴ چه اثری بر شروع رسیدگی دارد؟",
        "در بانک آزمایشی مهلت ثبت درخواست کارت چیست، رسیدگی چند روز طول می کشد و آیا این مدت روز تقویمی است؟",
    ]
    # Predetermined checks are narrow lexical fact/condition checks, not an LLM
    # judge or calibrated estimate of natural-query answer quality.
    facts = [
        {"id": "duration", "entry": "fact-time", "pattern": r"(?:دو|2|۲)\s*روز\s*کاری"},
        {"id": "cutoff", "entry": "fact-cutoff", "pattern": r"(?:14|۱۴)"},
        {"id": "late-start", "entry": "fact-cutoff", "pattern": r"روز\s*کاری\s*بعد"},
    ]
    return [dict(case, id=f"synthetic-info-{i+1}", query=query,
                 relevant_ids=["fact-time", "fact-cutoff"], required_facts=facts,
                 forbidden_patterns=[r"دو\s*روز\s*تقویمی\s*(?:است|طول)"])
            for i, query in enumerate(queries)]
