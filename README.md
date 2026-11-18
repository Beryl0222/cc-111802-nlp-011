# 备课对话依据回溯台

备课对话依据回溯台保存从备课工具导出的对话回合、模型候选、教材片段、教师决定与课件条目，供教师核验生成内容并在课后复盘。复盘时可以从课件中的具体内容回查到：它来自哪次提示的哪个候选、当时引用的教材片段原文、以及由谁在哪次决定中采纳或改成了现在样子。样例数据为合成内容，不连接外部模型或校务系统。

## 数据模型

导入文件是记录列表，每条记录用 `kind` 区分类型（缺省为 `turn`）；也可以按分节对象导入（`{"turns": [...], "decisions": [...]}`）。

- `turn` 对话回合：角色（user/assistant/teacher）、前序回合、课程任务、教材版本等元数据；同一 `record_id` 的多个修订全部保留。
- `candidate` 模型候选：一轮回复可含多个候选，教师可只采用其中一部分；`source_refs` 记录模型自称的依据。
- `fragment` 教材片段：按 `document + fragment_id + revision` 留档，旧修订永久保留，历史按当时内容还原。
- `decision` 教师决定：`adopt` / `modify` / `reject`，记录复核人、复核时的回合修订与教材依据；更正用新决定加 `supersedes`，旧决定不删除。
- `item` 课件条目：已采用的课件内容，按修订号留档，每条修订指向产生它的决定。
- `confirmation` 核验记录：按“教材片段 × 课程任务”生效；某任务下的确认不泛化到同一片段在其他任务中的引用。

## 留档保证

- 追加式保存：所有记录按键追加，相同内容重复导入幂等跳过，同键不同内容直接拒绝，补录不会抹掉已复核版本。
- 不补全缺失内容：断网或导入中断造成的缺回合只在查询时标记（`missing_turns`、`dangling_parents`），绝不伪造未收到的回复；补录到达后缺口自动消失。
- 需重新核对：教材片段或对话回合出现新修订时，当前课件的对应依据会被标出；历史回溯仍按当时修订还原。

## 环境

需要 Python 3.11 或更新版本。应用运行不依赖第三方包；运行测试和构建前，安装固定版本的开发工具：`python -m pip install -r requirements-dev.txt`。

## 运行

```bash
# 导入（可多次、可乱序补录；运行数据保存在 var/records.json）
PYTHONPATH=src python -m nlp_school_policy_entity_events.cli ingest fixtures/records.json
PYTHONPATH=src python -m nlp_school_policy_entity_events.cli ingest fixtures/review-session.json

# 当前对话回合列表（可用 --source、--conversation 过滤）
PYTHONPATH=src python -m nlp_school_policy_entity_events.cli list

# 从课件条目回查：决定、候选、回合、实际收到的上下文、教材依据与需重新核对项
PYTHONPATH=src python -m nlp_school_policy_entity_events.cli trace hw-b-1 [--revision 1]

# 对话完整性：缺回合与悬空引用只标记不补全，候选采纳状态一并列出
PYTHONPATH=src python -m nlp_school_policy_entity_events.cli conversation lesson-c

# 某条对话记录的全部修订
PYTHONPATH=src python -m nlp_school_policy_entity_events.cli history lesson-b-turn-02

# 当前课件中依据已过期或尚未核验的条目
PYTHONPATH=src python -m nlp_school_policy_entity_events.cli recheck
```

`trace` 输出中 `model_suggestion` 是模型候选原文，`adopted_text` 是教师最终采用进课件的文本，`modified` / `suggestion_matches_item` 区分原样采纳与修改后采用；`basis` 给出决定所依据教材片段的当时原文、当前修订号与按任务生效的核验状态。

## 测试

执行 `python -m pytest -q` 检查字段校验、回合元数据保留、文本规范化、追加式留档、候选部分采纳、按任务核验、历史还原与重核标记、缺口标记和本地持久化。
