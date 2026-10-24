# Task Breakdown: Ghost Data Still Exists (Deletion-Audit Agent)

This document outlines the detailed roadmap, milestones, and acceptance criteria for building, benchmarking, and packaging the AI-powered deletion-audit agent for HackerRank Orchestrate (October 2026).

---

## Progress Overview

| Phase | Description | Status | Target Completion |
|---|---|---|---|
| **Phase 1** | System Design & Module Setup | `[x]` Completed | Milestone 1 |
| **Phase 2** | Identity Resolution & Multilingual Intent Classifier | `[x]` Completed | Milestone 2 |
| **Phase 3** | Evidence & Activity Indexing Engine | `[x]` Completed | Milestone 3 |
| **Phase 4** | Policy Enforcement & Reconciliation Audit Engine | `[x]` Completed | Milestone 4 |
| **Phase 5** | Canonical Step Sequencer & Serializer | `[x]` Completed | Milestone 5 |
| **Phase 6** | Benchmarking & 100% Agreement on Sample Dataset (32 cases) | `[x]` Completed | Milestone 6 |
| **Phase 7** | Full Dataset Execution (518 cases) & `output.csv` | `[x]` Completed | Milestone 7 |
| **Phase 8** | Evaluation Reports, README & Final Packaging (`code.zip`) | `[x]` Completed | Milestone 8 |

---

## Detailed Task Checklist

### Phase 1: System Design & Project Architecture Setup
- [x] **Task 1.1: Project Structure Setup**
  - Create modular code structure in `code/`:
    - `code/config.py`: Path resolutions, constants, schemas, operational ordering definitions.
    - `code/identity.py`: User identity graph and historical audit resolution.
    - `code/intent.py`: Multilingual request classification (Deletion vs. Non-Deletion).
    - `code/evidence_indexer.py`: Parser and indexer for SQLite, logs, JSON/text, images, PDFs.
    - `code/audit_engine.py`: Core rule reconciliation, violation detection, and risk analysis.
    - `code/sequencer.py`: Strict step ordering and JSON serialization.
    - `code/main.py`: CLI entry point running the full pipeline end-to-end.
    - `code/evaluation/main.py`: Benchmark evaluation against ground truth.
- [x] **Task 1.2: Metrics & Usage Tracker**
  - Implement token, runtime, and cost tracking decorator/wrapper for LLM calls and system operations to satisfy `usage_report.md` requirements.
- [x] **Task 1.3: Schema & Output Validation Utility**
  - Write a validator script verifying:
    - Exactly 518 data rows (+ header) sorted by `case_id`.
    - Columns: `case_id,deletion_status,steps_json`.
    - Valid JSON array for `steps_json` with 1-indexed consecutive step numbers.
    - Strict phase and operation sorting order.
    - Valid evidence citations for findings and COMPLETE verifications; empty strings for remediation.

---

### Phase 2: Identity Resolution & Multilingual Request Intent Engine
- [x] **Task 2.1: Identity Graph Construction**
  - Parse `dataset/user_identities.csv` (851 records) capturing `user_id`, `name`, `email`, `phone`, `email_hash`, and `updated_at`.
  - Parse `dataset/user_audit_log.csv` (307 records) tracking historical mutations of phone, email, and name.
  - Build bidirectional resolver mapping any current/historical identifier to the primary `user_id` and all associated aliases.
- [x] **Task 2.2: Multilingual Intent Classification**
  - Identify whether `request_text` explicitly authorizes deletion vs. non-deletion (e.g., access, data export, profile correction, invoice copies, marketing preferences).
  - Support multiple languages present in dataset: English, Spanish, French, German, Japanese, Korean, Portuguese, etc.
  - Set `deletion_status = "NOT_APPLICABLE"` and `steps_json = []` for non-deletion requests.
- [x] **Task 2.3: Verification of Intent & Identity**
  - Test against non-deletion cases (e.g., cases 533, 535, 537, 540, 541).
  - Verify 100% resolution of emails in `sample_deletion_requests.csv`.

---

### Phase 3: Evidence & Activity Indexing Engine
- [x] **Task 3.1: Temporal Filter & Evidence Manifest Handler**
  - Parse `dataset/evidence_files.csv` (95 evidence files across databases, documents, images, logs, records).
  - Enforce temporal cutoff: only process evidence where `captured_at <= audit_at`.
- [x] **Task 3.2: SQLite Database Snapshot Ingestion**
  - Ingest SQL files under `dataset/evidence/databases/` into in-memory or cached SQLite databases.
  - Enable rapid querying by `user_id`, `email`, `phone`, `email_hash`, or resource IDs across primary, failover, and regional replicas.
- [x] **Task 3.3: Logs and Record Snapshot Ingestion**
  - Index structured logs (`.log`) under `dataset/evidence/logs/` (with JSON and key-value extraction).
  - Parse JSON and TXT bundles under `dataset/evidence/records/` (account handovers, snapshot bundles, connector configs).
- [x] **Task 3.4: Multimodal Document & Image Extraction**
  - Extract text and structured metadata from PDF documents (`dataset/evidence/documents/`).
  - Parse text/tables from admin portal screenshots (`dataset/evidence/images/`).
- [x] **Task 3.5: Global Activity Correlator**
  - Parse `dataset/system_activity.csv` (4,012 events) filtering by `event_time <= audit_at`.
  - Correlate events involving relevant resources and user identifiers.

---

### Phase 4: Policy Enforcement & Reconciliation Audit Engine
- [x] **Task 4.1: Policy Rule Engine**
  - Implement exact rules from `dataset/deletion_rules.csv`:
    - `USER_PROFILE`, `SECONDARY_IDENTIFIER`, `SEARCH_INDEX_ENTRY`, `CACHE_ENTRY`, `USER_EXPORT`, `MARKETING_PROFILE`, `SUPPORT_ATTACHMENT` $\rightarrow$ `DELETE`
    - `SUPPORT_MESSAGE`, `EMAIL_DELIVERY_LOG` $\rightarrow$ `REDACT`
    - `ANALYTICS_PROFILE`, `PRODUCT_TELEMETRY` $\rightarrow$ `ANONYMIZE`
    - `SECURITY_AUDIT_LOG`, `LEGAL_HOLD_RECORD`, `BACKUP_ARCHIVE` $\rightarrow$ `RETAIN`
- [x] **Task 4.2: Account Tombstone Validation**
  - For deleted accounts preserving an `ACCOUNT_TOMBSTONE`:
    - Confirm stable `user_id` is preserved.
    - Flag violation (`REPORT_EXPOSED_PII`) if direct identifiers (`name`, `email`, `phone`, `email_hash`) remain present.
- [x] **Task 4.3: Active Data Flow & Restore Risk Detection**
  - Detect active synchronization, replication, or indexing jobs capable of recreating deleted user data (`REPORT_ACTIVE_DATA_FLOW`).
  - Detect backup snapshots containing unpurged user records that lack restore-blocking controls (`REPORT_RESTORE_RISK`).
- [x] **Task 4.4: Status Decision Logic**
  - If any remaining record, exposed PII, active data flow, or restore risk exists $\rightarrow$ `INCOMPLETE`.
  - If all data is deleted/redacted/anonymized according to policy, retained records are preserved, and no recreation risk exists $\rightarrow$ `COMPLETE`.

---

### Phase 5: Canonical Step Sequencer & Serializer
- [x] **Task 5.1: Remediation & Verification Synthesis**
  - For `COMPLETE`: Generate `VERIFICATION` steps proving the compliant state at `audit_at` citing the proving `evidence_id`.
  - For `INCOMPLETE`:
    - Generate `FINDING` steps citing participant-visible evidence (`file_id`, `activity_id`, or `audit_id`).
    - Synthesize `REMEDIATION` steps (`DISABLE_DATA_FLOW`, `BLOCK_RESTORE`, `DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`) with `evidence_id = ""`.
    - Synthesize post-remediation `VERIFICATION` checks with `evidence_id = ""`.
- [x] **Task 5.2: Strict Sorting Order Implementation**
  - Sort by Phase: `FINDING` $\rightarrow$ `REMEDIATION` $\rightarrow$ `VERIFICATION`.
  - Sort within Phase by problem statement operation order:
    - FINDING: `REPORT_REMAINING_RECORD` $\rightarrow$ `REPORT_EXPOSED_PII` $\rightarrow$ `REPORT_ACTIVE_DATA_FLOW` $\rightarrow$ `REPORT_RESTORE_RISK`
    - REMEDIATION: `DISABLE_DATA_FLOW` $\rightarrow$ `BLOCK_RESTORE` $\rightarrow$ `DELETE_RECORD` $\rightarrow$ `REDACT_RECORD` $\rightarrow$ `ANONYMIZE_RECORD`
    - VERIFICATION: `VERIFY_RECORD_ABSENT` $\rightarrow$ `VERIFY_RECORD_PRESENT` $\rightarrow$ `VERIFY_RECORD_REDACTED` $\rightarrow$ `VERIFY_RECORD_ANONYMIZED` $\rightarrow$ `VERIFY_DATA_FLOW_DISABLED` $\rightarrow$ `VERIFY_RESTORE_BLOCKED`
  - Secondary Sort: `system_id` ascending, then `resource_id` ascending.
  - Consecutively number steps starting at `1`.

---

### Phase 6: Benchmarking & 100% Agreement on Sample Dataset
- [x] **Task 6.1: Run Benchmark Evaluation on Sample Cases**
  - Execute audit pipeline on `dataset/sample_deletion_requests.csv` (32 cases).
  - Compare generated steps with `dataset/sample_output.csv`.
- [x] **Task 6.2: Diff & Failure Analysis**
  - Evaluate:
    - Case status accuracy: 32/32 (100.00%).
    - Step-level accuracy: 193/193 (100.00%).
    - Evidence ID citations: 100% match.
    - Exact JSON ordering and sequence match: 32/32 (100.00%).
- [x] **Task 6.3: Refine Audit Logic**
  - Resolved JSON log parsing, quote escaping, tuple membership checks, and analytics profile matching.

---

### Phase 7: Full Dataset Execution & Prediction Generation
- [x] **Task 7.1: Full Production Run**
  - Run `code/main.py` across all 518 cases in `dataset/deletion_requests.csv`.
  - Write output to root `output.csv`.
- [x] **Task 7.2: Sanity Checks & Contract Verification**
  - Verify row count: exactly 518 data rows.
  - Verify `case_id` sort order (`case_33` through `case_550`).
  - Verify no empty fields, valid JSON arrays, consecutive 1-indexed numbering.

---

### Phase 8: Reports, README & Submission Packaging
- [x] **Task 8.1: Create Evaluation Report (`code/evaluation/evaluation_report.md`)**
  - Document status accuracy, step-level accuracy, and sequence accuracy (100% on benchmark).
  - Include 3 custom-crafted evaluation cases (`custom_case_01`, `custom_case_02`, `custom_case_03`).
  - Document failure modes discovered and improvements implemented.
- [x] **Task 8.2: Create Usage Report (`code/evaluation/usage_report.md`)**
  - Document model names, call counts, token counts, latency (0.12s full run), and cost breakdown ($0.028 total).
- [x] **Task 8.3: Update `README.md`**
  - Complete execution instructions (`python3 code/main.py`), requirements, architecture details, benchmark tables.
- [x] **Task 8.4: Package `code.zip`**
  - Create `code.zip` containing `code/`, `README.md`, and `evaluation/`.
  - Ensure zero datasets, caches, or virtual environments are bundled.
  - Verify no secrets or real personal data exist in any submission files or `log.txt`.
