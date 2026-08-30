# 飞书多项目知识中心

此模块为两个报告 Agent 提供同一套确定性项目路由、跨项目参考和运行写回能力。目标项目事实与历史参考严格分栏；LLM 只能提出检索意图，不能决定项目归属、数值可比性或披露权限。

## 第一版运行方式

本地 JSON 用于开发、迁移和无凭据回归：

```powershell
python -m knowledge_center.cli --store knowledge_center/examples/local-store.sample.json plan-retrieval `
  --project-id demo-current `
  --agent-type generate-operation-analysis-report `
  --query "参考同类项目的写法和药耗对标"
```

知识中心默认不由两个报告 Agent 自动启用。显式使用
`--knowledge-mode optional` 或 `--knowledge-mode required` 后，才会读取本地
`lark-cli` 配置并连接飞书 Base。

连接飞书 Base 时不传 `--knowledge-store`，并配置：

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_BASE_APP_TOKEN
FEISHU_TABLE_PROJECTS_ID
FEISHU_TABLE_SOURCES_ID
FEISHU_TABLE_KNOWLEDGE_ID
FEISHU_TABLE_METRICS_ID
FEISHU_TABLE_REQUIREMENTS_ID
FEISHU_TABLE_RUNS_ID
FEISHU_TABLE_CHANGES_ID
```

Base 中七张表及主键见 `base-schema.json`。中文字段名到代码字段的映射位于 `core.py` 的 `FIELD_MAP`。

## 检索边界

- `target_project_id` 唯一；无法唯一判断时返回 `project_confirmation_required`。
- 历史数值自动引用必须同时满足：相似度至少 70、关键元数据齐全、QA 通过、用途允许、`named_reference + named`。
- 结构化指标只读 Base，不进入语义向量检索。
- `search-documents` 当前采用元数据与关键词过滤。未来 Aily 只能接收路由器批准的资产/项目允许列表，并且返回片段仍需重新校验权限和来源。
- Git 中的执行规则、公式和模板始终高于远端知识，不允许远端条目覆盖 Harness 的确定性计算。

## Agent 接入参数

两个 `run_pipeline.py prepare` 均支持：

```text
--knowledge-store PATH
--retrieval-query TEXT
--knowledge-intent INTENT        # 可重复
--reference-project-id ID        # 可重复
--knowledge-mode MODE            # disabled（默认）/ optional / required
--disable-knowledge              # 旧命令兼容别名
```

每次准备阶段生成不可变的 `working/knowledge-snapshot.json`，并把模式、状态、
SHA-256 和参考项目写入 manifest。只有知识状态为 `enabled` 且 QA 通过后才写回；
`disabled` 和 `unavailable` 均不访问飞书。
