# Claim—Evidence 合同

允许类型：`fact`、`trend`、`assessment`、`requirement`、`assumption`、`to_confirm`。

每条正式 claim 必须引用 `analysis-model.json` 中存在的 evidence ID。`assessment` 和 `requirement` 至少引用一个已确认指标；带节能率、达标性或因果内容时还必须引用项目配置中的批准依据。没有证据的内容不能进入正文。

段落通过 `claim_ids` 关联 claim。表格和图表通过 `metric_ids` 关联标准化 observation，并追溯到 Excel 单元格。
