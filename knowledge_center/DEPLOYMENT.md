# 飞书多项目知识中心：部署、迭代与治理

## 1. 上线顺序

1. 在飞书 Base 按 `base-fields.md` 创建七张表，并将表 ID 配置到运行服务。
2. 导入项目台账，优先补齐工艺、规模档位、排放标准、时间粒度、公式版本、设备边界和地域。缺少任一关键元数据的项目不能自动参与数值对标。
3. 导入资料索引和知识条目。历史文件默认设为 `internal_reference/internal_only`，完成披露审批后再改为 `named_reference/named`。
4. 用 `sync` 拉取一次七表快照，核对字段映射和中文字段名。
5. 先以 `--knowledge-store` 本地影子库跑双 Agent 回归，再移除该参数切换飞书 Base。
6. 服务环境可安装 `lark-oapi` 并运行 `listen` 接收 Base 变更事件；不安装不影响批处理检索。

## 2. 环境变量

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
FEISHU_KNOWLEDGE_CACHE
```

飞书连接异常时，只允许使用 24 小时以内的缓存；缓存缺失或过期会返回 `knowledge_unavailable`，不静默退化为无知识运行。

## 3. 日常命令

```powershell
# 识别目标项目；无法唯一识别时返回 project_confirmation_required
python -m knowledge_center.cli resolve-project --input .\input.xlsx

# 生成确定性 RetrievalPlan
python -m knowledge_center.cli plan-retrieval `
  --project-id current-project `
  --agent-type generate-operation-analysis-report `
  --query "参考同类项目写法并比较药耗"

# 生成不可变知识快照
python -m knowledge_center.cli build-knowledge-snapshot `
  --project-id current-project `
  --agent-type generate-operation-analysis-report `
  --reference-project-id history-project `
  --output .\knowledge-snapshot.json

# 拉取七表备份
python -m knowledge_center.cli sync --output .\feishu-base-snapshot.json

# 可选：监听 Base 变更事件
python -m knowledge_center.cli listen
```

## 4. 两个 Agent 的运行合同

`prepare` 新增可选参数：

```text
--project-name
--knowledge-store PATH
--retrieval-query TEXT
--knowledge-intent INTENT          可重复
--reference-project-id ID          可重复
--knowledge-mode MODE              disabled（默认）/ optional / required
--disable-knowledge                旧命令兼容别名
```

每次运行都会生成 `working/knowledge-snapshot.json`，manifest 保存检索意图、参考项目列表和快照 SHA-256。

- 调研 Agent：批准的历史案例和指标被登记到 `chapter-model.json.reference_sources`；草稿只能引用这些已登记的 `source_id`。写法和方法不能充当事实来源。
- 运营 Agent：批准的历史案例和指标被登记到 `analysis-model.json.evidence`；草稿校验器只接受已登记 evidence。当前项目指标仍由 Harness 重算。
- 两者都不把历史数据合并进当前项目统计结果。

## 5. 知识生命周期

```text
原始资料/运行产物
→ 自动登记（internal_reference 或 pending_review）
→ 业务审核来源与内容
→ 数据负责人审核公式、单位和边界
→ 披露负责人审批是否允许实名
→ named_reference + named + allowed_usages
→ 可进入下一次跨项目检索
→ 变更时写入“知识变更”并执行回归
```

建议角色：

- 项目负责人：项目归属、项目别名、当前事实确认。
- 数据负责人：指标定义、公式版本、单位换算和 QA。
- 内容负责人：批准写法、分析方法和案例表述。
- 披露负责人：实名复用范围。
- Agent 维护者：规则、Harness、回归测试和版本发布。

## 6. 迭代规则

- 单项目审核结果先形成项目级知识，不自动升级为通用规则。
- 写作偏好可在内容负责人批准后复用；项目参数永不随写法迁移。
- 分析方法至少经过跨项目回归后再标为通用方法；执行公式仍以 Git 中 Harness 为准。
- 运营指标只有运行完成、QA 通过后才写回；写回初始状态为内部参考，必须再次审批才能用于跨项目数值比较。
- 调研事实写回初始状态为 `pending_review`，审核前不参与正式引用。
- 每次知识变更记录前后版本、审批、影响范围和回归结果；旧条目标记替代关系，不直接覆盖历史记录。

## 7. Aily 接入

`semantic.py` 已提供项目/资产双白名单结果校验。接入 Aily 时必须：

1. 先运行 ProjectResolver 和 ReferenceRouter。
2. 仅把批准项目对应的资产 ID 传给 Aily。
3. 对返回片段再次执行项目、资产、用途、复用状态和披露方式校验。
4. 禁止把 `structured_metric` 放入语义搜索；指标始终从 Base 的“项目指标事实”表读取。

## 8. 验收命令

```powershell
python -m unittest discover -s knowledge_center/tests -v
python generate-operation-analysis-report/tests/smoke_test_pipeline.py
python generate-survey-report/tests/smoke_test_pipeline.py
```

两个 smoke test 只需要根目录 `requirements.txt` 中的公开 Python 依赖，不需要
Node.js、Microsoft Office 或 Codex 内置包。
