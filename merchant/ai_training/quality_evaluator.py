from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _normalize_label(label: str) -> str:
    if not isinstance(label, str):
        return ""
    return " ".join(label.strip().lower().split())


@dataclass
class ReleaseGateThresholds:
    min_macro_f1: float = 0.85
    max_hallucination_rate: float = 0.02
    max_column_leakage_rate: float = 0.0
    min_success_rate: float = 0.98
    max_p95_latency_ms: int = 8000


def compute_classification_metrics(y_true: Iterable[str], y_pred: Iterable[str]) -> Dict[str, object]:
    """
    يحسب مقاييس التصنيف الأساسية:
    - precision / recall / f1 لكل فئة
    - macro averages
    - accuracy
    """
    true_labels = [_normalize_label(x) for x in y_true]
    pred_labels = [_normalize_label(x) for x in y_pred]

    if len(true_labels) != len(pred_labels):
        raise ValueError("y_true and y_pred length mismatch")

    labels = sorted(set(true_labels) | set(pred_labels))
    per_label: Dict[str, Dict[str, float]] = {}

    correct = 0
    for t, p in zip(true_labels, pred_labels):
        if t == p:
            correct += 1

    for label in labels:
        tp = sum(1 for t, p in zip(true_labels, pred_labels) if t == label and p == label)
        fp = sum(1 for t, p in zip(true_labels, pred_labels) if t != label and p == label)
        fn = sum(1 for t, p in zip(true_labels, pred_labels) if t == label and p != label)

        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        support = sum(1 for t in true_labels if t == label)

        per_label[label] = {
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "support": support,
        }

    macro_precision = _safe_div(sum(v["precision"] for v in per_label.values()), len(per_label)) if per_label else 0.0
    macro_recall = _safe_div(sum(v["recall"] for v in per_label.values()), len(per_label)) if per_label else 0.0
    macro_f1 = _safe_div(sum(v["f1"] for v in per_label.values()), len(per_label)) if per_label else 0.0
    accuracy = _safe_div(correct, len(true_labels))

    return {
        "samples": len(true_labels),
        "accuracy": round(accuracy, 6),
        "macro_precision": round(macro_precision, 6),
        "macro_recall": round(macro_recall, 6),
        "macro_f1": round(macro_f1, 6),
        "per_label": per_label,
    }


def _percentile(values: List[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = int((len(ordered) - 1) * p)
    return ordered[idx]


def evaluate_message_flow(records: List[Dict[str, object]]) -> Dict[str, object]:
    """
    يقيس جودة تدفق الرسائل على مستوى النظام.
    كل سجل متوقع أن يحتوي:
    - expected_label: str
    - predicted_label: str
    - hallucinated: bool
    - column_leakage: bool
    - success: bool
    - latency_ms: int
    """
    if not records:
        return {
            "samples": 0,
            "classification": compute_classification_metrics([], []),
            "hallucination_rate": 0.0,
            "column_leakage_rate": 0.0,
            "success_rate": 0.0,
            "latency_ms": {"p50": 0, "p95": 0, "avg": 0},
        }

    y_true = [str(r.get("expected_label", "")) for r in records]
    y_pred = [str(r.get("predicted_label", "")) for r in records]
    classification = compute_classification_metrics(y_true, y_pred)

    hallucinated_count = sum(1 for r in records if bool(r.get("hallucinated", False)))
    leakage_count = sum(1 for r in records if bool(r.get("column_leakage", False)))
    success_count = sum(1 for r in records if bool(r.get("success", False)))

    latencies = []
    for r in records:
        try:
            latencies.append(int(r.get("latency_ms", 0)))
        except (TypeError, ValueError):
            latencies.append(0)

    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

    return {
        "samples": len(records),
        "classification": classification,
        "hallucination_rate": round(_safe_div(hallucinated_count, len(records)), 6),
        "column_leakage_rate": round(_safe_div(leakage_count, len(records)), 6),
        "success_rate": round(_safe_div(success_count, len(records)), 6),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "avg": avg_latency,
        },
    }


def compare_with_baseline(current: Dict[str, object], baseline: Dict[str, object]) -> Dict[str, float]:
    """
    يقارن الأداء الحالي بخط الأساس ويعيد فروق المؤشرات الأساسية.
    """
    def _get(path: Tuple[str, ...], source: Dict[str, object], default: float = 0.0) -> float:
        node: object = source
        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
        if isinstance(node, (int, float)):
            return float(node)
        return default

    delta_macro_f1 = _get(("classification", "macro_f1"), current) - _get(("classification", "macro_f1"), baseline)
    delta_success_rate = _get(("success_rate",), current) - _get(("success_rate",), baseline)
    delta_hallucination_rate = _get(("hallucination_rate",), current) - _get(("hallucination_rate",), baseline)
    delta_column_leakage_rate = _get(("column_leakage_rate",), current) - _get(("column_leakage_rate",), baseline)
    delta_p95_latency_ms = _get(("latency_ms", "p95"), current) - _get(("latency_ms", "p95"), baseline)

    return {
        "delta_macro_f1": round(delta_macro_f1, 6),
        "delta_success_rate": round(delta_success_rate, 6),
        "delta_hallucination_rate": round(delta_hallucination_rate, 6),
        "delta_column_leakage_rate": round(delta_column_leakage_rate, 6),
        "delta_p95_latency_ms": round(delta_p95_latency_ms, 2),
    }


def validate_release_gate(metrics: Dict[str, object], thresholds: ReleaseGateThresholds | None = None) -> Dict[str, object]:
    """
    بوابة قبول للإطلاق:
    - ترجع pass/fail مع أسباب الإخفاق.
    """
    cfg = thresholds or ReleaseGateThresholds()
    failures: List[str] = []

    macro_f1 = float(metrics.get("classification", {}).get("macro_f1", 0.0))
    hallucination_rate = float(metrics.get("hallucination_rate", 1.0))
    column_leakage_rate = float(metrics.get("column_leakage_rate", 1.0))
    success_rate = float(metrics.get("success_rate", 0.0))
    p95_latency = int(metrics.get("latency_ms", {}).get("p95", 0))

    if macro_f1 < cfg.min_macro_f1:
        failures.append(f"macro_f1 below threshold: {macro_f1} < {cfg.min_macro_f1}")
    if hallucination_rate > cfg.max_hallucination_rate:
        failures.append(
            f"hallucination_rate above threshold: {hallucination_rate} > {cfg.max_hallucination_rate}"
        )
    if column_leakage_rate > cfg.max_column_leakage_rate:
        failures.append(
            f"column_leakage_rate above threshold: {column_leakage_rate} > {cfg.max_column_leakage_rate}"
        )
    if success_rate < cfg.min_success_rate:
        failures.append(f"success_rate below threshold: {success_rate} < {cfg.min_success_rate}")
    if p95_latency > cfg.max_p95_latency_ms:
        failures.append(f"p95_latency above threshold: {p95_latency} > {cfg.max_p95_latency_ms}")

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "thresholds": {
            "min_macro_f1": cfg.min_macro_f1,
            "max_hallucination_rate": cfg.max_hallucination_rate,
            "max_column_leakage_rate": cfg.max_column_leakage_rate,
            "min_success_rate": cfg.min_success_rate,
            "max_p95_latency_ms": cfg.max_p95_latency_ms,
        },
    }
