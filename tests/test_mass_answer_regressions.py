"""Regression contracts for the audited mass-answer timeout and parity defects."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _async_function(path: Path, name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )


class MassAnswerTimeoutRegressionTests(unittest.TestCase):
    def test_lifespan_constructs_answering_dependencies_in_valid_order(self):
        lifespan = _async_function(ROOT / "main.py", "lifespan")
        assignments = {
            target.id: (node, call)
            for node in ast.walk(lifespan)
            if isinstance(node, ast.Assign)
            for target in node.targets
            for call in (
                node.value.value
                if isinstance(node.value, ast.Await)
                else node.value,
            )
            if isinstance(target, ast.Name)
            and target.id
            in {
                "rag_system",
                "history_rewriting_service",
                "intent_classifier",
                "agent_service",
                "answering_service",
                "mass_answer_processor",
            }
            and isinstance(call, ast.Call)
        }

        expected_order = (
            "rag_system",
            "history_rewriting_service",
            "intent_classifier",
            "agent_service",
            "answering_service",
            "mass_answer_processor",
        )
        self.assertEqual(
            sorted(
                expected_order,
                key=lambda name: assignments[name][0].lineno,
            ),
            list(expected_order),
        )

        rag_keywords = {
            keyword.arg for keyword in assignments["rag_system"][1].keywords
        }
        agent_keywords = {
            keyword.arg for keyword in assignments["agent_service"][1].keywords
        }
        self.assertNotIn("category_resolver", rag_keywords)
        self.assertIn("category_resolver", agent_keywords)

    def test_http_route_does_not_apply_interactive_deadline_to_complete_file(self):
        route = _async_function(ROOT / "main.py", "process_mass_answer")
        whole_file_waits = []
        for node in ast.walk(route):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "wait_for"
                and node.args
            ):
                continue
            awaited = node.args[0]
            if (
                isinstance(awaited, ast.Call)
                and isinstance(awaited.func, ast.Name)
                and awaited.func.id == "_process_mass_answer"
            ):
                whole_file_waits.append(node)

        self.assertEqual(
            whole_file_waits,
            [],
            "the 50-second interactive deadline must not wrap the entire file",
        )

    def test_batch_pipeline_does_not_duplicate_low_level_rag_calls(self):
        pipeline = _async_function(ROOT / "main.py", "_process_mass_answer")
        direct_calls = [
            node.func.attr
            for node in ast.walk(pipeline)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"retrieve", "answer"}
        ]
        self.assertEqual(
            direct_calls,
            [],
            "mass answer must call the shared application answering service",
        )

    def test_batch_rows_are_not_implemented_as_one_sequential_dataframe_loop(self):
        pipeline = _async_function(ROOT / "main.py", "_process_mass_answer")
        dataframe_loops = [
            node
            for node in ast.walk(pipeline)
            if isinstance(node, (ast.For, ast.AsyncFor))
            and isinstance(node.iter, ast.Subscript)
            and isinstance(node.iter.value, ast.Name)
            and node.iter.value.id == "df"
        ]
        self.assertEqual(
            dataframe_loops,
            [],
            "rows must be handled by a bounded worker abstraction",
        )


if __name__ == "__main__":
    unittest.main()
