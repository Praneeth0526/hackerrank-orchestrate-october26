import sys
import os
import csv
import json
import time
import argparse
from pathlib import Path

# Add repo root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from code.config import (
    DELETION_REQUESTS_PATH,
    OUTPUT_PATH,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_NOT_APPLICABLE,
    PHASE_FINDING,
    PHASE_REMEDIATION,
    PHASE_VERIFICATION,
)
from code.audit_engine import AuditEngine

def run_audit(input_path: str, output_path: str, quiet: bool = False):
    start_time = time.time()
    input_file = Path(input_path)
    output_file = Path(output_path)

    if not quiet:
        print("==================================================")
        print("  Ghost Data Still Exists: Deletion-Audit Agent   ")
        print("==================================================")
        print(f"Reading requests from: {input_file}")
        print(f"Output will be saved to: {output_file}")

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        requests = list(reader)

    total_requests = len(requests)
    if not quiet:
        print(f"Loaded {total_requests} requests for auditing.\nInitializing audit engines...")

    engine = AuditEngine()

    if not quiet:
        print("Auditing requests across systems and evidence...")

    results = []
    status_counts = {
        STATUS_COMPLETE: 0,
        STATUS_INCOMPLETE: 0,
        STATUS_NOT_APPLICABLE: 0,
    }

    for i, req in enumerate(requests, 1):
        case_id = req["case_id"]
        email = req["email"]
        request_text = req["request_text"]
        audit_at = req["audit_at"]
        reported_status = req.get("reported_status")
        requested_at = req.get("requested_at")
        reported_at = req.get("reported_at")

        status, steps = engine.audit_case(
            case_id=case_id,
            email=email,
            request_text=request_text,
            audit_at=audit_at,
            reported_status=reported_status,
            requested_at=requested_at,
            reported_at=reported_at,
        )

        status_counts[status] = status_counts.get(status, 0) + 1
        steps_json = json.dumps(steps, separators=(",", ":"))

        results.append({
            "case_id": case_id,
            "deletion_status": status,
            "steps_json": steps_json,
            "_sort_key": int(case_id.split("_")[1]) if "_" in case_id and case_id.split("_")[1].isdigit() else 0,
        })

        if not quiet and (i % 50 == 0 or i == total_requests):
            print(f"  Processed {i}/{total_requests} cases ({i / total_requests * 100:.1f}%)")

    # Sort strictly by case_id number
    results.sort(key=lambda r: r["_sort_key"])

    # Write output CSV
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for r in results:
            writer.writerow([r["case_id"], r["deletion_status"], r["steps_json"]])

    elapsed = time.time() - start_time

    if not quiet:
        print("\n==================================================")
        print("                 AUDIT COMPLETE                   ")
        print("==================================================")
        print(f"Total Cases Audited:    {total_requests}")
        print(f"  - COMPLETE:           {status_counts.get(STATUS_COMPLETE, 0)}")
        print(f"  - INCOMPLETE:         {status_counts.get(STATUS_INCOMPLETE, 0)}")
        print(f"  - NOT_APPLICABLE:     {status_counts.get(STATUS_NOT_APPLICABLE, 0)}")
        print(f"Output File:            {output_file} ({output_file.stat().st_size:,} bytes)")
        print(f"Execution Time:         {elapsed:.2f} seconds ({elapsed / max(1, total_requests):.3f}s/case)")
        print("==================================================")

    # Automated output contract validation
    validate_output(output_file, expected_count=total_requests, quiet=quiet)
    return output_file

def validate_output(output_file: Path, expected_count: int, quiet: bool = False):
    if not quiet:
        print("Validating output against HackerRank Orchestrate contract...")

    with open(output_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        assert fieldnames == ["case_id", "deletion_status", "steps_json"], (
            f"Invalid header: {fieldnames}"
        )
        rows = list(reader)

    assert len(rows) == expected_count, (
        f"Row count mismatch: expected {expected_count}, got {len(rows)}"
    )

    seen_cases = set()
    prev_num = -1

    for row in rows:
        cid = row["case_id"]
        status = row["deletion_status"]
        steps_str = row["steps_json"]

        assert cid not in seen_cases, f"Duplicate case_id: {cid}"
        seen_cases.add(cid)

        # Ordering check
        curr_num = int(cid.split("_")[1])
        assert curr_num > prev_num, f"Cases out of order: {prev_num} followed by {curr_num}"
        prev_num = curr_num

        assert status in (STATUS_COMPLETE, STATUS_INCOMPLETE, STATUS_NOT_APPLICABLE), (
            f"Invalid status: {status} in case {cid}"
        )

        steps = json.loads(steps_str)
        assert isinstance(steps, list), f"steps_json is not an array for case {cid}"

        if status == STATUS_NOT_APPLICABLE:
            assert len(steps) == 0, f"NOT_APPLICABLE must have steps_json=[]: {cid}"
        else:
            prev_phase_order = -1
            phase_map = {PHASE_FINDING: 1, PHASE_REMEDIATION: 2, PHASE_VERIFICATION: 3}

            for step_idx, step in enumerate(steps, 1):
                assert step["step_no"] == step_idx, (
                    f"Step number not consecutive in {cid}: step {step_idx} has step_no {step['step_no']}"
                )
                phase = step["phase"]
                assert phase in phase_map, f"Invalid phase {phase} in {cid}"
                curr_phase_order = phase_map[phase]
                assert curr_phase_order >= prev_phase_order, (
                    f"Phases out of order in {cid}: {phase} appeared after {prev_phase_order}"
                )
                prev_phase_order = curr_phase_order

                # Evidence checks
                if status == STATUS_COMPLETE:
                    assert step["evidence_id"] != "", (
                        f"COMPLETE verification must cite evidence_id: {cid}"
                    )
                elif phase in (PHASE_REMEDIATION, PHASE_VERIFICATION):
                    assert step["evidence_id"] == "", (
                        f"INCOMPLETE remediation/verification must have empty evidence_id: {cid}"
                    )
                elif phase == PHASE_FINDING:
                    assert step["evidence_id"] != "", (
                        f"INCOMPLETE finding must cite evidence_id: {cid}"
                    )

    if not quiet:
        print("[✓] All HackerRank Orchestrate output contract checks PASSED!")

def main():
    parser = argparse.ArgumentParser(description="HackerRank Orchestrate Deletion-Audit Agent")
    parser.add_argument("--input", default=DELETION_REQUESTS_PATH, help="Path to input deletion requests CSV")
    parser.add_argument("--output", default=str(ROOT_DIR / "output.csv"), help="Path to output CSV")
    parser.add_argument("--quiet", action="store_true", help="Suppress detailed console output")
    args = parser.parse_args()

    run_audit(input_path=args.input, output_path=args.output, quiet=args.quiet)

if __name__ == "__main__":
    main()
