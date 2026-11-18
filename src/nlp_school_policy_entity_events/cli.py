import argparse
import json
import sys
from pathlib import Path

from .repository import RecordRepository
from .workflow import TextWorkflow


def main():
    parser = argparse.ArgumentParser(description="备课对话及教材依据记录工具")
    parser.add_argument("action", choices=("ingest", "list", "trace", "conversation", "history", "recheck"))
    parser.add_argument("target", nargs="?", default=None,
                        help="ingest 的导入文件路径，或要查询的课件条目、对话、记录编号")
    parser.add_argument("--state", default="var/records.json")
    parser.add_argument("--source", default=None)
    parser.add_argument("--conversation", dest="conversation_id", default=None)
    parser.add_argument("--revision", type=int, default=None)
    args = parser.parse_args()
    workflow = TextWorkflow(RecordRepository(args.state))
    try:
        if args.action == "ingest":
            path = args.target or "fixtures/records.json"
            result = workflow.ingest(json.loads(Path(path).read_text(encoding="utf-8")))
        elif args.action == "list":
            result = workflow.list_records(source=args.source, conversation_id=args.conversation_id)
        elif args.action == "trace":
            result = workflow.trace_item(_required(args, "课件条目编号"), revision=args.revision)
        elif args.action == "conversation":
            result = workflow.conversation_view(_required(args, "对话编号"))
        elif args.action == "history":
            result = workflow.record_history(_required(args, "记录编号"))
        else:
            result = workflow.recheck_report()
    except (ValueError, KeyError) as error:
        message = error.args[0] if error.args else str(error)
        print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _required(args, name):
    if not args.target:
        raise SystemExit(f"该操作需要提供{name}")
    return args.target


if __name__ == "__main__":
    main()
