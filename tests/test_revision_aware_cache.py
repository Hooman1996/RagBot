import unittest

from utils.revision_cache import RevisionAwareCache


class RevisionAwareCacheTests(unittest.TestCase):
    def test_shared_revision_refreshes_independent_worker_caches(self):
        shared = {"revision": "v1", "content": "old"}
        worker_a = RevisionAwareCache()
        worker_b = RevisionAwareCache()

        def read(cache):
            return cache.get_or_build(
                ("General_FAQ",),
                shared["revision"],
                lambda: shared["content"],
            )

        self.assertEqual(read(worker_a), "old")
        self.assertEqual(read(worker_b), "old")
        shared.update(revision="v2", content="new")
        self.assertEqual(read(worker_a), "new")
        self.assertEqual(read(worker_b), "new")

    def test_same_revision_reuses_value_and_clear_forces_rebuild(self):
        cache = RevisionAwareCache()
        builds = 0

        def build():
            nonlocal builds
            builds += 1
            return builds

        self.assertEqual(cache.get_or_build("key", "v1", build), 1)
        self.assertEqual(cache.get_or_build("key", "v1", build), 1)
        self.assertEqual(builds, 1)
        self.assertEqual(cache.clear(), 1)
        self.assertEqual(cache.get_or_build("key", "v1", build), 2)

    def test_missing_shared_revision_never_reuses_worker_local_value(self):
        cache = RevisionAwareCache()
        builds = 0

        def build():
            nonlocal builds
            builds += 1
            return builds

        self.assertEqual(cache.get_or_build("key", None, build), 1)
        self.assertEqual(cache.get_or_build("key", None, build), 2)


if __name__ == "__main__":
    unittest.main()
