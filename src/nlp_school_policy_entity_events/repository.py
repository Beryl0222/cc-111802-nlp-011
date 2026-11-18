import json
from pathlib import Path

from .records import SECTIONS


class RecordRepository:
    """本地 JSON 留档库；写入先落临时文件再原子替换，导入中断不会留下半个文件。"""

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._empty()
        if not isinstance(value, dict):
            raise ValueError("记录库格式无效")
        store = self._empty()
        if any(section in value for section in SECTIONS):
            for section in SECTIONS:
                rows = value.get(section, [])
                if not isinstance(rows, list):
                    raise ValueError("记录库格式无效")
                store[section] = rows
            return store
        legacy = value.get("records")
        if isinstance(legacy, list):
            store["turns"] = legacy
            return store
        raise ValueError("记录库格式无效")

    def save(self, store):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 2}
        for section in SECTIONS:
            payload[section] = store.get(section, [])
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def read(self):
        return self.load()["turns"]

    def replace(self, records):
        store = self.load()
        store["turns"] = records
        self.save(store)

    @staticmethod
    def _empty():
        return {section: [] for section in SECTIONS}
