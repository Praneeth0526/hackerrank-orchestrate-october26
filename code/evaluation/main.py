import sys
import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from code.config import SAMPLE_REQUESTS_PATH, SAMPLE_OUTPUT_PATH
from code.audit_engine import AuditEngine
from code.sequencer import StepSequencer

def evaluate_sample_cases():
    engine = AuditEngine()

    with open(SAMPLE_REQUESTS_PATH, "r", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))

    with open(SAMPLE_OUTPUT_PATH, "r", encoding="utf-8") as f:
        ground_truth = list(csv.DictReader(f))

    truth_map = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in ground_truth}

    total_cases = len(requests)
    status_matches = 0
    exact_sequence_matches = 0
    total_truth_steps = 0
    matched_steps = 0

    results = []

    for req in requests:
        cid = req["case_id"]
        true_status, true_steps = truth_map.get(cid, ("UNKNOWN", []))
        pred_status, pred_steps = engine.audit_case(
            case_id=cid,
            email=req["email"],
            request_text=req["request_text"],
            audit_at=req["audit_at"],
            reported_status=req.get("reported_status"),
            requested_at=req.get("requested_at"),
            reported_at=req.get("reported_at")
        )

        status_correct = (pred_status == true_status)
        if status_correct:
            status_matches += 1

        total_truth_steps += len(true_steps)

        # Check step by step
        true_sig = [(s["phase"], s["operation"], s["system_id"], s["resource_id"], s["state"]) for s in true_steps]
        pred_sig = [(s["phase"], s["operation"], s["system_id"], s["resource_id"], s["state"]) for s in pred_steps]

        exact_match = (status_correct and true_sig == pred_sig)
        if exact_match:
            exact_sequence_matches += 1

        # Calculate step overlap
        true_set = set(true_sig)
        pred_set = set(pred_sig)
        matched_steps += len(true_set.intersection(pred_set))

        results.append({
            "case_id": cid,
            "status_correct": status_correct,
            "exact_match": exact_match,
            "true_status": true_status,
            "pred_status": pred_status,
            "true_step_count": len(true_steps),
            "pred_step_count": len(pred_steps),
            "missing_steps": list(true_set - pred_set),
            "extra_steps": list(pred_set - true_set),
        })

    status_acc = (status_matches / total_cases) * 100
    sequence_acc = (exact_sequence_matches / total_cases) * 100
    step_acc = (matched_steps / total_truth_steps) * 100 if total_truth_steps > 0 else 0

    print("========================================")
    print("   SAMPLE DATASET EVALUATION RESULTS    ")
    print("========================================")
    print(f"Total Cases:            {total_cases}")
    print(f"Status Accuracy:        {status_matches}/{total_cases} ({status_acc:.2f}%)")
    print(f"Exact Sequence Match:   {exact_sequence_matches}/{total_cases} ({sequence_acc:.2f}%)")
    print(f"Step Level Accuracy:    {matched_steps}/{total_truth_steps} ({step_acc:.2f}%)")
    print("----------------------------------------")

    for res in results:
        status_symbol = "✓" if res["exact_match"] else "✗"
        print(f"[{status_symbol}] {res['case_id']}: status ({res['pred_status']} vs {res['true_status']}) | steps: {res['pred_step_count']}/{res['true_step_count']}")
        if not res["exact_match"]:
            if res["missing_steps"]:
                print(f"    Missing: {res['missing_steps']}")
            if res["extra_steps"]:
                print(f"    Extra:   {res['extra_steps']}")

    return status_acc, sequence_acc, step_acc

if __name__ == "__main__":
    evaluate_sample_cases()
