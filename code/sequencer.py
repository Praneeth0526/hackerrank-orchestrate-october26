import json
from typing import List, Dict, Any
from code.config import OPERATION_PRIORITY

PHASE_PRIORITY = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}

class StepSequencer:
    """
    Ensures that steps are correctly sorted according to the problem contract:
    1. Phase: FINDING -> REMEDIATION -> VERIFICATION
    2. Operation order within phase (per specification table)
    3. Secondary order: system_id ASC, then resource_id ASC
    4. Consecutive 1-indexed numbering (step_no)
    """

    @staticmethod
    def sort_and_number(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not steps:
            return []

        def sort_key(s: Dict[str, Any]):
            phase_p = PHASE_PRIORITY.get(s["phase"], 99)
            op_p = OPERATION_PRIORITY.get(s["operation"], 999)
            sys_id = s.get("system_id", "")
            res_id = s.get("resource_id", "")
            return (phase_p, op_p, sys_id, res_id)

        sorted_steps = sorted(steps, key=sort_key)

        numbered_steps = []
        for idx, s in enumerate(sorted_steps, 1):
            step_copy = dict(s)
            step_copy["step_no"] = idx
            # Ensure evidence_id is empty string if null/None
            if step_copy.get("evidence_id") is None:
                step_copy["evidence_id"] = ""
            numbered_steps.append(step_copy)

        return numbered_steps

    @staticmethod
    def serialize(steps: List[Dict[str, Any]]) -> str:
        """
        Serializes steps array to valid JSON string.
        """
        ordered = StepSequencer.sort_and_number(steps)
        return json.dumps(ordered, separators=(",", ":"))
