# drafted-content.json 合同（V0.2）

Agent 只读取 `source-index.json`、`facts.json`、`chapter-model.json`、写作规则和术语表。正文必须通过 `claim_ids` 关联结论，每个结论必须通过 `fact_id` 或 `source_id` 追溯。

```json
{
  "schema_version": "0.2",
  "title": "XX污水处理厂现场调研现状评估",
  "chapters": [
    {
      "chapter_id": "3.3",
      "title": "3.3 自控与数据基础",
      "status": "completed",
      "paragraphs": [{
        "paragraph_id": "P-3.3-001",
        "text": "厂区现有多套PLC控制系统和上位监控平台，系统间尚未完全互联。",
        "claim_ids": ["C-3.3-001"]
      }],
      "claims": [{
        "claim_id": "C-3.3-001",
        "text": "厂区自控系统整体集成度不足。",
        "kind": "assessment",
        "sources": [{"fact_id": "F-0023"}]
      }],
      "to_confirm": [{"item": "补充PLC与SCADA接口清单。", "source": {"fact_id": "F-0024"}}]
    }
  ]
}
```

约束：

- 章节必须与 `chapter-model.json` 完全一致，不自行增加不适用章节。
- `target_requirement` 不得作为现状事实；当章节模型的 `requirements` 提供了已确认建设要求时，可以生成 `kind: requirement` 的 claim，并明确使用“拟、建议、后续、计划”等措辞。
- 正文不使用“调研表显示”“现场填写信息表明”等来源前缀。
- 待确认事项不作为正文确定事实。
- 项目存在 `golden_profile` 时，章节编号和章节集合必须服从该项目的人工批准配置。
