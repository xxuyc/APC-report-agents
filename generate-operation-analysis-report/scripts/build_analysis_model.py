#!/usr/bin/env python3
import argparse
from common import read_json, write_json


TREND_METRICS = [
    ("daily_flow_10k_m3d", "日均处理量", "万 m³/d"),
    ("influent_bod5_mg_l", "进水 BOD5", "mg/L"),
    ("influent_ss_mg_l", "进水 SS", "mg/L"),
    ("influent_cod_mg_l", "进水 COD", "mg/L"),
    ("influent_tp_mg_l", "进水 TP", "mg/L"),
    ("influent_tn_mg_l", "进水 TN", "mg/L"),
    ("influent_nh3n_mg_l", "进水 NH3-N", "mg/L"),
]
MONTHLY_TABLE = [
    ("daily_flow_10k_m3d", "日均处理量（万 m³/d）", 2),
    ("influent_bod5_mg_l", "进水 BOD5（mg/L）", 1), ("effluent_bod5_mg_l", "出水 BOD5（mg/L）", 2),
    ("influent_ss_mg_l", "进水 SS（mg/L）", 1), ("effluent_ss_mg_l", "出水 SS（mg/L）", 2),
    ("influent_cod_mg_l", "进水 COD（mg/L）", 1), ("effluent_cod_mg_l", "出水 COD（mg/L）", 2),
    ("influent_tp_mg_l", "进水 TP（mg/L）", 2), ("effluent_tp_mg_l", "出水 TP（mg/L）", 3),
    ("influent_tn_mg_l", "进水 TN（mg/L）", 1), ("effluent_tn_mg_l", "出水 TN（mg/L）", 2),
    ("influent_nh3n_mg_l", "进水 NH3-N（mg/L）", 1), ("effluent_nh3n_mg_l", "出水 NH3-N（mg/L）", 3),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--chart-spec", required=True)
    args = parser.parse_args()
    data, metrics, profile = read_json(args.data), read_json(args.metrics), read_json(args.profile)
    preferences = profile.get("report_preferences", {})
    suggested = []
    flow = metrics.get("statistics", {}).get("daily_flow_10k_m3d")
    if flow:
        suggested.append({"claim_id": "CLM-FLOW-001", "type": "trend",
                          "text": f"日均处理量在{flow['max_period'][5:]}月达到年内高位 {flow['max']:.2f} 万 m³/d。",
                          "evidence": ["EV-STAT-daily_flow_10k_m3d"], "confidence": "confirmed"})
    for metric_id, label, unit in TREND_METRICS[1:]:
        item = metrics.get("statistics", {}).get(metric_id)
        if item:
            suggested.append({"claim_id": f"CLM-TREND-{metric_id}", "type": "trend",
                              "text": f"{label}年内范围为 {item['min']:.2f}—{item['max']:.2f} {unit}，峰值出现在{item['max_period'][5:]}月。",
                              "evidence": [f"EV-STAT-{metric_id}"], "confidence": "confirmed"})
    if metrics.get("removal_efficiency"):
        lowest = min(metrics["removal_efficiency"], key=lambda x: x["rate_pct"])
        suggested.append({"claim_id": "CLM-EFF-001", "type": "assessment",
                          "text": f"按年度质量平衡口径，{lowest['pollutant']}去除率为 {lowest['rate_pct']:.2f}%，在所分析指标中相对最低。",
                          "evidence": [lowest["evidence_id"]], "confidence": "confirmed"})
    if metrics.get("cost_items"):
        largest = max(metrics["cost_items"], key=lambda x: x["cost_cny"])
        suggested.append({"claim_id": "CLM-COST-001", "type": "assessment",
                          "text": f"在“{profile['cost_scope']['label']}”口径下，{largest['label']}占比最高，为 {largest['share_pct']:.2f}%。",
                          "evidence": [largest["evidence_id"], "EV-COST-CORE-TOTAL"], "confidence": "confirmed"})
    for item in metrics.get("comparisons", []):
        if item.get("change_pct") is None:
            continue
        direction = "增加" if item["change_pct"] >= 0 else "减少"
        suggested.append({"claim_id": f"CLM-YOY-{item['metric_id']}", "type": "trend",
                          "text": f"{item['label']}由2025年同期的 {item['value_2025']:,.2f} {item['unit']}变为2026年同期的 {item['value_2026']:,.2f} {item['unit']}，同比{direction}{abs(item['change_pct']):.2f}%。",
                          "evidence": [item["evidence_id"]], "confidence": "confirmed"})
    if metrics.get("plant_performance") and preferences.get("allow_cross_plant_comparison", False):
        p = metrics["plant_performance"]
        suggested.append({"claim_id":"CLM-PLANT-ENERGY", "type":"assessment",
                          "text":f"城东单位水量电耗为 {p['east_energy_intensity']:.3f} kWh/m³，高于城南的 {p['south_energy_intensity']:.3f} kWh/m³；城南处理量占比为 {p['south_flow_share_pct']:.1f}%，用电量占比为 {p['south_power_share_pct']:.1f}%。",
                          "evidence":["EV-PLANT-ENERGY"], "confidence":"confirmed"})
    requirements = []
    known_evidence = {x["evidence_id"] for x in metrics.get("evidence", [])}
    for index, item in enumerate(profile.get("approved_system_directions", []), 1):
        refs = [ref for ref in item.get("evidence", []) if ref in known_evidence]
        if refs and item.get("text"):
            requirements.append({"claim_id": item.get("claim_id", f"CLM-REQ-{index:03d}"),
                                 "type": "requirement", "system": item.get("system", ""),
                                 "text": item["text"], "evidence": refs, "confidence": "assessment"})
    monthly_rows = []
    configured_monthly = profile.get("monthly_table_metrics") or [
        {"metric_id": metric_id, "label": label, "decimals": decimals} for metric_id, label, decimals in MONTHLY_TABLE]
    for cfg in configured_monthly:
        metric_id, label, decimals = cfg["metric_id"], cfg["label"], int(cfg.get("decimals", 2))
        metric = data["metrics"].get(metric_id)
        if metric:
            monthly_rows.append({"metric_id": metric_id, "label": label, "decimals": decimals,
                                 "values": metric["values"]})
    sections = [
        {"section_id": "data_basis", "title": "数据来源、时间范围和质量说明"},
        {"section_id": "flow_quality", "title": "处理水量与进出水水质分析"},
        {"section_id": "efficiency", "title": "污染物处理效率分析"},
        {"section_id": "cost", "title": "能耗、药耗、污泥与生产成本分析"},
        {"section_id": "conclusions", "title": "主要数据结论"},
        {"section_id": "requirements", "title": "建设需求评估"},
        {"section_id": "limitations", "title": "关键输入提醒与分析边界"},
    ]
    model = {"schema_version": "0.1", "project": data["project"], "analysis_year": data["analysis_year"],
             "period_label": profile.get("period_label", f"{data['analysis_year']}年度"),
             "report_mode": profile.get("report_mode", "both"), "sections": sections,
             "monthly_table": {"periods": data["periods"], "rows": monthly_rows},
             "removal_table": metrics["removal_efficiency"], "cost_table": metrics["cost_items"],
             "core_cost_total_cny": metrics["core_cost_total_cny"],
             "recognized_cost_total_cny": metrics["recognized_cost_total_cny"],
             "cost_scope": metrics["cost_scope"], "resource_table": metrics.get("comparisons", []),
             "plant_performance": metrics.get("plant_performance"), "evidence": metrics["evidence"],
             "quality_issues": metrics["quality_issues"],
             "critical_inputs": [x for x in metrics["quality_issues"] if x.get("report_disposition") == "critical_input"],
             "review_only_issues": [x for x in metrics["quality_issues"] if x.get("report_disposition") != "critical_input"],
             "report_preferences": preferences,
             "data_provenance_opening": profile.get("data_provenance_opening", ""),
             "suggested_claims": suggested,
             "suggested_requirements": requirements}
    configured_trends = profile.get("trend_metrics") or [
        {"metric_id": mid, "title": title, "unit": unit} for mid, title, unit in TREND_METRICS]
    chart_spec = {"schema_version": "0.1", "periods": data["periods"],
                  "monthly_title": "月度处理量、负荷及资源消耗强度变化",
                  "charts": [
                      {"chart_id": "monthly-trends", "type": "small_multiples_line",
                       "axis_policy": preferences.get("chart_axis_policy", "zero_baseline"),
                       "series": [{"metric_id": item["metric_id"], "title": item["title"], "unit": item["unit"],
                                   "values": data["metrics"].get(item["metric_id"], {}).get("values", [])}
                                  for item in configured_trends if item["metric_id"] in data["metrics"]]},
                      {"chart_id": "cost-share", "type": "pie" if len(metrics["cost_items"]) <= 6 else "bar",
                       "scope": metrics["cost_scope"]["label"], "items": metrics["cost_items"]},
                      {"chart_id":"yoy-change", "type":"horizontal_bar", "items":metrics.get("comparisons", [])}
                  ]}
    write_json(args.output, model)
    write_json(args.chart_spec, chart_spec)


if __name__ == "__main__":
    main()
