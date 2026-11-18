from dataclasses import dataclass, asdict
from datetime import datetime


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
                or record.role not in {"user", "assistant", "teacher"}
                or not record.source or record.revision < 1 or not record.text.strip()):
            raise ValueError("对话记录缺少身份、角色、来源、有效修订号或正文")
        if record.source_revision < 0:
            raise ValueError("教材修订号不能小于零")
        datetime.fromisoformat(record.observed_at.replace("Z", "+00:00"))
        return record

    def to_dict(self):
        return asdict(self)
