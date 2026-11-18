from dataclasses import asdict

from .records import (
    ENTRY_KINDS,
    KIND_SECTION,
    SECTIONS,
    SECTION_KIND,
    entry_key,
    parse_entry,
)
from .text import annotate, normalize_text

ADOPTION_LABELS = {"adopt": "adopted", "modify": "modified", "reject": "rejected"}


def _turn_sort_key(turn_id):
    if turn_id.isdigit():
        return (0, int(turn_id), "")
    return (1, 0, turn_id)


class TextWorkflow:
    """对话、教材与课件的追加式留档，以及从课件条目回到来源依据的回溯。"""

    def __init__(self, repository):
        self.repository = repository

    # ---- 导入 ----

    def ingest(self, values):
        entries = self._entries(values)
        staged = []
        for value in entries:
            kind, record = parse_entry(value)
            data = record.to_dict()
            if kind == "turn":
                data["text"] = normalize_text(data["text"])
                data["analysis"] = annotate(data)
            staged.append((kind, data))
        store = self.repository.load()
        indexes = {section: {} for section in SECTIONS}
        for section in SECTIONS:
            kind = SECTION_KIND[section]
            for row in store[section]:
                indexes[section][entry_key(kind, row)] = row
        appended = 0
        for kind, data in staged:
            section = KIND_SECTION[kind]
            key = entry_key(kind, data)
            existing = indexes[section].get(key)
            if existing is not None:
                if self._same_record(kind, existing, data):
                    continue
                raise ValueError(f"记录{key}与已保存内容冲突，拒绝覆盖留档")
            indexes[section][key] = data
            store[section].append(data)
            appended += 1
        self.repository.save(store)
        return {"received": len(staged), "stored": appended}

    @staticmethod
    def _entries(values):
        if isinstance(values, dict):
            entries = []
            for section in SECTIONS:
                chunk = values.get(section, [])
                if not isinstance(chunk, list):
                    raise TypeError("导入内容的分节必须是列表")
                kind = SECTION_KIND[section]
                for row in chunk:
                    if not isinstance(row, dict):
                        raise ValueError("记录必须是对象")
                    entries.append({**row, "kind": kind})
            return entries
        if isinstance(values, list):
            return list(values)
        raise TypeError("导入内容必须是记录列表")

    @staticmethod
    def _same_record(kind, stored, incoming):
        record_class = ENTRY_KINDS[kind]
        return record_class.from_dict(stored).to_dict() == record_class.from_dict(incoming).to_dict()

    def _parsed(self):
        store = self.repository.load()
        return {
            SECTION_KIND[section]: [ENTRY_KINDS[SECTION_KIND[section]].from_dict(row) for row in rows]
            for section, rows in store.items()
        }

    # ---- 查询 ----

    def list_records(self, source=None, conversation_id=None):
        rows = self.repository.load()["turns"]
        latest = {}
        for row in rows:
            key = row["record_id"]
            if key not in latest or row["revision"] > latest[key]["revision"]:
                latest[key] = row
        records = list(latest.values())
        if source:
            records = [record for record in records if record["source"] == source]
        if conversation_id:
            records = [record for record in records if record["conversation_id"] == conversation_id]
        records.sort(key=lambda row: (row["conversation_id"], row["observed_at"], row["turn_id"]))
        return records

    def record_history(self, record_id):
        rows = [row for row in self.repository.load()["turns"] if row["record_id"] == record_id]
        rows.sort(key=lambda row: row["revision"])
        return rows

    def conversation_view(self, conversation_id):
        parsed = self._parsed()
        by_record = {}
        for turn in parsed["turn"]:
            by_record.setdefault(turn.record_id, []).append(turn)
        current = [max(versions, key=lambda turn: turn.revision) for versions in by_record.values()]
        current = [turn for turn in current if turn.conversation_id == conversation_id]
        current.sort(key=lambda turn: _turn_sort_key(turn.turn_id))
        version_counts = {turn.record_id: len(by_record[turn.record_id]) for turn in current}
        ids = {turn.turn_id for turn in current}
        missing = []
        if current and all(turn.turn_id.isdigit() for turn in current):
            width = max(len(turn.turn_id) for turn in current)
            have = {int(turn.turn_id) for turn in current}
            missing = [str(number).zfill(width)
                       for number in range(min(have), max(have) + 1) if number not in have]
        dangling = sorted({turn.parent_turn_id for turn in current
                           if turn.parent_turn_id and turn.parent_turn_id not in ids})
        candidates_by_turn = {}
        for candidate in parsed["candidate"]:
            candidates_by_turn.setdefault(candidate.turn_id, []).append(candidate)
        turns = []
        for turn in current:
            turns.append({
                "turn_id": turn.turn_id,
                "record_id": turn.record_id,
                "role": turn.role,
                "revision": turn.revision,
                "versions": version_counts[turn.record_id],
                "observed_at": turn.observed_at,
                "parent_turn_id": turn.parent_turn_id,
                "task_id": turn.task_id,
                "text": turn.text,
                "candidates": [
                    {
                        "candidate_id": candidate.candidate_id,
                        "label": candidate.label,
                        "text": candidate.text,
                        "adoption": self._adoption(parsed["decision"], candidate.candidate_id),
                    }
                    for candidate in sorted(candidates_by_turn.get(turn.turn_id, []),
                                            key=lambda entry: entry.candidate_id)
                ],
            })
        return {
            "conversation_id": conversation_id,
            "received_turns": len(turns),
            "complete": bool(turns) and not missing and not dangling,
            "missing_turns": missing,
            "dangling_parents": dangling,
            "turns": turns,
        }

    @staticmethod
    def _adoption(decisions, candidate_id):
        related = [decision for decision in decisions if decision.candidate_id == candidate_id]
        if not related:
            return {"status": "undecided", "decision_id": None, "item_id": None}
        latest = max(related, key=lambda decision: (decision.decided_at, decision.decision_id))
        return {
            "status": ADOPTION_LABELS[latest.action],
            "decision_id": latest.decision_id,
            "item_id": latest.item_id or None,
        }

    def trace_item(self, item_id, revision=None):
        parsed = self._parsed()
        items = [item for item in parsed["item"] if item.item_id == item_id]
        if not items:
            raise KeyError(f"未找到课件条目: {item_id}")
        if revision is None:
            item = max(items, key=lambda entry: entry.revision)
        else:
            match = [entry for entry in items if entry.revision == revision]
            if not match:
                raise KeyError(f"课件条目{item_id}没有修订{revision}")
            item = match[0]
        decisions = parsed["decision"]
        decision = next((entry for entry in decisions if entry.decision_id == item.decision_id), None)
        chain = sorted((entry for entry in decisions if entry.item_id == item_id),
                       key=lambda entry: (entry.decided_at, entry.decision_id))
        candidate = None
        if decision and decision.candidate_id:
            candidate = next((entry for entry in parsed["candidate"]
                              if entry.candidate_id == decision.candidate_id), None)
        conversation_id = candidate.conversation_id if candidate else ""
        turn_id = decision.turn_id if decision else ""
        wanted_revision = decision.turn_revision if decision else 0
        if not turn_id and candidate:
            turn_id = candidate.turn_id
        turn = None
        turn_current_revision = None
        turn_superseded = False
        if turn_id:
            pool = parsed["turn"]
            if conversation_id:
                pool = [entry for entry in pool if entry.conversation_id == conversation_id]
            elif decision:
                scoped = [entry for entry in pool if entry.task_id == decision.task_id]
                pool = scoped or pool
            matches = [entry for entry in pool if entry.turn_id == turn_id]
            if matches:
                turn_current_revision = max(entry.revision for entry in matches)
                target = wanted_revision if wanted_revision >= 1 else turn_current_revision
                turn = next((entry for entry in matches if entry.revision == target), None)
                turn_superseded = wanted_revision >= 1 and turn_current_revision > wanted_revision
            if not conversation_id and turn:
                conversation_id = turn.conversation_id
        needs = []
        if decision is None:
            needs.append(f"产生该课件的教师决定{item.decision_id}缺失")
        if decision and decision.candidate_id and candidate is None:
            needs.append(f"决定指向的模型候选{decision.candidate_id}未收到")
        if turn_id and turn is None:
            detail = f"修订{wanted_revision}" if wanted_revision >= 1 else "内容"
            needs.append(f"决定指向的对话回合{turn_id}的{detail}未收到")
        if turn_superseded:
            needs.append(f"对话回合{turn_id}已有新修订r{turn_current_revision}"
                         f"（决定复核时为r{wanted_revision}），需重新核对")
        basis = []
        if decision:
            for ref in decision.basis:
                basis.append(self._basis_entry(parsed, decision.task_id, ref, needs))
        model_refs = []
        if candidate:
            for ref in candidate.source_refs:
                model_refs.append(self._ref_availability(parsed, ref))
        model_suggestion = candidate.text if candidate else (turn.text if turn else None)
        conversation = self.conversation_view(conversation_id) if conversation_id else None
        return {
            "item": asdict(item),
            "item_revisions": [
                {"revision": entry.revision, "decision_id": entry.decision_id,
                 "recorded_at": entry.recorded_at}
                for entry in sorted(items, key=lambda entry: entry.revision)
            ],
            "decision": asdict(decision) if decision else None,
            "decision_chain": [asdict(entry) for entry in chain],
            "candidate": asdict(candidate) if candidate else None,
            "turn": asdict(turn) if turn else None,
            "turn_current_revision": turn_current_revision,
            "turn_superseded": turn_superseded,
            "model_suggestion": model_suggestion,
            "adopted_text": item.text,
            "modified": (decision.action == "modify") if decision else None,
            "suggestion_matches_item": (model_suggestion == item.text)
                                       if model_suggestion is not None else None,
            "model_source_refs": model_refs,
            "conversation": conversation,
            "basis": basis,
            "needs_recheck": needs,
        }

    def _basis_entry(self, parsed, task_id, ref, needs):
        document = ref["document"]
        fragment_id = ref["fragment_id"]
        label = f"{document}#{fragment_id}"
        fragments = [entry for entry in parsed["fragment"]
                     if entry.document == document and entry.fragment_id == fragment_id]
        current_revision = max((entry.revision for entry in fragments), default=0)
        at_revision = next((entry for entry in fragments if entry.revision == ref["revision"]), None)
        if at_revision is None:
            needs.append(f"依据{label}的第{ref['revision']}修订教材片段未收到")
        stale = bool(current_revision) and current_revision > ref["revision"]
        if stale:
            needs.append(f"依据{label}已更新到r{current_revision}"
                         f"（决定依据r{ref['revision']}），需重新核对")
        confirmations = [entry for entry in parsed["confirmation"]
                         if entry.document == document and entry.fragment_id == fragment_id
                         and entry.task_id == task_id]
        latest = max(confirmations, key=lambda entry: (entry.confirmed_at, entry.confirmation_id),
                     default=None)
        if latest is None:
            state = "unconfirmed"
            needs.append(f"依据{label}在任务{task_id}中尚未核验")
        elif latest.verdict == "flagged":
            state = "flagged"
            needs.append(f"依据{label}被{latest.reviewer}标记存疑，需重新核对")
        elif latest.revision < current_revision:
            state = "outdated"
            needs.append(f"依据{label}的核验停留在r{latest.revision}"
                         f"（教材已到r{current_revision}），需重新核验")
        else:
            state = "confirmed"
        other_tasks = sorted({entry.task_id for entry in parsed["confirmation"]
                              if entry.document == document and entry.fragment_id == fragment_id
                              and entry.task_id != task_id})
        return {
            "document": document,
            "fragment_id": fragment_id,
            "revision": ref["revision"],
            "fragment_text": at_revision.text if at_revision else None,
            "fragment_available": at_revision is not None,
            "current_revision": current_revision,
            "stale": stale,
            "confirmation": asdict(latest) if latest else None,
            "confirmation_state": state,
            "confirmation_scope": task_id,
            "other_task_confirmations": other_tasks,
        }

    @staticmethod
    def _ref_availability(parsed, ref):
        fragments = [entry for entry in parsed["fragment"]
                     if entry.document == ref["document"] and entry.fragment_id == ref["fragment_id"]]
        current_revision = max((entry.revision for entry in fragments), default=0)
        return {
            "document": ref["document"],
            "fragment_id": ref["fragment_id"],
            "revision": ref["revision"],
            "fragment_available": any(entry.revision == ref["revision"] for entry in fragments),
            "current_revision": current_revision,
        }

    def recheck_report(self):
        parsed = self._parsed()
        current = {}
        for item in parsed["item"]:
            if item.item_id not in current or item.revision > current[item.item_id].revision:
                current[item.item_id] = item
        flagged = []
        for item in sorted(current.values(), key=lambda entry: entry.item_id):
            bundle = self.trace_item(item.item_id)
            if bundle["needs_recheck"]:
                flagged.append({
                    "item_id": item.item_id,
                    "task_id": item.task_id,
                    "revision": item.revision,
                    "needs_recheck": bundle["needs_recheck"],
                })
        return {"item_count": len(current), "items": flagged}
