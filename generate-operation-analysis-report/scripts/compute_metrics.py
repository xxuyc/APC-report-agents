#!/usr/bin/env python3
import argparse
import math
import statistics
from common import read_json, write_json


POLLUTANTS = [("ss", "SS"), ("bod5", "BOD5"), ("cod", "COD"),
              ("nh3n", "NH3-N"), ("tn", "TN"), ("tp", "TP")]


def series(data, metric_id):
    metric = data.get("metrics", {}).get(metric_id, {})
    return [(period, value) for period, value in zip(data.get("periods", []), metric.get("values", [])) if value is not None]


def total(data, metric_id):
    items = series(data, metric_id)
    return sum(value for _, value in items) if items else None


def stat(data, metric_id):
    items = series(data, metric_id)
    if not items:
        return None
    vals = [v for _, v in items]
    mean = statistics.fmean(vals)
    return {"metric_id": metric_id, "count": len(vals), "mean": mean,
            "min": min(vals), "min_period": items[vals.index(min(vals))][0],
            "max": max(vals), "max_period": items[vals.index(max(vals))][0],
            "cv": statistics.pstdev(vals) / mean if mean else None,
            "first_half_mean": statistics.fmean(vals[:6]) if len(vals) >= 6 else None,
            "second_half_mean": statistics.fmean(vals[6:12]) if len(vals) >= 12 else None}


def evidence(evidence_id, kind, value, unit, sources, calculation):
    return {"evidence_id": evidence_id, "kind": kind, "value": value, "unit": unit,
            "sources": sources, "calculation": calculation, "confirmation": "confirmed"}


def observation_sources(data, metric_id):
    return [item["source"] | {"observation_id": item["observation_id"]}
            for item in data.get("observations", []) if item["metric_id"] == metric_id and item["value"] is not None]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data, profile, validation = read_json(args.data), read_json(args.profile), read_json(args.validation)
    stats, evidence_items = {}, []
    for metric_id in data.get("metrics", {}):
        value = stat(data, metric_id)
        if value:
            stats[metric_id] = value
            evidence_items.append(evidence(f"EV-STAT-{metric_id}", "descriptive_statistics", value,
                                           data["metrics"][metric_id]["unit"], observation_sources(data, metric_id),
                                           "min/max/mean/CV computed from available monthly observations"))
    flow_total = total(data, "total_flow_m3")
    evidence_items.append(evidence("EV-FLOW-ANNUAL", "annual_total", flow_total, "m3",
                                   observation_sources(data, "total_flow_m3"), "sum(monthly total flow)"))
    if profile.get("analysis_mode") == "two_plant_halfyear_resource":
        evidence_items.append(evidence("EV-DATA-SCOPE", "data_availability",
                                       {"water_quality_available": False, "cost_amount_available": False,
                                        "pump_selection_inputs_available": False}, "boolean",
                                       [], "workbook structure and configured project scope review"))
    comparison_results = []
    for item in data.get("comparisons", []):
        old, new = item.get("value_2025"), item.get("value_2026")
        change = (new / old - 1) * 100 if old not in (None, 0) and new is not None else None
        result = {**item, "change_pct": change, "evidence_id": f"EV-YOY-{item['metric_id']}"}
        comparison_results.append(result)
        evidence_items.append(evidence(result["evidence_id"], "year_over_year_comparison",
                                       {"value_2025": old, "value_2026": new, "change_pct": change}, item["unit"],
                                       item.get("sources", []), "2026H1/2025H1-1"))
    south_flow, east_flow = total(data, "south_flow_m3"), total(data, "east_flow_m3")
    south_power, east_power = total(data, "south_electricity_kwh"), total(data, "east_electricity_kwh")
    plant_performance = None
    if all(x is not None and x > 0 for x in (south_flow, east_flow, south_power, east_power)):
        plant_performance = {
            "south_flow_m3": south_flow, "east_flow_m3": east_flow,
            "south_power_kwh": south_power, "east_power_kwh": east_power,
            "south_energy_intensity": south_power / south_flow,
            "east_energy_intensity": east_power / east_flow,
            "south_flow_share_pct": 100 * south_flow / (south_flow + east_flow),
            "south_power_share_pct": 100 * south_power / (south_power + east_power),
        }
        evidence_items.append(evidence("EV-PLANT-ENERGY", "plant_comparison", plant_performance, "mixed",
                                       observation_sources(data, "south_flow_m3") + observation_sources(data, "east_flow_m3") +
                                       observation_sources(data, "south_electricity_kwh") + observation_sources(data, "east_electricity_kwh"),
                                       "plant totals, shares and kWh/m3 recomputed from monthly observations"))
    removal = []
    for key, label in POLLUTANTS:
        removed, emitted = total(data, f"{key}_removed_kg"), total(data, f"{key}_emitted_kg")
        if removed is None or emitted is None or removed + emitted == 0:
            continue
        rate = 100 * removed / (removed + emitted)
        eid = f"EV-REMOVAL-{key}"
        evidence_items.append(evidence(eid, "mass_balance_removal_rate", rate, "pct",
                                       observation_sources(data, f"{key}_removed_kg") + observation_sources(data, f"{key}_emitted_kg"),
                                       "removed/(removed+emitted)*100"))
        removal.append({"pollutant": label, "key": key, "removed_kg": removed,
                        "emitted_kg": emitted, "rate_pct": rate, "evidence_id": eid})
    cost_items = []
    cost_names = profile.get("cost_metric_labels", {})
    for metric_id in profile.get("cost_scope", {}).get("included_metrics", []):
        value = total(data, metric_id)
        if value is not None:
            cost_items.append({"metric_id": metric_id, "label": cost_names.get(metric_id, metric_id), "cost_cny": value})
    selected_total = sum(item["cost_cny"] for item in cost_items)
    for item in cost_items:
        item["share_pct"] = 100 * item["cost_cny"] / selected_total if selected_total else None
        item["evidence_id"] = f"EV-COST-{item['metric_id']}"
        evidence_items.append(evidence(item["evidence_id"], "annual_cost", item["cost_cny"], "CNY",
                                       observation_sources(data, item["metric_id"]), "sum(monthly cost)"))
    all_cost_total = sum(total(data, metric) or 0 for metric in profile.get("recognized_cost_metrics", []))
    evidence_items.append(evidence("EV-COST-CORE-TOTAL", "cost_subtotal", selected_total, "CNY",
                                   [source for item in cost_items for source in observation_sources(data, item["metric_id"])],
                                   "sum(configured core cost metrics)"))
    evidence_items.append(evidence("EV-COST-RECOGNIZED-TOTAL", "cost_subtotal", all_cost_total, "CNY", [],
                                   "sum(all recognized cost metrics)"))
    payload = {"schema_version": "0.1", "project": data["project"], "analysis_year": data["analysis_year"],
               "periods": data["periods"], "statistics": stats, "annual_flow_m3": flow_total,
               "removal_efficiency": removal, "cost_scope": profile["cost_scope"],
               "cost_items": cost_items, "core_cost_total_cny": selected_total,
               "recognized_cost_total_cny": all_cost_total, "comparisons": comparison_results,
               "plant_performance": plant_performance, "evidence": evidence_items,
               "quality_issues": validation.get("issues", [])}
    write_json(args.output, payload)


if __name__ == "__main__":
    main()
