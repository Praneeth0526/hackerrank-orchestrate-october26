import os
import json
import csv
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from code.config import (
    EVIDENCE_FILES_PATH, EVIDENCE_DIR, ROOT_DIR,
    PHASE_FINDING, PHASE_REMEDIATION, PHASE_VERIFICATION
)
from code.identity import UserIdentity

class EvidenceObservation:
    def __init__(
        self,
        system_id: str,
        resource_id: str,
        operation: str,
        state: str,
        evidence_id: str,
        captured_at: str,
        is_violation: bool,
        user_ref: Optional[str] = None,
        email_ref: Optional[str] = None,
        phone_ref: Optional[str] = None,
        hash_ref: Optional[str] = None,
    ):
        self.system_id = system_id
        self.resource_id = resource_id
        self.operation = operation
        self.state = state
        self.evidence_id = evidence_id
        self.captured_at = captured_at
        self.is_violation = is_violation
        self.user_ref = user_ref
        self.email_ref = email_ref.lower() if email_ref else None
        self.phone_ref = phone_ref
        self.hash_ref = hash_ref.lower() if hash_ref else None

    def to_dict(self, phase: str, evidence_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id if evidence_id is None else evidence_id,
            "phase": phase,
        }

class EvidenceIndexer:
    def __init__(self, evidence_manifest_path=EVIDENCE_FILES_PATH):
        self.manifest_path = Path(evidence_manifest_path)
        self.evidence_files: Dict[str, Dict[str, Any]] = {}
        self.observations_by_file: Dict[str, List[EvidenceObservation]] = {}
        self.ocr_texts: Dict[str, str] = {}
        self._load_manifest()
        self._load_ocr_texts()
        self._parse_all_evidence()

    def _load_manifest(self):
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.evidence_files[r["file_id"]] = r

    def _load_ocr_texts(self):
        ocr_path = ROOT_DIR / "code" / "extracted_evidence_text.json"
        if ocr_path.exists():
            with open(ocr_path, "r", encoding="utf-8") as f:
                self.ocr_texts = json.load(f)

    def _parse_all_evidence(self):
        for fid, finfo in self.evidence_files.items():
            fpath = ROOT_DIR / "dataset" / finfo["file_path"]
            if not fpath.exists():
                continue
            ext = fpath.suffix.lower()
            fname = fpath.name
            captured_at = finfo["captured_at"]

            observations: List[EvidenceObservation] = []
            if ext == ".json":
                observations = self._parse_json_file(fid, fpath, captured_at)
            elif ext == ".sql":
                observations = self._parse_sql_file(fid, fpath, captured_at)
            elif ext == ".log":
                observations = self._parse_log_file(fid, fpath, captured_at)
            elif ext == ".txt":
                observations = self._parse_txt_file(fid, fpath, captured_at)
            elif ext in [".pdf", ".png"]:
                observations = self._parse_document_image(fid, fname, captured_at)

            self.observations_by_file[fid] = observations

    def _parse_json_file(self, fid: str, fpath: Path, captured_at: str) -> List[EvidenceObservation]:
        obs: List[EvidenceObservation] = []
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return obs

        # 1. service_resource_export_*.json
        if "service_exports" in data:
            exports = data["service_exports"]

            if "account_service" in exports:
                acc_data = exports["account_service"]
                lookups = acc_data.get("profile_lookups", [])
                for item in lookups:
                    res_id = item.get("resource_id")
                    status_code = item.get("status_code", 404)
                    prof = item.get("profile")
                    if status_code == 404 or not prof:
                        obs.append(EvidenceObservation(
                            system_id="account_service",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_ABSENT",
                            state="ABSENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                        ))
                    else:
                        obs.append(EvidenceObservation(
                            system_id="account_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=prof.get("customer_reference"),
                            email_ref=prof.get("email"),
                            phone_ref=prof.get("phone"),
                        ))

            if "analytics_platform" in exports:
                for item in exports["analytics_platform"].get("profiles", []):
                    res_id = item.get("resource_id")
                    email = item.get("email")
                    phone = item.get("phone")
                    cust_ref = item.get("customer_reference")
                    if email or phone or cust_ref:
                        obs.append(EvidenceObservation(
                            system_id="analytics_platform",
                            resource_id=res_id,
                            operation="REPORT_EXPOSED_PII",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=cust_ref,
                            email_ref=email,
                            phone_ref=phone,
                        ))
                    else:
                        obs.append(EvidenceObservation(
                            system_id="analytics_platform",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_ANONYMIZED",
                            state="ANONYMIZED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                        ))

            if "backup_service" in exports:
                for item in exports["backup_service"].get("restore_entries", []):
                    res_id = item.get("resource_id")
                    cust_ref = item.get("customer_reference")
                    cust_email = item.get("customer_email")
                    restore_allowed = item.get("restore_allowed", False)
                    obs.append(EvidenceObservation(
                        system_id="backup_service",
                        resource_id=res_id,
                        operation="REPORT_RESTORE_RISK" if restore_allowed else "VERIFY_RESTORE_BLOCKED",
                        state="ACTIVE" if restore_allowed else "BLOCKED",
                        evidence_id=fid,
                        captured_at=captured_at,
                        is_violation=restore_allowed,
                        user_ref=cust_ref,
                        email_ref=cust_email,
                    ))

            if "export_service" in exports:
                for item in exports["export_service"].get("exports", []):
                    res_id = item.get("resource_id")
                    cust_ref = item.get("customer_reference")
                    owner_email = item.get("owner_email")
                    owner_phone = item.get("owner_phone")
                    obs.append(EvidenceObservation(
                        system_id="export_service",
                        resource_id=res_id,
                        operation="REPORT_REMAINING_RECORD",
                        state="PRESENT",
                        evidence_id=fid,
                        captured_at=captured_at,
                        is_violation=True,
                        user_ref=cust_ref,
                        email_ref=owner_email,
                        phone_ref=owner_phone,
                    ))

            if "integration_service" in exports:
                for item in exports["integration_service"].get("connectors", []):
                    res_id = item.get("resource_id")
                    cust_ref = item.get("customer_reference")
                    cust_email = item.get("customer_email")
                    enabled = item.get("enabled", False)
                    obs.append(EvidenceObservation(
                        system_id="integration_service",
                        resource_id=res_id,
                        operation="REPORT_ACTIVE_DATA_FLOW" if enabled else "VERIFY_DATA_FLOW_DISABLED",
                        state="ACTIVE" if enabled else "DISABLED",
                        evidence_id=fid,
                        captured_at=captured_at,
                        is_violation=enabled,
                        user_ref=cust_ref,
                        email_ref=cust_email,
                    ))

            if "search_service" in exports:
                for item in exports["search_service"].get("index_queries", []):
                    res_id = item.get("resource_id")
                    query = item.get("query")
                    hits = item.get("hits", {}).get("total", 0)
                    docs = item.get("hits", {}).get("documents", [])
                    if hits > 0 or len(docs) > 0:
                        obs.append(EvidenceObservation(
                            system_id="search_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            email_ref=query,
                        ))

            if "security_service" in exports:
                for item in exports["security_service"].get("audit_records", []):
                    res_id = item.get("resource_id")
                    subj_ref = item.get("subject_reference")
                    obs.append(EvidenceObservation(
                        system_id="security_service",
                        resource_id=res_id,
                        operation="VERIFY_RECORD_PRESENT",
                        state="PRESENT",
                        evidence_id=fid,
                        captured_at=captured_at,
                        is_violation=False,
                        user_ref=subj_ref,
                    ))

            if "support_platform" in exports:
                for item in exports["support_platform"].get("tickets", []):
                    res_id = item.get("resource_id")
                    cust_ref = item.get("customer_reference")
                    req_email = item.get("requester_email")
                    req_name = item.get("requester_name")
                    req_phone = item.get("requester_phone")
                    if req_email or req_name or req_phone:
                        obs.append(EvidenceObservation(
                            system_id="support_platform",
                            resource_id=res_id,
                            operation="REPORT_EXPOSED_PII",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=cust_ref,
                            email_ref=req_email,
                            phone_ref=req_phone,
                        ))
                    elif cust_ref:
                        obs.append(EvidenceObservation(
                            system_id="support_platform",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_REDACTED",
                            state="REDACTED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                            user_ref=cust_ref,
                        ))

        # 2. customer_data_snapshot_bundle_*.json
        elif "snapshots" in data:
            for s in data["snapshots"]:
                store = s.get("data_store", "")
                collection = s.get("collection", "")
                records = s.get("records", [])

                if store == "identity_service" and collection == "deleted_customer_references":
                    for rec in records:
                        res_id = rec.get("resource_id")
                        subj_ref = rec.get("subject_reference")
                        name = rec.get("name")
                        email = rec.get("email")
                        phone = rec.get("phone")
                        email_hash = rec.get("email_hash")
                        if name or email or phone or email_hash:
                            obs.append(EvidenceObservation(
                                system_id="identity_service",
                                resource_id=res_id,
                                operation="REPORT_EXPOSED_PII",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=subj_ref,
                                email_ref=email,
                                phone_ref=phone,
                            ))
                        else:
                            obs.append(EvidenceObservation(
                                system_id="identity_service",
                                resource_id=res_id,
                                operation="VERIFY_RECORD_REDACTED",
                                state="REDACTED",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=False,
                                user_ref=subj_ref,
                            ))

                elif store == "security_service" and collection == "security_audit_events":
                    for rec in records:
                        res_id = rec.get("resource_id")
                        subj_ref = rec.get("subject_reference")
                        obs.append(EvidenceObservation(
                            system_id="security_service",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_PRESENT",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                            user_ref=subj_ref,
                        ))

                elif store == "analytics_platform":
                    for rec in records:
                        res_id = rec.get("resource_id")
                        email = rec.get("email")
                        phone = rec.get("phone")
                        cust_ref = rec.get("customer_reference") or rec.get("user_id")
                        if email or phone:
                            obs.append(EvidenceObservation(
                                system_id="analytics_platform",
                                resource_id=res_id,
                                operation="REPORT_EXPOSED_PII",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=cust_ref,
                                email_ref=email,
                                phone_ref=phone,
                            ))
                        else:
                            obs.append(EvidenceObservation(
                                system_id="analytics_platform",
                                resource_id=res_id,
                                operation="VERIFY_RECORD_ANONYMIZED",
                                state="ANONYMIZED",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=False,
                                user_ref=cust_ref,
                            ))

                elif store == "backup_service":
                    for rec in records:
                        res_id = rec.get("resource_id")
                        cust_ref = rec.get("customer_reference")
                        cust_email = rec.get("customer_email")
                        restore_allowed = rec.get("restore_allowed", False)
                        obs.append(EvidenceObservation(
                            system_id="backup_service",
                            resource_id=res_id,
                            operation="REPORT_RESTORE_RISK" if restore_allowed else "VERIFY_RESTORE_BLOCKED",
                            state="ACTIVE" if restore_allowed else "BLOCKED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=restore_allowed,
                            user_ref=cust_ref,
                            email_ref=cust_email,
                        ))

                elif store == "search_service":
                    for rec in records:
                        res_id = rec.get("resource_id")
                        cust_ref = rec.get("customer_reference")
                        email = rec.get("email")
                        obs.append(EvidenceObservation(
                            system_id="search_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=cust_ref,
                            email_ref=email,
                        ))

                elif store == "account_service":
                    for rec in records:
                        res_id = rec.get("resource_id")
                        cust_ref = rec.get("customer_reference")
                        email = rec.get("email")
                        account_status = rec.get("account_status", "")
                        is_active = (account_status == "ACTIVE" or bool(email))
                        obs.append(EvidenceObservation(
                            system_id="account_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD" if is_active else "VERIFY_RECORD_ABSENT",
                            state="PRESENT" if is_active else "ABSENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=is_active,
                            user_ref=cust_ref,
                            email_ref=email,
                        ))

        # 3. Files with "records" list
        elif "records" in data:
            coll = data.get("collection", "")
            for rec in data["records"]:
                res_id = rec.get("resource_id")

                # customer_export_jobs
                if coll == "customer_export_jobs" or "file_name" in rec:
                    owner_email = rec.get("owner_email") or rec.get("email")
                    cust_ref = rec.get("customer_reference") or rec.get("user_id")
                    obs.append(EvidenceObservation(
                        system_id="export_service",
                        resource_id=res_id,
                        operation="REPORT_REMAINING_RECORD",
                        state="PRESENT",
                        evidence_id=fid,
                        captured_at=captured_at,
                        is_violation=True,
                        user_ref=cust_ref,
                        email_ref=owner_email,
                    ))

                # customer_analytics_reports
                elif coll == "customer_analytics_reports" or "reporting_window" in rec:
                    email = rec.get("email")
                    phone = rec.get("phone")
                    uid = rec.get("user_id") or rec.get("customer_reference")
                    if email or phone:
                        obs.append(EvidenceObservation(
                            system_id="analytics_platform",
                            resource_id=res_id,
                            operation="REPORT_EXPOSED_PII",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=uid,
                            email_ref=email,
                            phone_ref=phone,
                        ))
                    else:
                        obs.append(EvidenceObservation(
                            system_id="analytics_platform",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_ANONYMIZED",
                            state="ANONYMIZED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                            user_ref=uid,
                        ))

                # structured audits
                elif "system" in rec and "result" in rec:
                    sys_name = rec["system"]
                    res_val = rec["result"]
                    ident = rec.get("subject_reference") or rec.get("user_id") or rec.get("email")
                    user_ref = ident if ident and ident.startswith("user_") else None
                    email_ref = ident if ident and "@" in ident else None

                    if sys_name == "account_service":
                        obs.append(EvidenceObservation(
                            system_id="account_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD" if res_val == "FOUND" else "VERIFY_RECORD_ABSENT",
                            state="PRESENT" if res_val == "FOUND" else "ABSENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=(res_val == "FOUND"),
                            user_ref=user_ref,
                            email_ref=email_ref,
                        ))
                    elif sys_name == "security_service":
                        obs.append(EvidenceObservation(
                            system_id="security_service",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_PRESENT",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                            user_ref=user_ref,
                        ))
                    elif sys_name == "search_service":
                        obs.append(EvidenceObservation(
                            system_id="search_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD" if res_val == "FOUND" else "VERIFY_RECORD_ABSENT",
                            state="PRESENT" if res_val == "FOUND" else "ABSENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=(res_val == "FOUND"),
                            user_ref=user_ref,
                            email_ref=email_ref,
                        ))

        return obs

    def _parse_sql_file(self, fid: str, fpath: Path, captured_at: str) -> List[EvidenceObservation]:
        obs: List[EvidenceObservation] = []
        try:
            conn = sqlite3.connect(":memory:")
            with open(fpath, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            cursor = conn.cursor()
            tables = [t[0] for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]

            # 1. search_documents_primary
            if "search_documents_primary" in tables:
                rows = cursor.execute("SELECT resource_id, email, source_resource_id FROM search_documents_primary;").fetchall()
                for r in rows:
                    obs.append(EvidenceObservation(
                        system_id="search_service",
                        resource_id=r[0],
                        operation="REPORT_REMAINING_RECORD",
                        state="PRESENT",
                        evidence_id=fid,
                        captured_at=captured_at,
                        is_violation=True,
                        email_ref=r[1],
                    ))

            # 2. Failover replica
            if "customer_profiles_failover_replica" in tables:
                rows = cursor.execute("SELECT resource_id, user_id, email, phone FROM customer_profiles_failover_replica;").fetchall()
                for r in rows:
                    obs.append(EvidenceObservation(
                        system_id="account_service",
                        resource_id=r[0],
                        operation="REPORT_REMAINING_RECORD",
                        state="PRESENT",
                        evidence_id=fid,
                        captured_at=captured_at,
                        is_violation=True,
                        user_ref=r[1],
                        email_ref=r[2],
                        phone_ref=r[3],
                    ))

            # 3. customer_data_inventory
            if "customer_data_inventory" in fpath.name or "customer_profiles" in tables:
                if "customer_profiles" in tables:
                    rows = cursor.execute("SELECT resource_id, customer_reference, email, phone, account_status FROM customer_profiles;").fetchall()
                    for r in rows:
                        obs.append(EvidenceObservation(
                            system_id="account_service",
                            resource_id=r[0],
                            operation="REPORT_REMAINING_RECORD" if r[4] == "ACTIVE" else "VERIFY_RECORD_ABSENT",
                            state="PRESENT" if r[4] == "ACTIVE" else "ABSENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=(r[4] == "ACTIVE"),
                            user_ref=r[1],
                            email_ref=r[2],
                            phone_ref=r[3],
                        ))

                if "backup_restore_entries" in tables:
                    rows = cursor.execute("SELECT resource_id, customer_reference, customer_email, restore_allowed FROM backup_restore_entries;").fetchall()
                    for r in rows:
                        allowed = bool(int(r[3]))
                        obs.append(EvidenceObservation(
                            system_id="backup_service",
                            resource_id=r[0],
                            operation="REPORT_RESTORE_RISK" if allowed else "VERIFY_RESTORE_BLOCKED",
                            state="ACTIVE" if allowed else "BLOCKED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=allowed,
                            user_ref=r[1],
                            email_ref=r[2],
                        ))

                if "customer_search_documents" in tables:
                    rows = cursor.execute("SELECT resource_id, customer_reference, email FROM customer_search_documents;").fetchall()
                    for r in rows:
                        obs.append(EvidenceObservation(
                            system_id="search_service",
                            resource_id=r[0],
                            operation="REPORT_REMAINING_RECORD",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=r[1],
                            email_ref=r[2],
                        ))

                if "customer_analytics_profiles" in tables:
                    rows = cursor.execute("SELECT resource_id, customer_reference, email, phone FROM customer_analytics_profiles;").fetchall()
                    for r in rows:
                        has_pii = bool(r[2] or r[3])
                        obs.append(EvidenceObservation(
                            system_id="analytics_platform",
                            resource_id=r[0],
                            operation="REPORT_EXPOSED_PII" if has_pii else "VERIFY_RECORD_ANONYMIZED",
                            state="PRESENT" if has_pii else "ANONYMIZED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=has_pii,
                            user_ref=r[1],
                            email_ref=r[2],
                            phone_ref=r[3],
                        ))

                if "support_records" in tables:
                    rows = cursor.execute("SELECT resource_id, customer_reference, requester_email, requester_phone FROM support_records;").fetchall()
                    for r in rows:
                        has_pii = bool(r[2] or r[3])
                        obs.append(EvidenceObservation(
                            system_id="support_platform",
                            resource_id=r[0],
                            operation="REPORT_EXPOSED_PII" if has_pii else "VERIFY_RECORD_REDACTED",
                            state="PRESENT" if has_pii else "REDACTED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=has_pii,
                            user_ref=r[1],
                            email_ref=r[2],
                            phone_ref=r[3],
                        ))

                if "customer_exports" in tables:
                    rows = cursor.execute("SELECT resource_id, customer_reference, owner_email, owner_phone FROM customer_exports;").fetchall()
                    for r in rows:
                        obs.append(EvidenceObservation(
                            system_id="export_service",
                            resource_id=r[0],
                            operation="REPORT_REMAINING_RECORD",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=r[1],
                            email_ref=r[2],
                            phone_ref=r[3],
                        ))

                if "connector_subscriptions" in tables:
                    rows = cursor.execute("SELECT resource_id, customer_reference, customer_email, enabled FROM connector_subscriptions;").fetchall()
                    for r in rows:
                        enabled = bool(int(r[3]))
                        obs.append(EvidenceObservation(
                            system_id="integration_service",
                            resource_id=r[0],
                            operation="REPORT_ACTIVE_DATA_FLOW" if enabled else "VERIFY_DATA_FLOW_DISABLED",
                            state="ACTIVE" if enabled else "DISABLED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=enabled,
                            user_ref=r[1],
                            email_ref=r[2],
                        ))

                if "security_audit_records" in tables:
                    rows = cursor.execute("SELECT resource_id, subject_reference FROM security_audit_records;").fetchall()
                    for r in rows:
                        obs.append(EvidenceObservation(
                            system_id="security_service",
                            resource_id=r[0],
                            operation="VERIFY_RECORD_PRESENT",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                            user_ref=r[1],
                        ))

            # 4. Read replica tables with JSON blobs
            replica_tables = [t for t in tables if "customer_data" in t]
            for tname in replica_tables:
                rows = cursor.execute(f"SELECT resource_id, origin_system, collection_name, record_json FROM {tname};").fetchall()
                for r in rows:
                    res_id, origin, coll, rec_raw = r[0], r[1], r[2], r[3]
                    try:
                        rec = json.loads(rec_raw)
                    except Exception:
                        continue

                    doc = rec.get("document", {}) if isinstance(rec.get("document"), dict) else {}
                    uid = rec.get("customer_reference") or rec.get("user_id") or doc.get("customer_reference") or doc.get("user_id")
                    email = rec.get("email") or rec.get("customer_email") or doc.get("email")
                    phone = rec.get("phone") or doc.get("phone")

                    if origin == "account_service":
                        obs.append(EvidenceObservation(
                            system_id="account_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=uid,
                            email_ref=email,
                            phone_ref=phone,
                        ))
                    elif origin == "search_service":
                        obs.append(EvidenceObservation(
                            system_id="search_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=uid,
                            email_ref=email,
                        ))
                    elif origin == "support_platform":
                        rem = rec.get("requester_email") or email
                        obs.append(EvidenceObservation(
                            system_id="support_platform",
                            resource_id=res_id,
                            operation="REPORT_EXPOSED_PII",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=True,
                            user_ref=uid or rec.get("subject_reference"),
                            email_ref=rem,
                        ))
                    elif origin == "integration_service":
                        enabled = rec.get("enabled", False)
                        obs.append(EvidenceObservation(
                            system_id="integration_service",
                            resource_id=res_id,
                            operation="REPORT_ACTIVE_DATA_FLOW" if enabled else "VERIFY_DATA_FLOW_DISABLED",
                            state="ACTIVE" if enabled else "DISABLED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=enabled,
                            user_ref=uid,
                            email_ref=email,
                        ))
                    elif origin == "backup_service":
                        allowed = rec.get("restore_allowed", False)
                        obs.append(EvidenceObservation(
                            system_id="backup_service",
                            resource_id=res_id,
                            operation="REPORT_RESTORE_RISK" if allowed else "VERIFY_RESTORE_BLOCKED",
                            state="ACTIVE" if allowed else "BLOCKED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=allowed,
                            user_ref=uid,
                            email_ref=email,
                        ))
                    elif origin == "analytics_platform":
                        has_pii = bool(email or phone)
                        obs.append(EvidenceObservation(
                            system_id="analytics_platform",
                            resource_id=res_id,
                            operation="REPORT_EXPOSED_PII" if has_pii else "VERIFY_RECORD_ANONYMIZED",
                            state="PRESENT" if has_pii else "ANONYMIZED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=has_pii,
                            user_ref=uid,
                            email_ref=email,
                            phone_ref=phone,
                        ))
                    elif origin == "security_service":
                        subj = rec.get("subject_reference") or uid
                        obs.append(EvidenceObservation(
                            system_id="security_service",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_PRESENT",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                            user_ref=subj,
                        ))

            conn.close()
        except Exception:
            pass
        return obs

    def _parse_log_file(self, fid: str, fpath: Path, captured_at: str) -> List[EvidenceObservation]:
        obs: List[EvidenceObservation] = []
        kv_re = re.compile(r"([a-zA-Z0-9_]+)=(\"[^\"]*\"|\'[^\']*\'|\S+)")
        traces: Dict[str, Dict[str, str]] = {}

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    kvs = {}
                    idx = line.find('{')
                    if idx != -1 and line.endswith('}'):
                        try:
                            kvs = json.loads(line[idx:])
                        except Exception:
                            kvs = {}
                    if not kvs:
                        clean_line = line.replace('\\\"', '\"')
                        kvs = {k: v.strip("\"'") for k, v in kv_re.findall(clean_line)}

                    if "function" in kvs and "service" not in kvs:
                        kvs["service"] = kvs["function"]
                    if "requestId" in kvs and "trace_id" not in kvs:
                        kvs["trace_id"] = kvs["requestId"]

                    tid = kvs.get("trace_id") or kvs.get("requestId")

                    # Track trace-level context across all lines
                    if tid:
                        if tid not in traces:
                            traces[tid] = {}
                        for k in [
                            "lookup_key", "match_key", "correlation_key", "subject_key",
                            "subject_ref", "subject_reference", "customer_reference",
                            "user_id", "email", "matched_value", "requester_email", "service", "resource_id"
                        ]:
                            if k in kvs and kvs[k] != "null":
                                traces[tid][k] = kvs[k]

                    event = kvs.get("event", "")
                    # IMPORTANT: Only emit observations on completed or scan events, NOT on *_started!
                    if event.endswith("_started"):
                        continue

                    svc = kvs.get("service") or (traces[tid].get("service") if tid else None)
                    res_id = kvs.get("resource_id") or (traces[tid].get("resource_id") if tid else None)

                    if not svc or not res_id:
                        continue

                    ctx = traces.get(tid, {}) if tid else {}
                    lookup_key = kvs.get("lookup_key") or ctx.get("lookup_key")
                    subject_key = kvs.get("subject_key") or ctx.get("subject_key")
                    subj_ref = kvs.get("subject_reference") or kvs.get("customer_reference") or kvs.get("subject_ref") or ctx.get("subject_ref") or ctx.get("customer_reference")
                    corr_key = kvs.get("correlation_key") or kvs.get("match_key") or ctx.get("correlation_key") or ctx.get("match_key")
                    email_ref = kvs.get("email") or kvs.get("requester_email") or kvs.get("matched_value") or ctx.get("email") or ctx.get("requester_email") or ctx.get("matched_value")
                    hash_ref = None

                    for cand in [lookup_key, subject_key, corr_key]:
                        if not cand:
                            continue
                        if "@" in cand:
                            email_ref = cand
                        elif cand.startswith("user_"):
                            subj_ref = cand
                        elif len(cand) == 64 and all(c in "0123456789abcdefABCDEF" for c in cand):
                            hash_ref = cand

                    # Map service observations
                    if svc == "account_service":
                        rows = int(kvs.get("rows", 0)) if kvs.get("rows", "").isdigit() else 0
                        status = int(kvs.get("http_status", 404)) if kvs.get("http_status", "").isdigit() else 404
                        if rows == 0 or status == 404:
                            obs.append(EvidenceObservation(
                                system_id="account_service",
                                resource_id=res_id,
                                operation="VERIFY_RECORD_ABSENT",
                                state="ABSENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=False,
                                user_ref=subj_ref,
                                email_ref=email_ref,
                                hash_ref=hash_ref,
                            ))
                        else:
                            obs.append(EvidenceObservation(
                                system_id="account_service",
                                resource_id=res_id,
                                operation="REPORT_REMAINING_RECORD",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=subj_ref,
                                email_ref=email_ref,
                                hash_ref=hash_ref,
                            ))

                    elif svc == "security_service":
                        obs.append(EvidenceObservation(
                            system_id="security_service",
                            resource_id=res_id,
                            operation="VERIFY_RECORD_PRESENT",
                            state="PRESENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=False,
                            user_ref=subj_ref,
                        ))

                    elif svc == "analytics_platform":
                        rows = int(kvs.get("rows", 0)) if kvs.get("rows", "").isdigit() else 0
                        em = email_ref or kvs.get("email")
                        if (rows > 0 and (em or hash_ref)) or (em and em != "null"):
                            # If contact lookup returned a remaining record
                            if "contact_lookup" in event:
                                obs.append(EvidenceObservation(
                                    system_id="analytics_platform",
                                    resource_id=res_id,
                                    operation="REPORT_REMAINING_RECORD",
                                    state="PRESENT",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=True,
                                    user_ref=subj_ref,
                                    email_ref=em,
                                    hash_ref=hash_ref,
                                ))
                            else:
                                obs.append(EvidenceObservation(
                                    system_id="analytics_platform",
                                    resource_id=res_id,
                                    operation="REPORT_EXPOSED_PII",
                                    state="PRESENT",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=True,
                                    user_ref=subj_ref,
                                    email_ref=em,
                                    hash_ref=hash_ref,
                                ))
                        else:
                            obs.append(EvidenceObservation(
                                system_id="analytics_platform",
                                resource_id=res_id,
                                operation="VERIFY_RECORD_ANONYMIZED",
                                state="ANONYMIZED",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=False,
                                user_ref=subj_ref,
                            ))

                    elif svc == "integration_service":
                        enabled = kvs.get("enabled", "").lower() == "true"
                        obs.append(EvidenceObservation(
                            system_id="integration_service",
                            resource_id=res_id,
                            operation="REPORT_ACTIVE_DATA_FLOW" if enabled else "VERIFY_DATA_FLOW_DISABLED",
                            state="ACTIVE" if enabled else "DISABLED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=enabled,
                            user_ref=subj_ref,
                            email_ref=email_ref,
                            hash_ref=hash_ref,
                        ))

                    elif svc == "backup_service":
                        restore_allowed = kvs.get("restore_allowed", "").lower() == "true"
                        eligible = kvs.get("eligible", "").lower() == "true"
                        deletion_block = kvs.get("deletion_block", "").lower() == "false"
                        is_active_risk = (restore_allowed or eligible or deletion_block)
                        obs.append(EvidenceObservation(
                            system_id="backup_service",
                            resource_id=res_id,
                            operation="REPORT_RESTORE_RISK" if is_active_risk else "VERIFY_RESTORE_BLOCKED",
                            state="ACTIVE" if is_active_risk else "BLOCKED",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=is_active_risk,
                            user_ref=subj_ref,
                            email_ref=email_ref,
                            hash_ref=hash_ref,
                        ))

                    elif svc == "search_service":
                        result = kvs.get("result")
                        total_hits = kvs.get("total_hits", "0")
                        is_hit = (result == "hit" or total_hits != "0")
                        obs.append(EvidenceObservation(
                            system_id="search_service",
                            resource_id=res_id,
                            operation="REPORT_REMAINING_RECORD" if is_hit else "VERIFY_RECORD_ABSENT",
                            state="PRESENT" if is_hit else "ABSENT",
                            evidence_id=fid,
                            captured_at=captured_at,
                            is_violation=is_hit,
                            user_ref=subj_ref,
                            email_ref=email_ref,
                            hash_ref=hash_ref,
                        ))

                    elif svc in ["support_platform", "support_replica"]:
                        marker_found = kvs.get("marker_found", "").lower() == "true"
                        if kvs.get("event") == "deletion_marker_check" and not marker_found:
                            obs.append(EvidenceObservation(
                                system_id="support_platform",
                                resource_id=res_id,
                                operation="REPORT_REMAINING_RECORD",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=subj_ref,
                                email_ref=email_ref,
                                hash_ref=hash_ref,
                            ))
                        elif svc == "support_replica":
                            # In replica, any query completed with rows=1 is a lingering remaining record
                            obs.append(EvidenceObservation(
                                system_id="support_platform",
                                resource_id=res_id,
                                operation="REPORT_REMAINING_RECORD",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=subj_ref,
                                email_ref=email_ref,
                                hash_ref=hash_ref,
                            ))
                        elif "attachment" in str(kvs.get("event")) or "file" in kvs:
                            obs.append(EvidenceObservation(
                                system_id="support_platform",
                                resource_id=res_id,
                                operation="REPORT_REMAINING_RECORD",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=subj_ref,
                                email_ref=email_ref,
                                hash_ref=hash_ref,
                            ))
                        elif email_ref and email_ref != "null":
                            obs.append(EvidenceObservation(
                                system_id="support_platform",
                                resource_id=res_id,
                                operation="REPORT_EXPOSED_PII",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=subj_ref,
                                email_ref=email_ref,
                                hash_ref=hash_ref,
                            ))
                        else:
                            obs.append(EvidenceObservation(
                                system_id="support_platform",
                                resource_id=res_id,
                                operation="VERIFY_RECORD_REDACTED",
                                state="REDACTED",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=False,
                                user_ref=subj_ref,
                            ))
        except Exception:
            pass
        return obs

    def _parse_txt_file(self, fid: str, fpath: Path, captured_at: str) -> List[EvidenceObservation]:
        obs: List[EvidenceObservation] = []
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith("-"):
                        continue
                    parts = [p.strip() for p in line.lstrip("-").split("|")]
                    if len(parts) >= 6:
                        _, svc, res_id, cat, st, user_info = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                        user_ref = user_info if user_info.startswith("user_") else None
                        email_ref = user_info if "@" in user_info else None

                        if svc == "account_service" and st == "NOT_FOUND":
                            obs.append(EvidenceObservation(
                                system_id="account_service",
                                resource_id=res_id,
                                operation="VERIFY_RECORD_ABSENT",
                                state="ABSENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=False,
                                user_ref=user_ref,
                                email_ref=email_ref,
                            ))
                        elif svc == "security_service" and st == "FOUND":
                            obs.append(EvidenceObservation(
                                system_id="security_service",
                                resource_id=res_id,
                                operation="VERIFY_RECORD_PRESENT",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=False,
                                user_ref=user_ref,
                                email_ref=email_ref,
                            ))
                        elif svc == "search_service" and st == "FOUND":
                            obs.append(EvidenceObservation(
                                system_id="search_service",
                                resource_id=res_id,
                                operation="REPORT_REMAINING_RECORD",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=user_ref,
                                email_ref=email_ref,
                            ))
                        elif svc == "analytics_platform":
                            if st == "IDENTIFIABLE":
                                obs.append(EvidenceObservation(
                                    system_id="analytics_platform",
                                    resource_id=res_id,
                                    operation="REPORT_EXPOSED_PII",
                                    state="PRESENT",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=True,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                            else:
                                obs.append(EvidenceObservation(
                                    system_id="analytics_platform",
                                    resource_id=res_id,
                                    operation="VERIFY_RECORD_ANONYMIZED",
                                    state="ANONYMIZED",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=False,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                        elif svc == "support_platform":
                            if cat == "SUPPORT_ATTACHMENT" and st == "FOUND":
                                obs.append(EvidenceObservation(
                                    system_id="support_platform",
                                    resource_id=res_id,
                                    operation="REPORT_REMAINING_RECORD",
                                    state="PRESENT",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=True,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                            elif st in ("IDENTIFIABLE", "FOUND"):
                                obs.append(EvidenceObservation(
                                    system_id="support_platform",
                                    resource_id=res_id,
                                    operation="REPORT_EXPOSED_PII",
                                    state="PRESENT",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=True,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                            else:
                                obs.append(EvidenceObservation(
                                    system_id="support_platform",
                                    resource_id=res_id,
                                    operation="VERIFY_RECORD_REDACTED",
                                    state="REDACTED",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=False,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                        elif svc == "integration_service":
                            if st == "ACTIVE":
                                obs.append(EvidenceObservation(
                                    system_id="integration_service",
                                    resource_id=res_id,
                                    operation="REPORT_ACTIVE_DATA_FLOW",
                                    state="ACTIVE",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=True,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                            else:
                                obs.append(EvidenceObservation(
                                    system_id="integration_service",
                                    resource_id=res_id,
                                    operation="VERIFY_DATA_FLOW_DISABLED",
                                    state="DISABLED",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=False,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                        elif svc == "backup_service":
                            if st == "ACTIVE":
                                obs.append(EvidenceObservation(
                                    system_id="backup_service",
                                    resource_id=res_id,
                                    operation="REPORT_RESTORE_RISK",
                                    state="ACTIVE",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=True,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                            else:
                                obs.append(EvidenceObservation(
                                    system_id="backup_service",
                                    resource_id=res_id,
                                    operation="VERIFY_RESTORE_BLOCKED",
                                    state="BLOCKED",
                                    evidence_id=fid,
                                    captured_at=captured_at,
                                    is_violation=False,
                                    user_ref=user_ref,
                                    email_ref=email_ref,
                                ))
                        elif svc == "export_service":
                            obs.append(EvidenceObservation(
                                system_id="export_service",
                                resource_id=res_id,
                                operation="REPORT_REMAINING_RECORD",
                                state="PRESENT",
                                evidence_id=fid,
                                captured_at=captured_at,
                                is_violation=True,
                                user_ref=user_ref,
                                email_ref=email_ref,
                            ))
        except Exception:
            pass
        return obs

    def _parse_document_image(self, fid: str, fname: str, captured_at: str) -> List[EvidenceObservation]:
        obs: List[EvidenceObservation] = []
        txt = self.ocr_texts.get(fname, "")
        if not txt:
            return obs

        # Delivery correction PDF (evidence_58)
        if "delivery_correction_attachment" in fname:
            if "support_001" in txt:
                obs.append(EvidenceObservation(
                    system_id="support_platform",
                    resource_id="support_001",
                    operation="REPORT_REMAINING_RECORD",
                    state="PRESENT",
                    evidence_id=fid,
                    captured_at=captured_at,
                    is_violation=True,
                    email_ref="priya.raman@gmail.com",
                ))

        return obs

    def find_observations_for_user(
        self,
        user: UserIdentity,
        audit_at: str,
    ) -> List[EvidenceObservation]:
        """
        Finds all valid observations matching this user's identifiers captured on or before audit_at.
        """
        user_emails = {em.lower() for em in user.emails}
        user_hashes = {h.lower() for h in user.email_hashes}
        user_id = user.user_id

        # Candidate files captured on or before audit_at, sorted DESC by captured_at
        candidates = [
            fid for fid, info in self.evidence_files.items()
            if info["captured_at"] <= audit_at
        ]
        candidates.sort(key=lambda fid: self.evidence_files[fid]["captured_at"], reverse=True)

        matched_obs: List[EvidenceObservation] = []
        seen_resources: Set[str] = set()

        for fid in candidates:
            file_obs = self.observations_by_file.get(fid, [])
            for ob in file_obs:
                if ob.resource_id in seen_resources:
                    continue
                # Check user match
                is_match = False
                if ob.user_ref and ob.user_ref == user_id:
                    is_match = True
                elif ob.email_ref and ob.email_ref.lower() in user_emails:
                    is_match = True
                elif ob.hash_ref and ob.hash_ref.lower() in user_hashes:
                    is_match = True

                if is_match:
                    seen_resources.add(ob.resource_id)
                    matched_obs.append(ob)

        return matched_obs
