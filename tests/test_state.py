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

    def test_opencode_properties_contain_session_id(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({
            "data": {
                "id": "evt-1",
                "type": "message.part.updated",
                "properties": {"sessionID": "ses-real", "messageID": "msg-1"},
            },
            "pid": 12,
        })
        session = store.snapshot()["sessions"][0]
        self.assertEqual(session["sessionID"], "ses-real")
        self.assertEqual(session["pid"], 12)

    def test_session_created_info_contains_id_and_directory(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({
            "pid": 13,
            "directory": "/tmp/other-repo",
            "data": {
                "id": "evt-created",
                "type": "session.created",
                "properties": {"info": {"id": "ses-created"}},
            },
        })
        session = store.snapshot()["sessions"][0]
        self.assertEqual(session["sessionID"], "ses-created")
        self.assertEqual(session["directory"], "/tmp/other-repo")

    def test_event_id_is_not_a_session_id(self):
        store = StateStore(pid_checker=lambda pid: True)
        with self.assertRaises(ValueError):
            store.apply_event({"id": "evt-only", "type": "server.connected"})

    def test_message_parent_does_not_hide_master_session(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({"sessionID": "session", "parentID": "message"})
        session = store.snapshot()["sessions"][0]
        self.assertTrue(session["master"])
        self.assertIsNone(session["parentID"])

    def test_busy_idle_status_and_completion_notification(self):
        notices = []
        store = StateStore(notifier=lambda title, message: notices.append((title, message)))
        store.apply_event({"sessionID": "s", "status": {"type": "busy"}})
        store.apply_event({"sessionID": "s", "status": {"type": "idle"}})
        self.assertEqual(store.snapshot()["sessions"][0]["status"], "normal")
        self.assertEqual(notices, [("Agent completato", "s")])

    def test_working_transition_is_not_notified(self):
        notices = []
        store = StateStore(notifier=lambda title, message: notices.append((title, message)))
        store.apply_event({"sessionID": "s", "status": "normal"})
        store.apply_event({"sessionID": "s", "status": "working"})
        self.assertEqual(notices, [])

    def test_nested_message_tokens_and_cache_are_aggregated(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({
            "type": "message.updated",
            "properties": {
                "info": {
                    "id": "msg-1",
                    "sessionID": "s",
                    "tokens": {"input": 10, "output": 4, "reasoning": 2,
                                "cache": {"read": 7, "write": 3}},
                }
            },
        })
        self.assertEqual(store.snapshot()["sessions"][0]["tokens"], {
            "input": 10, "output": 4, "reasoning": 2,
            "cacheRead": 7, "cacheWrite": 3, "total": 14,
        })

    def test_tool_event_extracts_session_and_activity(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({
            "kind": "tool.execute.before",
            "data": {"input": {"sessionID": "s", "tool": "task",
                                  "args": {"description": "Lavoro figlio"}}},
        })
        session = store.snapshot()["sessions"][0]
        self.assertEqual(session["activity"], "Lavoro figlio")

    def test_child_arriving_before_parent_is_linked_later(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({"sessionID": "child", "parentID": "master"})
        store.apply_event({"sessionID": "master"})
        master = next(s for s in store.snapshot()["sessions"] if s["sessionID"] == "master")
        child = next(s for s in store.snapshot()["sessions"] if s["sessionID"] == "child")
        self.assertEqual(master["children"], ["child"])
        self.assertFalse(child["master"])

    def test_token_update_replaces_previous_message_value(self):
        store = StateStore(pid_checker=lambda pid: True)
        store.apply_event({"sessionID": "s", "messageID": "m", "tokens": {"input": 2}})
        store.apply_event({"sessionID": "s", "messageID": "m", "tokens": {"input": 20}})
        self.assertEqual(store.snapshot()["sessions"][0]["tokens"]["input"], 20)

    def test_permission_reply_clears_confirmation_and_tool_error_notifies(self):
        notices = []
        store = StateStore(notifier=lambda title, message: notices.append((title, message)))
        store.apply_event({"sessionID": "s", "type": "session.status", "status": {"type": "busy"}})
        store.apply_event({"sessionID": "s", "type": "permission.asked"})
        self.assertEqual(store.snapshot()["sessions"][0]["status"], "confirm")
        store.apply_event({"sessionID": "s", "type": "permission.replied"})
        self.assertEqual(store.snapshot()["sessions"][0]["status"], "normal")
        store.apply_event({"kind": "tool.execute.after", "data": {
            "input": {"sessionID": "s", "tool": "bash"},
            "output": {"error": "fallimento"},
        }})
        self.assertEqual(store.snapshot()["sessions"][0]["status"], "error")
        self.assertTrue(any(title == "Agent error" for title, _ in notices))


if __name__ == "__main__":
    unittest.main()
