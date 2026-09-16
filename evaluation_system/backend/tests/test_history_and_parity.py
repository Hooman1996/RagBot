from __future__ import annotations

import unittest
import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from evaluation_system.backend.app.services.history_state import (
    exact_agent_state_from_turns,
)


class ExactHistoryStateTests(unittest.TestCase):
    def test_no_previous_turns_returns_none(self):
        self.assertIsNone(exact_agent_state_from_turns([]))

    def test_latest_persisted_state_is_returned_exactly(self):
        first = {"messages": [{"role": "user", "content": "one"}]}
        latest = {
            "messages": [
                {"role": "custom", "content": "untouched", "extra": True}
            ],
            "nested": {"values": [1, 2]},
        }
        turns = [
            SimpleNamespace(metadata_json={"agent_state_after": first}),
            SimpleNamespace(metadata_json={"agent_state_after": latest}),
        ]

        self.assertEqual(exact_agent_state_from_turns(turns), latest)

    def test_returned_state_is_deeply_detached_and_storage_is_not_mutated(self):
        stored = {
            "messages": [{"role": "assistant", "content": "answer"}],
            "nested": {"values": [1]},
        }
        original = deepcopy(stored)
        turn = SimpleNamespace(metadata_json={"agent_state_after": stored})

        restored = exact_agent_state_from_turns([turn])
        restored["messages"][0]["content"] = "changed"
        restored["nested"]["values"].append(2)

        self.assertEqual(stored, original)

    def test_previous_completed_turn_without_any_exact_state_fails(self):
        turn = SimpleNamespace(metadata_json={"other": "metadata"})
        with self.assertRaisesRegex(
            RuntimeError, "EVALUATION_HISTORY_STATE_MISSING"
        ):
            exact_agent_state_from_turns([turn])

    def test_non_dictionary_state_is_not_accepted(self):
        turns = [
            {"metadata": {"agent_state_after": ["not", "state"]}},
        ]
        with self.assertRaisesRegex(
            RuntimeError, "EVALUATION_HISTORY_STATE_MISSING"
        ):
            exact_agent_state_from_turns(turns)


class RunnerHistoryQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_queries_only_prior_completed_turns(self):
        from evaluation_system.backend.app.worker.runner import EvaluationRunExecutor

        state = {"opaque": {"messages": ["unchanged"]}}
        completed = SimpleNamespace(
            metadata_json={"agent_state_after": state}
        )

        class Session:
            query = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def scalars(self, query):
                self.query = query
                return [completed]

        session = Session()
        runner = EvaluationRunExecutor(
            session_factory=lambda: session,
            ragbot_client=AsyncMock(),
        )

        restored = await runner._state_before(uuid.uuid4(), 3)

        self.assertEqual(restored, state)
        params = session.query.compile().params
        self.assertIn("COMPLETED", params.values())
        self.assertIn(3, params.values())


if __name__ == "__main__":
    unittest.main()
