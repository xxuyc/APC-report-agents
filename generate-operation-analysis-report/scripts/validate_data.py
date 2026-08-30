#!/usr/bin/env python3
import argparse
import math
from common import read_json, write_json


CORE = ["total_flow_m3", "daily_flow_10k_m3d", "influent_cod_mg_l", "influent_tn_mg_l",
        "influent_tp_mg_l", "electricity_cost_cny"]
POLLUTANTS = ["ss", "bod5", "cod", "nh3n", "tn", "tp"]


def values(data, metric_id):
    return data.get("metrics", {}).get(metric_id, {}).get("values", [])


def annual_sum(data, metric_id):
    present = [v for v in values(data, metric_id) if v is not None]
    return sum(present) if present else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--inspection", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--golden-profile")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data, inspection, profile = read_json(args.data), read_json(args.inspection), read_json(args.profile)
    golden = read_json(args.golden_profile) if args.golden_profile else {}
    issues = list(data.get("predefined_quality_issues", []))
    for sheet in inspection.get("sheets", []):
        for error in sheet.get("formula_errors", []):
            issues.append({"severity": "error", "type": "formula_error", "message": "源表存在公式错误。",
                           "source": {"sheet": sheet["name"], "cell": error["cell"]}})
    if len(set(data.get("periods", []))) != len(data.get("periods", [])):
        issues.append({"severity": "error", "type": "duplicate_period", "message": "月份轴存在重复值。"})
    for metric_id in profile.get("core_metrics", CORE):
        missing = [data["periods"][i] for i, value in enumerate(values(data, metric_id)) if value is None]
        if missing:
            issues.append({"severity": "warning", "type": "missing_core_observations", "metric_id": metric_id,
                           "message": f"核心指标缺失月份：{', '.join(missing)}"})
    for metric_id, metric in data.get("metrics", {}).items():
        for period, value in zip(data["periods"], metric.get("values", [])):
            if value is not None and value < 0:
                issues.append({"severity": "error", "type": "negative_value", "metric_id": metric_id,
                               "period": period, "message": "指标出现不合理负值。"})
        if metric.get("aggregation") == "sum" and metric.get("annual_cached_total") is not None:
            recomputed = annual_sum(data, metric_id)
            cached = metric["annual_cached_total"]
            tolerance = max(0.01, abs(recomputed or 0) * 0.001)
            if recomputed is not None and abs(recomputed - cached) > tolerance:
                issues.append({"severity": "warning", "type": "annual_total_conflict", "metric_id": metric_id,
                               "recomputed": recomputed, "cached": cached,
                               "message": "月度重算合计与 Excel 年度缓存值不一致。"})
    for pollutant in POLLUTANTS:
        removed = annual_sum(data, f"{pollutant}_removed_kg")
        emitted = annual_sum(data, f"{pollutant}_emitted_kg")
        monthly_rate = data.get("metrics", {}).get(f"{pollutant}_removal_rate_pct", {}).get("annual_cached_average")
        if removed is not None and emitted is not None and removed + emitted > 0:
            mass_rate = 100 * removed / (removed + emitted)
            if monthly_rate is not None and abs(mass_rate - monthly_rate) > 0.1:
                issues.append({"severity": "warning", "type": "removal_rate_method_conflict",
                               "metric_id": pollutant, "mass_balance_rate": mass_rate,
                               "monthly_average_rate": monthly_rate,
                               "message": "质量平衡去除率与月去除率算术平均存在口径差异。"})
            reference_rate = golden.get("reference_report_rates", {}).get(pollutant)
            if reference_rate is not None and abs(mass_rate - float(reference_rate)) > 0.1:
                issues.append({"severity": "warning", "type": "reference_report_value_conflict",
                               "metric_id": pollutant, "mass_balance_rate": mass_rate,
                               "reference_report_rate": reference_rate,
                               "message": "暂定金标准报告中的去除率与重算结果不一致，不沿用原值。"})
    recognized_costs = profile.get("recognized_cost_metrics", [])
    included = set(profile.get("cost_scope", {}).get("included_metrics", []))
    excluded_value = sum(annual_sum(data, metric) or 0 for metric in recognized_costs if metric not in included)
    if excluded_value > 0:
        issues.append({"severity": "warning", "type": "cost_scope_exclusion", "excluded_cost": excluded_value,
                       "message": "存在未纳入核心成本口径的已识别费用，报告必须明确成本范围。"})
    if not profile.get("effluent_limits"):
        issues.append({"severity": "warning", "type": "missing_effluent_limits",
                       "message": "未提供适用排放限值，不评价达标性。"})
    critical_types = set(profile.get("critical_input_types", []))
    for issue in issues:
        issue["report_disposition"] = "critical_input" if issue.get("type") in critical_types else "review_workbook"
    counts = {"error": sum(i["severity"] == "error" for i in issues),
              "warning": sum(i["severity"] == "warning" for i in issues)}
    write_json(args.output, {"schema_version": "0.1", "valid": counts["error"] == 0,
                             "counts": counts, "issues": issues})
    if counts["error"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
