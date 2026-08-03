import ast
import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ModulePatch:
    def __init__(self, replacements):
        self.replacements = replacements
        self.previous = {}

    def __enter__(self):
        for name, module in self.replacements.items():
            self.previous[name] = sys.modules.get(name)
            sys.modules[name] = module

    def __exit__(self, exc_type, exc, traceback):
        for name, previous in self.previous.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def graph_import_stubs():
    graph_module = types.ModuleType("langgraph.graph")

    class StateGraph:
        def __init__(self, *_args, **_kwargs):
            pass

    graph_module.StateGraph = StateGraph
    graph_module.END = object()
    langgraph = types.ModuleType("langgraph")
    langgraph.graph = graph_module
    return {"langgraph": langgraph, "langgraph.graph": graph_module}


class GraphContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        rag_utils = types.ModuleType("utils.rag_utils")
        rag_utils.clean_llm_answer = lambda value: value
        rag_utils.aggregate_results = lambda value: value
        performance_config = types.ModuleType("utils.performance_config")
        performance_config.PERFORMANCE_SETTINGS = types.SimpleNamespace(
            rag_retrieval_top_k=10,
            rag_related_questions_rerank_threshold=0.1,
        )
        utils = types.ModuleType("utils")
        utils.__path__ = []
        utils.rag_utils = rag_utils
        utils.performance_config = performance_config
        stubs = graph_import_stubs()
        stubs.update(
            {
                "utils": utils,
                "utils.rag_utils": rag_utils,
                "utils.performance_config": performance_config,
            }
        )
        self.patch = ModulePatch(stubs)
        self.patch.__enter__()
        self.module = load_module(
            "agent_graph_under_test", ROOT / "agent_graph.py"
        )

    async def asyncTearDown(self):
        self.patch.__exit__(None, None, None)
        sys.modules.pop("agent_graph_under_test", None)

    async def test_classifier_is_awaited(self):
        class Classifier:
            async def classify(self, query):
                await asyncio.sleep(0)
                return {"type": "general", "scenario_id": None}

        state = {"messages": [{"role": "user", "content": "original"}]}
        result = await self.module.make_classify_intent(Classifier(), {})(state)
        self.assertEqual(result["intent"]["type"], "general")

    async def test_general_path_keeps_original_and_uses_rewritten_for_ai_calls(self):
        class Result:
            content = "question: candidate\nanswer: response"

        class SearchEngine:
            def __init__(self):
                self.calls = []

            async def rerank(self, query, candidates, threshold):
                self.calls.append((query, candidates, threshold))
                return list(reversed(candidates))

        class Rag:
            def __init__(self):
                self.search_engine = SearchEngine()

            async def retrieve(self, query, top_k, allowed_docs):
                self.retrieve_query = query
                return [Result()]

            def generate_context(self, results):
                return "context"

            async def answer(self, **kwargs):
                self.answer_question = kwargs["user_question"]
                return "answer"

        rag = Rag()
        state = {
            "messages": [{"role": "user", "content": "original"}],
            "retrieval_query": "rewritten",
            "allowed_docs": ["General_FAQ"],
            "doc_category": "FAQ",
        }
        result = await self.module.make_handle_general(rag)(state)

        self.assertEqual(state["messages"][0]["content"], "original")
        self.assertEqual(rag.retrieve_query, "rewritten")
        self.assertEqual(rag.answer_question, "rewritten")
        self.assertEqual(len(rag.search_engine.calls), 1)
        self.assertEqual(rag.search_engine.calls[0][0], "rewritten")
        self.assertEqual(rag.search_engine.calls[0][2], 0.1)
        self.assertEqual(result["related_questions"][0]["question"], "candidate")

    async def test_chitchat_answer_is_awaited(self):
        class Rag:
            async def answer(self, **kwargs):
                await asyncio.sleep(0)
                return "chitchat answer"

        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "related_questions": [],
        }
        result = await self.module.make_handle_chitchat(Rag())(state)
        self.assertEqual(result["last_answer"], "chitchat answer")


class RewritingContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        config_module = types.ModuleType("new_architecture.app.config")

        class Config:
            SESSION_SUMMARY_PROMPT = "{current_summary}:{dropped_user_msg}:{dropped_ai_msg}"
            QUERY_REWRITE_PROMPT = "{current_history}:{current_query}"

        config_module.Config = Config
        transformers = types.ModuleType("transformers")
        transformers.AutoModelForCausalLM = object
        transformers.AutoTokenizer = object
        self.patch = ModulePatch(
            {
                "new_architecture.app.config": config_module,
                "torch": types.ModuleType("torch"),
                "transformers": transformers,
            }
        )
        self.patch.__enter__()
        self.module = load_module(
            "new_architecture.app.services.history.rewriting_under_test",
            ROOT / "new_architecture/app/services/history/rewriting.py",
        )

    async def asyncTearDown(self):
        self.patch.__exit__(None, None, None)
        sys.modules.pop(
            "new_architecture.app.services.history.rewriting_under_test", None
        )

    async def test_rewrite_and_summary_await_generation(self):
        class Rag:
            def __init__(self):
                self.calls = []

            async def generate_text(self, prompt):
                await asyncio.sleep(0)
                self.calls.append(prompt)
                return "<rewrite>standalone rewrite</rewrite>"

        rag = Rag()
        service = self.module.HistoryRewritingService.__new__(
            self.module.HistoryRewritingService
        )
        service.rag_system = rag
        service.config = sys.modules["new_architecture.app.config"].Config()

        unchanged = await service.rewrite_query("original", "[بدون مکالمه قبلی]")
        rewritten = await service.rewrite_query("original", "history")
        summary = await service.summarize_history("summary", "user", "assistant")

        self.assertEqual(unchanged, "original")
        self.assertEqual(rewritten, "standalone rewrite")
        self.assertEqual(summary, "<rewrite>standalone rewrite</rewrite>")
        self.assertEqual(len(rag.calls), 2)


class AgentServiceContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.graph = self.FakeGraph()
        agent_graph = types.ModuleType("agent_graph")
        agent_graph.AgentState = dict
        agent_graph.build_graph = lambda **_kwargs: self.graph

        database = types.ModuleType(
            "new_architecture.app.services.history.database"
        )
        database.DatabaseManager = object
        database.ChatManager = object
        self.patch = ModulePatch(
            {
                "agent_graph": agent_graph,
                "new_architecture.app.services.history.database": database,
            }
        )
        self.patch.__enter__()
        self.module = load_module(
            "agent_service_under_test", ROOT / "agent_service.py"
        )
        self.original_to_thread = self.module.asyncio.to_thread

        async def direct_call(function, *args, **kwargs):
            return function(*args, **kwargs)

        self.module.asyncio.to_thread = direct_call

    async def asyncTearDown(self):
        self.module.asyncio.to_thread = self.original_to_thread
        self.patch.__exit__(None, None, None)
        sys.modules.pop("agent_service_under_test", None)

    class FakeGraph:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.inputs = []

        async def ainvoke(self, state):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.inputs.append(
                (state["latest_user_input"], state["retrieval_query"])
            )
            await asyncio.sleep(0.01)
            state["messages"].extend(
                [
                    {"role": "user", "content": state["latest_user_input"]},
                    {"role": "assistant", "content": "answer"},
                ]
            )
            self.active -= 1
            return state

    class FakeDb:
        def __init__(self):
            self.metadata = {}

        def get_session_by_id(self, _session_id):
            return {"user_id": 7}

        def get_session_metadata(self, _session_id):
            return self.metadata.copy()

        def update_session_metadata(self, _session_id, metadata):
            self.metadata = metadata

    async def test_graph_is_not_compiled_twice_and_same_session_is_serialized(self):
        db = self.FakeDb()
        service = self.module.AgentService(
            rag_system=object(),
            intent_classifier=object(),
            scenarios_db={},
            db_manager=db,
            chat_manager=object(),
        )

        await asyncio.gather(
            service.process_message("1", "original one", retrieval_query="rewrite one"),
            service.process_message("1", "original two", retrieval_query="rewrite two"),
        )

        self.assertEqual(self.graph.max_active, 1)
        self.assertEqual(
            self.graph.inputs,
            [("original one", "rewrite one"), ("original two", "rewrite two")],
        )


class PersistenceContractTests(unittest.TestCase):
    def setUp(self):
        psycopg2 = types.ModuleType("psycopg2")
        psycopg2.Error = Exception
        extras = types.ModuleType("psycopg2.extras")
        extras.RealDictCursor = object
        psycopg2.extras = extras
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        self.patch = ModulePatch(
            {
                "psycopg2": psycopg2,
                "psycopg2.extras": extras,
                "dotenv": dotenv,
            }
        )
        self.patch.__enter__()
        self.module = load_module(
            "database_under_test",
            ROOT / "new_architecture/app/services/history/database.py",
        )

    def tearDown(self):
        self.patch.__exit__(None, None, None)
        sys.modules.pop("database_under_test", None)

    def test_assistant_updates_the_explicit_query(self):
        manager = self.module.DatabaseManager.__new__(self.module.DatabaseManager)
        calls = []

        def execute(_self, sql, params=None, fetch=None):
            calls.append((sql, params, fetch))
            if fetch == "one":
                return {"id": 17}
            return True

        manager._execute = types.MethodType(execute, manager)
        manager.update_query_response = types.MethodType(
            lambda _self, query_id, content: calls.append(
                ("update", query_id, content)
            ),
            manager,
        )
        manager.update_session_activity = lambda _session_id: None

        result = manager.add_message(
            session_id=5,
            user_id=9,
            role="assistant",
            content="answer",
            query_id=17,
        )

        self.assertEqual(calls[0][1], (17, 5, 9))
        self.assertIn(("update", 17, "answer"), calls)
        self.assertEqual(result["id"], "17")


class TeiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        numpy = types.ModuleType("numpy")
        numpy.ndarray = object
        parsivar = types.ModuleType("parsivar")
        parsivar.Normalizer = parsivar.Tokenizer = parsivar.FindStems = object
        rank_bm25 = types.ModuleType("rank_bm25")
        rank_bm25.BM25Okapi = object
        qdrant_client = types.ModuleType("qdrant_client")
        qdrant_client.QdrantClient = object
        qdrant_http = types.ModuleType("qdrant_client.http")
        qdrant_http.models = types.SimpleNamespace()
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        self.patch = ModulePatch(
            {
                "numpy": numpy,
                "parsivar": parsivar,
                "rank_bm25": rank_bm25,
                "qdrant_client": qdrant_client,
                "qdrant_client.http": qdrant_http,
                "dotenv": dotenv,
            }
        )
        self.patch.__enter__()
        self.module = load_module(
            "persian_hybrid_search_under_test",
            ROOT / "utils/persian_hybrid_search.py",
        )

    async def asyncTearDown(self):
        self.patch.__exit__(None, None, None)
        sys.modules.pop("persian_hybrid_search_under_test", None)

    async def test_embedding_and_reranking_payloads_and_index_mapping(self):
        class Response:
            def __init__(self, body):
                self.body = body

            def raise_for_status(self):
                return None

            def json(self):
                return self.body

        class Http:
            def __init__(self):
                self.calls = []

            async def post(self, url, json):
                self.calls.append((url, json))
                if url.endswith("/embed"):
                    return Response([[0.1] * 1024])
                return Response(
                    [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.2}]
                )

        search = self.module.PersianHybridSearch.__new__(
            self.module.PersianHybridSearch
        )
        search._http = Http()
        search.tei_embed_url = "http://localhost:7997"
        search.tei_rerank_url = "http://localhost:7998"
        search._expected_embedding_dimensions = 1024
        search.embedding_client = self.module.TeiEmbeddingClient(
            search.tei_embed_url,
            search._http,
            expected_dimension=1024,
        )

        embedding = await search._encode_query("query")
        candidates = [
            {"question": "zero", "answer": "answer zero"},
            {"question": "one", "answer": "answer one"},
        ]
        ranked = await search.rerank("query", candidates, threshold=0.1)

        self.assertEqual(embedding, [0.1] * 1024)
        self.assertEqual(
            search._http.calls[0],
            (
                "http://localhost:7997/embed",
                {
                    "inputs": "query",
                    "prompt_name": "query",
                    "normalize": True,
                },
            ),
        )
        self.assertEqual(
            search._http.calls[1],
            (
                "http://localhost:7998/rerank",
                {"query": "query", "texts": ["zero", "one"]},
            ),
        )
        self.assertEqual(ranked, [candidates[1], candidates[0]])

    async def test_invalid_reranker_index_is_rejected(self):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return [{"index": 4, "score": 1.0}]

        class Http:
            async def post(self, _url, json):
                return Response()

        search = self.module.PersianHybridSearch.__new__(
            self.module.PersianHybridSearch
        )
        search._http = Http()
        search.tei_rerank_url = "http://localhost:7998"
        with self.assertRaises(ValueError):
            await search.rerank(
                "query", [{"question": "only candidate"}], threshold=0.1
            )

    async def test_sync_kb_embedding_reuses_persistent_client(self):
        calls = []

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return [[0.3] * 1024]

        class Client:
            def post(self, url, json):
                calls.append((url, json))
                return Response()

        search = self.module.PersianHybridSearch.__new__(
            self.module.PersianHybridSearch
        )
        search.tei_embed_url = "http://localhost:7997"
        search._sync_http = Client()
        search._expected_embedding_dimensions = 1024
        first = search.embed_documents_sync(["chunk"])[0]
        second = search.embed_documents_sync(["chunk"])[0]

        self.assertEqual(first, [0.3] * 1024)
        self.assertEqual(second, [0.3] * 1024)
        self.assertEqual(
            calls,
            [
                (
                    "http://localhost:7997/embed",
                    {"inputs": ["chunk"], "normalize": True},
                ),
                (
                    "http://localhost:7997/embed",
                    {"inputs": ["chunk"], "normalize": True},
                ),
            ],
        )


class StaticContractTests(unittest.TestCase):
    def test_classifier_and_public_callers_are_async(self):
        classifier_tree = ast.parse((ROOT / "intent_classifier.py").read_text())
        classifier = next(
            node
            for node in ast.walk(classifier_tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "classify"
        )
        self.assertTrue(any(isinstance(node, ast.Await) for node in ast.walk(classifier)))

        for path, function_name in [
            (ROOT / "main.py", "query_documents"),
            (ROOT / "mobile_api.py", "gateway_talk"),
        ]:
            tree = ast.parse(path.read_text())
            function = next(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name == function_name
            )
            wait_calls = [
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "wait_for"
            ]
            self.assertEqual(len(wait_calls), 1, f"{path}:{function_name}")

        main_tree = ast.parse((ROOT / "main.py").read_text())
        mass_route = next(
            node
            for node in ast.walk(main_tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "process_mass_answer"
        )
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "wait_for"
                for node in ast.walk(mass_route)
            )
        )

        query_pipeline = next(
            node
            for node in ast.walk(main_tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_query_documents"
        )
        assigned_names = {
            target.id
            for node in ast.walk(query_pipeline)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            if isinstance(target, ast.Name)
        }
        request_query_writes = [
            node
            for node in ast.walk(query_pipeline)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "query_req"
            and node.attr == "query"
            and isinstance(node.ctx, ast.Store)
        ]
        self.assertIn("original_query", assigned_names)
        self.assertIn("normalized_query", assigned_names)
        self.assertEqual(request_query_writes, [])

    def test_no_active_sentence_transformer_or_query_encoder_reference(self):
        paths = [
            ROOT / "intent_classifier.py",
            ROOT / "main.py",
            ROOT / "kb_manager.py",
            ROOT / "utils/persian_hybrid_search.py",
        ]
        for path in paths:
            tree = ast.parse(path.read_text())
            names = {
                node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
            }
            attributes = {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            }
            self.assertNotIn("SentenceTransformer", names, str(path))
            self.assertNotIn("CrossEncoder", names, str(path))
            self.assertNotIn("query_encoder", attributes, str(path))

    def test_related_questions_have_one_canonical_rerank_call(self):
        graph_tree = ast.parse((ROOT / "agent_graph.py").read_text())
        endpoint_trees = [
            ast.parse((ROOT / "main.py").read_text()),
            ast.parse((ROOT / "mobile_api.py").read_text()),
        ]

        graph_rerank_calls = [
            node
            for node in ast.walk(graph_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "rerank"
        ]
        self.assertEqual(len(graph_rerank_calls), 1)

        for tree in endpoint_trees:
            endpoint_rerank_calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "rerank"
            ]
            self.assertEqual(endpoint_rerank_calls, [])
            self.assertNotIn(
                "reranker_model",
                {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)},
            )


if __name__ == "__main__":
    unittest.main()
