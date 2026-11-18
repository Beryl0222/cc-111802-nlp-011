import json
import tempfile
import unittest
from pathlib import Path

from nlp_school_policy_entity_events.repository import RecordRepository
from nlp_school_policy_entity_events.workflow import TextWorkflow

FIXTURES = Path("fixtures")


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workflow = TextWorkflow(RecordRepository(Path(self.directory.name) / "records.json"))

    def ingest_session(self):
        self.workflow.ingest(load_fixture("records.json"))
        self.workflow.ingest(load_fixture("review-session.json"))

    def test_trace_item_recovers_turns_fragments_and_decisions(self):
        self.ingest_session()
        bundle = self.workflow.trace_item("hw-b-1")
        self.assertEqual(bundle["decision"]["decision_id"], "dec-b-1")
        self.assertEqual(bundle["decision"]["reviewer"], "王老师")
        self.assertEqual(bundle["candidate"]["candidate_id"], "cand-b-b")
        self.assertEqual(bundle["turn"]["turn_id"], "02")
        conversation = bundle["conversation"]
        self.assertEqual(conversation["conversation_id"], "lesson-b")
        self.assertEqual([turn["turn_id"] for turn in conversation["turns"]], ["01", "02", "03"])
        basis = bundle["basis"][0]
        self.assertEqual((basis["document"], basis["fragment_id"], basis["revision"]),
                         ("reading-textbook", "ex-2", 1))
        self.assertEqual(basis["fragment_text"], "课后第2题：把结尾改为景物描写，不少于一百五十字。")

    def test_conversation_shows_partial_adoption_of_candidates(self):
        self.ingest_session()
        view = self.workflow.conversation_view("lesson-b")
        self.assertTrue(view["complete"])
        candidates = {entry["candidate_id"]: entry["adoption"]["status"]
                      for entry in view["turns"][1]["candidates"]}
        self.assertEqual(candidates, {
            "cand-b-a": "rejected",
            "cand-b-b": "modified",
            "cand-b-c": "adopted",
        })

    def test_confirmation_is_scoped_to_task_not_generalized(self):
        self.ingest_session()
        basis = self.workflow.trace_item("hw-b-2")["basis"][0]
        self.assertEqual(basis["confirmation_state"], "unconfirmed")
        self.assertIsNone(basis["confirmation"])
        self.assertEqual(basis["other_task_confirmations"], ["reading-lesson-c"])
        self.workflow.ingest([{
            "kind": "confirmation",
            "confirmation_id": "conf-b-9",
            "task_id": "reading-lesson-b",
            "document": "reading-textbook",
            "fragment_id": "ex-3",
            "revision": 1,
            "verdict": "confirmed",
            "reviewer": "李老师",
            "confirmed_at": "2026-11-19T11:00:00Z",
        }])
        bundle = self.workflow.trace_item("hw-b-2")
        self.assertEqual(bundle["basis"][0]["confirmation_state"], "confirmed")
        self.assertEqual(bundle["needs_recheck"], [])

    def test_history_restored_and_current_bases_flagged(self):
        self.ingest_session()
        bundle = self.workflow.trace_item("hw-b-1")
        basis = bundle["basis"][0]
        self.assertEqual(basis["fragment_text"], "课后第2题：把结尾改为景物描写，不少于一百五十字。")
        self.assertEqual(basis["current_revision"], 2)
        self.assertTrue(basis["stale"])
        self.assertEqual(basis["confirmation_state"], "outdated")
        self.assertTrue(any("需重新核对" in reason or "需重新核验" in reason
                            for reason in bundle["needs_recheck"]))
        flagged = {entry["item_id"] for entry in self.workflow.recheck_report()["items"]}
        self.assertIn("hw-b-1", flagged)
        self.assertIn("hw-b-2", flagged)
        self.workflow.ingest([
            {"kind": "decision", "decision_id": "dec-b-4", "task_id": "reading-lesson-b",
             "action": "modify", "reviewer": "王老师", "decided_at": "2026-11-20T09:00:00Z",
             "candidate_id": "cand-b-b", "turn_id": "02", "turn_revision": 1, "item_id": "hw-b-1",
             "text": "提高层：按课后第2题把结尾改为人物独白，不少于二百字。",
             "basis": [{"document": "reading-textbook", "fragment_id": "ex-2", "revision": 2}],
             "supersedes": "dec-b-1"},
            {"kind": "item", "item_id": "hw-b-1", "task_id": "reading-lesson-b", "revision": 2,
             "text": "提高层：按课后第2题把结尾改为人物独白，不少于二百字。",
             "decision_id": "dec-b-4", "recorded_at": "2026-11-20T09:00:30Z"},
            {"kind": "confirmation", "confirmation_id": "conf-b-2", "task_id": "reading-lesson-b",
             "document": "reading-textbook", "fragment_id": "ex-2", "revision": 2,
             "verdict": "confirmed", "reviewer": "王老师", "confirmed_at": "2026-11-20T09:01:00Z"},
        ])
        current = self.workflow.trace_item("hw-b-1")
        self.assertEqual(current["item"]["revision"], 2)
        self.assertEqual(current["basis"][0]["revision"], 2)
        self.assertEqual(current["needs_recheck"], [])
        self.assertEqual([entry["revision"] for entry in current["item_revisions"]], [1, 2])
        history = self.workflow.trace_item("hw-b-1", revision=1)
        self.assertEqual(history["decision"]["decision_id"], "dec-b-1")
        self.assertEqual(history["basis"][0]["fragment_text"],
                         "课后第2题：把结尾改为景物描写，不少于一百五十字。")

    def test_missing_turns_are_marked_never_fabricated(self):
        self.workflow.ingest(load_fixture("partial-conversation.json"))
        view = self.workflow.conversation_view("lesson-c")
        self.assertFalse(view["complete"])
        self.assertEqual(view["missing_turns"], ["02"])
        self.assertEqual(view["dangling_parents"], ["02"])
        self.assertEqual([turn["turn_id"] for turn in view["turns"]], ["01", "03"])
        self.workflow.ingest([{
            "record_id": "lesson-c-turn-02", "conversation_id": "lesson-c", "turn_id": "02",
            "role": "assistant", "source": "school-synthetic", "revision": 1,
            "observed_at": "2026-11-19T10:01:00Z",
            "text": "讨论题：比较两篇结尾各自留给读者的感受。",
            "parent_turn_id": "01", "task_id": "reading-lesson-c",
            "source_document": "reading-textbook", "source_revision": 1,
        }])
        view = self.workflow.conversation_view("lesson-c")
        self.assertTrue(view["complete"])
        self.assertEqual(view["missing_turns"], [])

    def test_reviewed_versions_survive_later_imports(self):
        turn_v1 = {"record_id": "lesson-d-turn-02", "conversation_id": "lesson-d", "turn_id": "02",
                   "role": "assistant", "source": "school-synthetic", "revision": 1,
                   "observed_at": "2026-11-19T12:00:00Z", "text": "原始建议：答案为42。",
                   "task_id": "math-lesson-d", "source_document": "algebra-textbook",
                   "source_revision": 3}
        self.workflow.ingest([
            turn_v1,
            {"kind": "candidate", "candidate_id": "cand-d-1", "conversation_id": "lesson-d",
             "turn_id": "02", "task_id": "math-lesson-d", "label": "唯一候选", "text": "答案为42。"},
            {"kind": "decision", "decision_id": "dec-d-1", "task_id": "math-lesson-d",
             "action": "adopt", "reviewer": "赵老师", "decided_at": "2026-11-19T12:05:00Z",
             "candidate_id": "cand-d-1", "turn_id": "02", "turn_revision": 1, "item_id": "hw-d-1"},
            {"kind": "item", "item_id": "hw-d-1", "task_id": "math-lesson-d", "revision": 1,
             "text": "答案为42。", "decision_id": "dec-d-1", "recorded_at": "2026-11-19T12:05:30Z"},
        ])
        self.workflow.ingest([{**turn_v1, "revision": 2, "text": "订正建议：答案为43。"}])
        bundle = self.workflow.trace_item("hw-d-1")
        # 回合正文入库时经 NFKC 规范化，全角冒号存为半角
        self.assertEqual(bundle["turn"]["text"], "原始建议:答案为42。")
        self.assertEqual(bundle["turn_current_revision"], 2)
        self.assertTrue(bundle["turn_superseded"])
        self.assertTrue(any("新修订" in reason for reason in bundle["needs_recheck"]))
        self.assertEqual([row["revision"] for row in self.workflow.record_history("lesson-d-turn-02")],
                         [1, 2])
        with self.assertRaises(ValueError):
            self.workflow.ingest([{**turn_v1, "text": "篡改：答案为7。"}])
        history = self.workflow.record_history("lesson-d-turn-02")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["text"], "原始建议:答案为42。")
        result = self.workflow.ingest([turn_v1])
        self.assertEqual(result, {"received": 1, "stored": 0})

    def test_review_distinguishes_model_suggestion_from_adopted_text(self):
        self.ingest_session()
        bundle = self.workflow.trace_item("hw-b-1")
        self.assertEqual(bundle["model_suggestion"], "按课后第2题把结尾改写为景物描写，不少于二百字。")
        self.assertEqual(bundle["adopted_text"], "提高层：按课后第2题把结尾改为景物描写，不少于一百五十字。")
        self.assertTrue(bundle["modified"])
        self.assertFalse(bundle["suggestion_matches_item"])
        adopted = self.workflow.trace_item("hw-b-2")
        self.assertFalse(adopted["modified"])
        self.assertTrue(adopted["suggestion_matches_item"])

    def test_conflicting_batch_is_rejected_atomically(self):
        original = {"record_id": "lesson-e-turn-01", "conversation_id": "lesson-e", "turn_id": "01",
                    "role": "user", "source": "school-synthetic", "revision": 1,
                    "observed_at": "2026-11-19T13:00:00Z", "text": "原始提问。", "task_id": "task-e"}
        self.workflow.ingest([original])
        newcomer = {"record_id": "lesson-e-turn-02", "conversation_id": "lesson-e", "turn_id": "02",
                    "role": "assistant", "source": "school-synthetic", "revision": 1,
                    "observed_at": "2026-11-19T13:01:00Z", "text": "回复。", "task_id": "task-e"}
        conflict = {**original, "text": "被改写的提问。"}
        with self.assertRaises(ValueError):
            self.workflow.ingest([newcomer, conflict])
        self.assertEqual([row["record_id"] for row in self.workflow.list_records()],
                         ["lesson-e-turn-01"])

    def test_ingest_accepts_sectioned_input(self):
        result = self.workflow.ingest({
            "turns": [{"record_id": "lesson-f-turn-01", "conversation_id": "lesson-f",
                       "turn_id": "01", "role": "user", "source": "school-synthetic", "revision": 1,
                       "observed_at": "2026-11-19T14:00:00Z", "text": "分节导入。", "task_id": "task-f"}],
            "confirmations": [{"confirmation_id": "conf-f-1", "task_id": "task-f",
                               "document": "doc", "fragment_id": "frag", "revision": 1,
                               "verdict": "flagged", "reviewer": "王老师",
                               "confirmed_at": "2026-11-19T14:05:00Z"}],
        })
        self.assertEqual(result, {"received": 2, "stored": 2})


if __name__ == "__main__":
    unittest.main()
