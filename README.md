# 备课对话依据回溯台

备课对话依据回溯台保存从备课工具导出的对话回合与本地教材片段，供教师核验生成内容并在课后复盘。记录包含对话、回合、发言角色、上下文和来源教材修订号。样例数据为合成内容，不连接外部模型或校务系统。

## 环境

需要 Python 3.11 或更新版本。应用运行不依赖第三方包；运行测试和构建前，安装固定版本的开发工具：`python -m pip install -r requirements-dev.txt`。

## 运行

执行 `PYTHONPATH=src python -m nlp_school_policy_entity_events.cli ingest fixtures/records.json` 导入演练对话，再执行 `PYTHONPATH=src python -m nlp_school_policy_entity_events.cli list` 查看文本记录和基础词项统计。运行数据保存在 `var/records.json`。每条记录使用稳定的记录编号，并保留对话编号、回合编号、发言角色、前序回合、课程任务和教材版本信息。

## 测试

执行 `python -m pytest -q` 检查字段校验、回合元数据保留、文本规范化、较新记录处理和本地持久化。
