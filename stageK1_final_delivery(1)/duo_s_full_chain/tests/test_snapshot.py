from __future__ import annotations

import dataclasses
import threading
import unittest

from duo_s_full_chain.runtime.snapshot import RuntimeSnapshot, SnapshotStore


class SnapshotTests(unittest.TestCase):
    def test_snapshot_is_immutable_and_safety_updates_are_thread_safe(self) -> None:
        store = SnapshotStore(RuntimeSnapshot())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            store.get().gesture_id = 2  # type: ignore[misc]

        def update() -> None:
            for _ in range(100):
                store.note_safety("concurrent_test")

        threads = [threading.Thread(target=update) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        snapshot = store.get()
        self.assertEqual(snapshot.safety_event_count, 400)
        self.assertEqual(dict(snapshot.safety_counters), {"concurrent_test": 400})


if __name__ == "__main__":
    unittest.main()
