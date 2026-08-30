---
name: generate-operation-analysis-report
description: Generate a traceable Chinese wastewater-plant production-operation data analysis DOCX and review workbooks from monthly or annual Excel data. Use for 生产运营数据分析、进出水水质趋势、处理效率、能耗药耗成本、运营现状评估或建设需求评估. Recompute metrics deterministically, flag conflicting definitions, and never infer compliance, causality, or savings without supporting evidence.
---

# 生产运营数据分析报告

将甲方原始运营 Excel 转为可追溯的运营现状分析和建设需求评估。原始文件只做快照，不修改。

## 固定流程

1. 使用仓库根目录 `.venv` 中的 Python 执行 `scripts/run_pipeline.py prepare`，建立运行目录、资料索引、工作簿结构、标准化数据、数据质量结果、指标模型和图表。
2. 状态为 `validation_failed` 时停止；状态为 `ready_to_draft` 时读取 `working/agent-request.md` 中列出的结构化文件。
3. Agent 只从 `analysis-model.json`、`chart-spec.json`、项目配置和本 Skill 的规则起草 `drafted-content.json`，不得重新计算、直接引用原始 Excel 或补写缺失参数。
4. 起草前读取项目配置中的 `report_preferences` 与 `approved_system_directions`。默认不做厂际比较；未确认内容不得混入普通正文；建设需求必须落到经项目批准的系统方向，不能退化成“继续补数据”。
5. 使用 `finalize` 校验 claim—evidence 链，生成独立报告、方案章节、分析工作簿、关键输入提醒和追溯表。
6. 使用 Word 和表格渲染逐页/逐表检查，再调用 `record-qa` 登记结果。

没有 Office 或文档渲染器时仍应完成 DOCX、XLSX 和图表生成，把视觉 QA 保持为待检查；不得因缺少 Office 阻断确定性流水线。

## 知识中心模式

- 默认 `--knowledge-mode disabled`，只运行本地分析，不读取飞书配置或执行远端写回。
- `optional` 在知识中心不可用时降级为本地分析并记录警告。
- `required` 要求检索和 QA 后写回均成功，否则停止。
- `--disable-knowledge` 仅作为旧命令兼容别名。

## 不可突破的边界

- Excel 公式缓存仅作对照；正式指标由 Harness 重算。
- 不同计算口径分别命名，冲突不得静默覆盖。
- 只有月均数据时，不得宣称全年持续达标；没有标准时不得评价达标性。
- 一年数据只描述年内阶段性变化，不证明长期季节规律。
- 相关性不是因果关系。
- 节能率、药耗降低率和设备配置数量必须有批准依据，否则只写方向性需求。
- 成本结论必须注明纳入范围。
- 正式正文只陈述已确认事实和有证据的受控判断。关键缺失输入使用统一提示框，并进入《待确认事项.xlsx》；普通缺口留在工作簿，不在正文反复解释。
- 缺少价格、费用或其他决定成本核算完整性的字段时，标记为“关键输入”，不得仅作为一般限制一笔带过。
- 厂际比较默认关闭，只有用户明确提出或项目配置批准时才生成比较结论。
- 绝对量和比例趋势图默认采用零基线，避免通过过窄纵轴夸大波动；例外必须由项目配置明确批准。

## 资源路由

- 指标含义和单位：`references/metric-dictionary.md`
- 计算及质量闸门：`references/calculation-rules.md`
- Agent 行文规则：`references/analysis-writing-rules.md`
- 人工审核意见的分层与迁移：`references/reviewer-feedback-rules.md`
- 结论追溯合同：`references/claim-evidence-policy.md`
- 报告章节和图表：`references/report-structure.md`
- 东阳年度表适配器：`adapters/dongyang-annual-v1.yaml`

## 迭代

每组“原始数据＋人工审核报告”放入 `operation-analysis-workspace/golden-cases/<case-id>/`。先将意见分为通用质量规则、项目级参数、模板级样式和流程缺陷；项目参数不得迁移，至少两个项目验证后的分析方法才能提升为通用规则。每次迭代必须增加或更新回归断言。
