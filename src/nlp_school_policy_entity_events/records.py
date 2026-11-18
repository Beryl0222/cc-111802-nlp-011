from dataclasses import asdict, dataclass, field
from datetime import datetime

ROLES = {"user", "assistant", "teacher"}
ACTIONS = {"adopt", "modify", "reject"}
VERDICTS = {"confirmed", "flagged"}

SECTIONS = ("turns", "candidates", "fragments", "decisions", "items", "confirmations")
SECTION_KIND = {
    "turns": "turn",
    "candidates": "candidate",
    "fragments": "fragment",
    "decisions": "decision",
    "items": "item",
    "confirmations": "confirmation",
}
KIND_SECTION = {kind: section for section, kind in SECTION_KIND.items()}


def _text(value):
    return str(value) if value is not None else ""


def _stripped(value):
    return _text(value).strip()


def _integer(value, field_name, minimum=1):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}必须是整数") from None
    if number < minimum:
        raise ValueError(f"{field_name}不能小于{minimum}")
    return number


def _instant(value, field_name):
    text = _stripped(value)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field_name}的时间格式无效") from None
    return text


def _refs(value, field_name):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name}必须是列表")
    refs = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError(f"{field_name}的条目必须是对象")
        document = _stripped(entry.get("document"))
        fragment_id = _stripped(entry.get("fragment_id"))
        if not document or not fragment_id:
            raise ValueError(f"{field_name}的条目缺少教材或片段编号")
        refs.append({
            "document": document,
            "fragment_id": fragment_id,
            "revision": _integer(entry.get("revision", 0), f"{field_name}的教材修订号"),
        })
    return refs


@dataclass(frozen=True)
class TextRecord:
    record_id: str
    conversation_id: str
    turn_id: str
    role: str
    source: str
    revision: int
    observed_at: str
    text: str
    context: str = ""
    parent_turn_id: str = ""
    task_id: str = ""
    source_document: str = ""
    source_revision: int = 0

    @classmethod
    def from_dict(cls, value):
        record = cls(
            record_id=str(value.get("record_id", "")).strip(),
            conversation_id=str(value.get("conversation_id", "")).strip(),
            turn_id=str(value.get("turn_id", "")).strip(),
            role=str(value.get("role", "")).strip(),
            source=str(value.get("source", "")).strip(),
            revision=int(value.get("revision", 0)),
            observed_at=str(value.get("observed_at", "")).strip(),
            text=str(value.get("text", "")),
            context=str(value.get("context", "")).strip(),
            parent_turn_id=str(value.get("parent_turn_id", "")).strip(),
            task_id=str(value.get("task_id", "")).strip(),
            source_document=str(value.get("source_document", "")).strip(),
            source_revision=int(value.get("source_revision", 0)),
        )
        if (not record.record_id or not record.conversation_id or not record.turn_id
                or record.role not in ROLES
                or not record.source or record.revision < 1 or not record.text.strip()):
            raise ValueError("对话记录缺少身份、角色、来源、有效修订号或正文")
        if record.source_revision < 0:
            raise ValueError("教材修订号不能小于零")
        datetime.fromisoformat(record.observed_at.replace("Z", "+00:00"))
        return record

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class CandidateRecord:
    """一轮回复中的一个模型候选；教师可能只采用其中一部分。"""
    candidate_id: str
    conversation_id: str
    turn_id: str
    task_id: str
    label: str
    text: str
    source_refs: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, value):
        record = cls(
            candidate_id=_stripped(value.get("candidate_id")),
            conversation_id=_stripped(value.get("conversation_id")),
            turn_id=_stripped(value.get("turn_id")),
            task_id=_stripped(value.get("task_id")),
            label=_stripped(value.get("label")),
            text=_text(value.get("text")),
            source_refs=_refs(value.get("source_refs"), "候选来源依据"),
        )
        if (not record.candidate_id or not record.conversation_id or not record.turn_id
                or not record.task_id or not record.text.strip()):
            raise ValueError("模型候选缺少编号、所属回合、课程任务或正文")
        return record

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class FragmentRecord:
    """教材片段，按修订号留档；旧修订永久保留供历史还原。"""
    document: str
    fragment_id: str
    revision: int
    text: str
    observed_at: str = ""

    @classmethod
    def from_dict(cls, value):
        record = cls(
            document=_stripped(value.get("document")),
            fragment_id=_stripped(value.get("fragment_id")),
            revision=_integer(value.get("revision", 0), "教材修订号"),
            text=_text(value.get("text")),
            observed_at=_stripped(value.get("observed_at")),
        )
        if not record.document or not record.fragment_id or not record.text.strip():
            raise ValueError("教材片段缺少文档、片段编号或正文")
        if record.observed_at:
            _instant(record.observed_at, "教材片段接收时间")
        return record

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DecisionRecord:
    """教师对模型候选的采纳、修改或拒绝决定；追加留档，更正用新决定加 supersedes。"""
    decision_id: str
    task_id: str
    action: str
    reviewer: str
    decided_at: str
    candidate_id: str = ""
    turn_id: str = ""
    turn_revision: int = 0
    item_id: str = ""
    text: str = ""
    basis: list = field(default_factory=list)
    supersedes: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, value):
        record = cls(
            decision_id=_stripped(value.get("decision_id")),
            task_id=_stripped(value.get("task_id")),
            action=_stripped(value.get("action")),
            reviewer=_stripped(value.get("reviewer")),
            decided_at=_instant(value.get("decided_at"), "决定时间"),
            candidate_id=_stripped(value.get("candidate_id")),
            turn_id=_stripped(value.get("turn_id")),
            turn_revision=_integer(value.get("turn_revision", 0), "回合修订号", minimum=0),
            item_id=_stripped(value.get("item_id")),
            text=_text(value.get("text")),
            basis=_refs(value.get("basis"), "决定依据"),
            supersedes=_stripped(value.get("supersedes")),
            note=_text(value.get("note")),
        )
        if not record.decision_id or not record.task_id or not record.reviewer:
            raise ValueError("教师决定缺少编号、课程任务或复核人")
        if record.action not in ACTIONS:
            raise ValueError("教师决定的动作无效")
        if not record.candidate_id and not record.turn_id:
            raise ValueError("教师决定必须指向模型候选或对话回合")
        if record.action in {"adopt", "modify"} and not record.item_id:
            raise ValueError("采纳或修改决定必须给出课件条目编号")
        if record.action == "modify" and not record.text.strip():
            raise ValueError("修改决定必须给出修改后的文本")
        return record

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ItemRecord:
    """已采用进课件的内容条目，按修订号留档。"""
    item_id: str
    task_id: str
    revision: int
    text: str
    decision_id: str
    recorded_at: str

    @classmethod
    def from_dict(cls, value):
        record = cls(
            item_id=_stripped(value.get("item_id")),
            task_id=_stripped(value.get("task_id")),
            revision=_integer(value.get("revision", 0), "课件条目修订号"),
            text=_text(value.get("text")),
            decision_id=_stripped(value.get("decision_id")),
            recorded_at=_instant(value.get("recorded_at"), "课件记录时间"),
        )
        if not record.item_id or not record.task_id or not record.text.strip() or not record.decision_id:
            raise ValueError("课件条目缺少编号、课程任务、正文或决定编号")
        return record

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ConfirmationRecord:
    """教师对教材片段的核验；只在同一课程任务内生效，不泛化到其他任务。"""
    confirmation_id: str
    task_id: str
    document: str
    fragment_id: str
    revision: int
    verdict: str
    reviewer: str
    confirmed_at: str
    note: str = ""

    @classmethod
    def from_dict(cls, value):
        record = cls(
            confirmation_id=_stripped(value.get("confirmation_id")),
            task_id=_stripped(value.get("task_id")),
            document=_stripped(value.get("document")),
            fragment_id=_stripped(value.get("fragment_id")),
            revision=_integer(value.get("revision", 0), "核验的教材修订号"),
            verdict=_stripped(value.get("verdict")),
            reviewer=_stripped(value.get("reviewer")),
            confirmed_at=_instant(value.get("confirmed_at"), "核验时间"),
            note=_text(value.get("note")),
        )
        if (not record.confirmation_id or not record.task_id or not record.document
                or not record.fragment_id or not record.reviewer):
            raise ValueError("核验记录缺少编号、课程任务、教材片段或核验人")
        if record.verdict not in VERDICTS:
            raise ValueError("核验结论无效")
        return record

    def to_dict(self):
        return asdict(self)


ENTRY_KINDS = {
    "turn": TextRecord,
    "candidate": CandidateRecord,
    "fragment": FragmentRecord,
    "decision": DecisionRecord,
    "item": ItemRecord,
    "confirmation": ConfirmationRecord,
}


def parse_entry(value):
    if not isinstance(value, dict):
        raise ValueError("记录必须是对象")
    kind = _stripped(value.get("kind")) or "turn"
    record_class = ENTRY_KINDS.get(kind)
    if record_class is None:
        raise ValueError(f"未知记录类型: {kind}")
    return kind, record_class.from_dict(value)


def entry_key(kind, data):
    if kind == "turn":
        return (data["record_id"], data["revision"])
    if kind == "candidate":
        return data["candidate_id"]
    if kind == "fragment":
        return (data["document"], data["fragment_id"], data["revision"])
    if kind == "decision":
        return data["decision_id"]
    if kind == "item":
        return (data["item_id"], data["revision"])
    if kind == "confirmation":
        return data["confirmation_id"]
    raise ValueError(f"未知记录类型: {kind}")
