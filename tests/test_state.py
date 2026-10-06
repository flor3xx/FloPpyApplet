import unittest

from daemon.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_sessions_parent_children_and_instance_number(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({"sessionID": "master", "pid": 10})
        store.apply_event({"sessionID": "child", "pid": 11, "parentID": "master"})
        state = store.snapshot()
        master = next(s for s in state["sessions"] if s["sessionID"] == "master")
        child = next(s for s in state["sessions"] if s["sessionID"] == "child")
        self.assertTrue(master["master"])
        self.assertEqual(master["children"], ["child"])
        self.assertEqual(child["parentID"], "master")

    def test_token_message_dedup_and_status_notification(self):
        notices = []
        store = StateStore(notifier=lambda title, message: notices.append((title, message)))
        event = {"sessionID": "s", "messageID": "m", "tokens": {"input": 2, "output": 3}}
        store.apply_event(event)
        store.apply_event(event)
        store.apply_event({"sessionID": "s", "status": "confirm"})
        store.apply_event({"sessionID": "s", "status": "confirm"})
        session = store.snapshot()["sessions"][0]
        self.assertEqual(session["tokens"], {
            "input": 2, "output": 3, "reasoning": 0,
            "cacheRead": 0, "cacheWrite": 0, "total": 5,
        })
        self.assertEqual(len(notices), 1)

    def test_first_event_never_notifies_and_stale_cleanup(self):
        notices = []
        store = StateStore(notifier=lambda *args: notices.append(args), pid_checker=lambda pid: pid == 2)
        store.apply_event({"sessionID": "dead", "pid": 1, "status": "error"})
        store.apply_event({"sessionID": "live", "pid": 2})
        self.assertEqual(notices, [])
        self.assertEqual(store.cleanup_stale(), ["dead"])
        self.assertEqual([s["sessionID"] for s in store.snapshot()["sessions"]], ["live"])


if __name__ == "__main__":
    unittest.main()
