from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PreclassifiedGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_preclassified_intent_bypasses_graph_classifier(self):
        graph_module = types.ModuleType("langgraph.graph")
        graph_module.StateGraph = object
        graph_module.END = object()
        langgraph_module = types.ModuleType("langgraph")
        langgraph_module.graph = graph_module
        previous = {
            name: sys.modules.get(name)
            for name in ("langgraph", "langgraph.graph")
        }
        sys.modules["langgraph"] = langgraph_module
        sys.modules["langgraph.graph"] = graph_module
        module_name = "agent_graph_history_routing_test"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, ROOT / "agent_graph.py"
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            assert spec.loader is not None
            spec.loader.exec_module(module)

            class Classifier:
                def __init__(self):
                    self.queries = []

                async def classify(self, query):
                    self.queries.append(query)
                    return {"type": "chitchat", "scenario_id": "chitchat"}

            classifier = Classifier()
            preclassified = {"type": "general", "scenario_id": None}
            state = {
                "messages": [{"role": "user", "content": "انقضا چی"}],
                "preclassified_intent": preclassified,
            }
            result = await module.make_classify_intent(
                classifier, scenarios_db={}
            )(state)

            self.assertEqual(classifier.queries, [])
            self.assertEqual(result["intent"], preclassified)
            self.assertNotIn("preclassified_intent", result)
        finally:
            sys.modules.pop(module_name, None)
            for name, prior in previous.items():
                if prior is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = prior


if __name__ == "__main__":
    unittest.main()
