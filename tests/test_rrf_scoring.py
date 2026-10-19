"""Exercise actual search fusion with frozen synthetic branch evidence."""
import unittest
from tests.rrf_fixtures import case_from_ids, controlled_cases, replay_search


class RrfScoringTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, case):
        return await replay_search(case).search(case["query"], top_k=case["top_k"], allowed_docs=["synthetic-FAQ"])

    async def test_rank_one_sparse_only_is_one_over_61(self):
        rows = await self.run_case(case_from_ids(["a"], []))
        self.assertAlmostEqual(rows[0].score, 1/61, delta=0.5e-6)

    async def test_rank_one_dense_only_is_one_over_61(self):
        rows = await self.run_case(case_from_ids([], ["a"]))
        self.assertAlmostEqual(rows[0].score, 1/61, delta=0.5e-6)

    async def test_rank_one_both_branches_is_two_over_61(self):
        rows = await self.run_case(case_from_ids(["a"], ["a"]))
        self.assertAlmostEqual(rows[0].score, 2/61, delta=0.5e-6)

    async def test_dense_rank_100_is_one_over_160(self):
        # Inject a rank-100 branch to test fusion independently of P2 limits.
        case = case_from_ids([], [f"id-{i:03}" for i in range(1, 101)], top_k=100)
        rows = await self.run_case(case)
        self.assertEqual(rows[-1].doc_id, "id-100")
        self.assertEqual(rows[-1].score, 1/160)

    async def test_different_ranks_sum_present_contributions(self):
        rows = await self.run_case(case_from_ids(["a", "b", "target"], ["z", "target"]))
        target = next(r for r in rows if r.doc_id == "target")
        self.assertAlmostEqual(target.score, 1/63 + 1/62, delta=0.5e-6)

    async def test_disjoint_branches_do_not_add_absent_contributions(self):
        rows = await self.run_case(case_from_ids(["s"], ["d"]))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.score == round(1/61, 6) for r in rows))

    async def test_empty_branches_return_no_candidates(self):
        self.assertEqual(await self.run_case(case_from_ids([], [])), [])

    async def test_empty_chunk_corpus_returns_no_candidates(self):
        case = case_from_ids(["a"], ["a"])
        case["chunks"] = {}
        self.assertEqual(await self.run_case(case), [])

    async def test_union_deduplicates_overlap_and_keeps_full_content(self):
        case = case_from_ids(["a", "b"], ["b", "c"])
        rows = await self.run_case(case)
        self.assertEqual({r.doc_id for r in rows}, {"a", "b", "c"})
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row.content, case["chunks"][row.doc_id]["text"])
            self.assertEqual(row.metadata["document_name"], "synthetic-FAQ")

    async def test_ties_preserve_dense_secondary_score(self):
        rows = await self.run_case(case_from_ids(["s"], ["d"]))
        self.assertEqual([r.doc_id for r in rows], ["d", "s"])

    async def test_exact_ties_use_string_id_and_are_repeatable(self):
        case = case_from_ids(["b", "a"], ["a", "b"])
        for branch in (case["sparse"], case["dense"]):
            for row in branch: row["score"] = 1.0
        first = await self.run_case(case)
        second = await self.run_case(case)
        self.assertEqual([r.doc_id for r in first], ["a", "b"])
        self.assertEqual(first, second)

    async def test_top_k_and_original_rrf_rank_track_fused_order(self):
        rows = await self.run_case(case_from_ids(["a", "b", "c"], ["c"], top_k=2))
        self.assertEqual([r.doc_id for r in rows], ["c", "a"])
        self.assertEqual([r.original_rrf_rank for r in rows], [1, 2])

    async def test_complementary_facts_reach_pool_for_paraphrases(self):
        for case in controlled_cases():
            with self.subTest(case=case["id"]):
                rows = await self.run_case(case)
                self.assertEqual(len(rows), 50)
                self.assertEqual([r.doc_id for r in rows[:2]], case["relevant_ids"])
                selected = {r.doc_id for r in rows}
                self.assertTrue(all(f["entry"] in selected for f in case["required_facts"]))
