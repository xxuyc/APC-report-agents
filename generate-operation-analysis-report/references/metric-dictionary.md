# 指标字典

- 水量：`total_flow_m3` 为月处理总量，`daily_flow_10k_m3d` 为日均处理量。
- 水质：统一使用 `influent/effluent_<pollutant>_mg_l`，污染物包括 BOD5、SS、COD、TP、TN、NH3-N。
- 负荷：`<pollutant>_removed_kg` 和 `<pollutant>_emitted_kg` 为周期质量。
- 能耗：`electricity_kwh` 为电量，`energy_intensity_kwh_m3` 为单位水量电耗。
- 药剂：PAC、PAM、乙酸钠和次氯酸钠的用量与费用必须分开记录。
- 污泥：泥饼、绝干泥、含水率、产泥率和处置费不得混用。
- 金额统一为 CNY；百分数在 JSON 中保留 0—100 数值，不存储为小数比例。

每项 observation 必须保存原文件、工作表和单元格位置。
