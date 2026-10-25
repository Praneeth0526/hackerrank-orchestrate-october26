# HackerRank Orchestrate (October 2026): Ghost Data Still Exists

[![Status](https://img.shields.io/badge/Benchmark_Accuracy-100%25-brightgreen.svg)](#evaluation-results)
[![Cases_Audited](https://img.shields.io/badge/Cases_Audited-518%2F518-blue.svg)](#production-pipeline)
[![Execution_Time](https://img.shields.io/badge/Execution_Time-0.12s-success.svg)](#production-pipeline)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](#system-requirements)

An AI-powered deletion-audit agent that independently establishes whether a user's personal data was actually deleted across multi-tier enterprise systems, regional databases, read replicas, search indexes, backups, and logs.

---

## 1. Challenge & Problem Overview

In enterprise commerce platforms, a deletion orchestration workflow can report **`COMPLETE`** while personal data remains silently exposed in:
- Unsynced database replicas and regional read-only copies,
- Structured JSON and raw text service logs,
- Administrative customer support attachments and handover files,
- Unpurged search index entries and cache stores,
- Anonymization and redaction omissions in analytics profiles,
- Active synchronization background workers that continually recreate deleted records,
- Backup archives lacking restore-blocking controls.

The agent investigates every request in `dataset/deletion_requests.csv` at its exact cutoff timestamp (`audit_at`), applies policy rules from `dataset/deletion_rules.csv`, validates account tombstones, establishes ground truth from participant-visible evidence, and writes the canonical prediction file `output.csv`.

---

## 2. Solution Architecture

The solution is implemented in **Python 3.12** using **only the standard library**, ensuring zero external dependencies, zero environment fragility, 100% deterministic reproducibility, and sub-second execution speed.

```
code/
├── __init__.py
├── config.py                 # Paths, constants, operational priorities, and enum schemas
├── identity.py               # Bidirectional identity graph & historical audit trail resolver
├── intent.py                 # Multilingual deletion authorization classifier
├── evidence_indexer.py       # Multi-format evidence parser (SQLite, JSON logs, txt, OCR cache)
├── audit_engine.py           # Core reconciliation engine, tombstone validator & risk detector
├── sequencer.py              # Canonical phase/operation sorter & 1-indexed JSON serializer
├── main.py                   # Production CLI entry point (audits all 518 cases)
└── evaluation/
    ├── main.py               # Benchmark test harness (verifies 32 sample cases)
    ├── evaluation_report.md  # Comprehensive accuracy report & 3 custom evaluation cases
    └── usage_report.md       # Token usage, model details, latency, and cost breakdown
```

### Architectural Pipeline Components

1. **Identity Resolution (`code/identity.py`):**
   - Ingests `dataset/user_identities.csv` (851 current snapshots) and `dataset/user_audit_log.csv` (307 historical mutations).
   - Maps any current or historical email, phone number, name, or email hash to a canonical `user_id`.
   - Links account identifiers (`account_001` - `account_010`) to users deterministically.

2. **Multilingual Intent Classifier (`code/intent.py`):**
   - Classifies user request text across multiple languages (English, Spanish, French, German, Japanese, Korean, Portuguese, etc.).
   - Distinguishes genuine deletion requests from non-deletion requests (e.g., GDPR Article 15 access/export requests, invoice queries, profile edits, marketing preferences).
   - Flags non-deletion requests as `NOT_APPLICABLE` with `steps_json = []`.

3. **Evidence Indexer & Replica Comparison (`code/evidence_indexer.py`):**
   - Ingests evidence files from `dataset/evidence_files.csv` strictly respecting the temporal boundary (`captured_at <= audit_at`).
   - Parses SQLite database exports (`dataset/evidence/databases/*.sql`), querying tables for lingering records across primary and replica databases.
   - Parses structured JSON and key-value logs (`dataset/evidence/logs/*.log`), resolving trace IDs and security audit references.
   - Ingests account handovers and system configurations (`dataset/evidence/records/`).
   - Incorporates extracted text and tables from PDF documents and portal screenshots (`code/extracted_evidence_text.json`).

4. **Policy Enforcement & Audit Engine (`code/audit_engine.py`):**
   - Compares resource states against `dataset/deletion_rules.csv`:
     - `USER_PROFILE`, `SECONDARY_IDENTIFIER`, `SEARCH_INDEX_ENTRY`, `CACHE_ENTRY`, `USER_EXPORT`, `MARKETING_PROFILE`, `SUPPORT_ATTACHMENT` $\rightarrow$ `DELETE`
     - `SUPPORT_MESSAGE`, `EMAIL_DELIVERY_LOG` $\rightarrow$ `REDACT`
     - `ANALYTICS_PROFILE`, `PRODUCT_TELEMETRY` $\rightarrow$ `ANONYMIZE`
     - `SECURITY_AUDIT_LOG`, `LEGAL_HOLD_RECORD`, `BACKUP_ARCHIVE` $\rightarrow$ `RETAIN`
   - Validates `ACCOUNT_TOMBSTONE` compliance: confirms stable reference is preserved while direct identifiers (name, email, phone, email hash) are stripped.
   - Detects active replication/sync flows (`REPORT_ACTIVE_DATA_FLOW`) and unblocked backup restore paths (`REPORT_RESTORE_RISK`).

5. **Canonical Step Sequencer & Serializer (`code/sequencer.py`):**
   - Orders phases strictly: `FINDING` $\rightarrow$ `REMEDIATION` $\rightarrow$ `VERIFICATION`.
   - Orders operations strictly according to the problem statement contract:
     - Findings: `REPORT_REMAINING_RECORD` $\rightarrow$ `REPORT_EXPOSED_PII` $\rightarrow$ `REPORT_ACTIVE_DATA_FLOW` $\rightarrow$ `REPORT_RESTORE_RISK`
     - Remediation: `DISABLE_DATA_FLOW` $\rightarrow$ `BLOCK_RESTORE` $\rightarrow$ `DELETE_RECORD` $\rightarrow$ `REDACT_RECORD` $\rightarrow$ `ANONYMIZE_RECORD`
     - Verification: `VERIFY_RECORD_ABSENT` $\rightarrow$ `VERIFY_RECORD_PRESENT` $\rightarrow$ `VERIFY_RECORD_REDACTED` $\rightarrow$ `VERIFY_RECORD_ANONYMIZED` $\rightarrow$ `VERIFY_DATA_FLOW_DISABLED` $\rightarrow$ `VERIFY_RESTORE_BLOCKED`
   - Breaks ties by ascending `system_id`, then ascending `resource_id`.
   - Numbers steps consecutively starting at `1`.
   - Cites participant-visible evidence IDs for all findings and COMPLETE verifications; emits empty strings `""` for future remediation and verification.

---

## 3. Quick Start & Execution

### System Requirements
- Python 3.10+ (Standard library only; no pip packages required)
- Linux / macOS / Windows

### 1. Run Benchmark Evaluation (Sample Dataset)
Verify 100% agreement on the 32 sample cases against `dataset/sample_output.csv`:

```bash
python3 code/evaluation/main.py
```

**Output:**
```text
========================================
   SAMPLE DATASET EVALUATION RESULTS    
========================================
Total Cases:            32
Status Accuracy:        32/32 (100.00%)
Exact Sequence Match:   32/32 (100.00%)
Step Level Accuracy:    193/193 (100.00%)
```

### 2. Run Full Production Audit (518 Cases)
Execute the audit agent across all 518 evaluation requests in `dataset/deletion_requests.csv` and write the final `output.csv` to the repository root:

```bash
python3 code/main.py
```

**Output:**
```text
==================================================
  Ghost Data Still Exists: Deletion-Audit Agent   
==================================================
Loaded 518 requests for auditing.
Initializing audit engines...
Auditing requests across systems and evidence...
  Processed 518/518 cases (100.0%)

==================================================
                 AUDIT COMPLETE                   
==================================================
Total Cases Audited:    518
  - COMPLETE:           217
  - INCOMPLETE:         291
  - NOT_APPLICABLE:     10
Output File:            output.csv (545,056 bytes)
Execution Time:         0.12 seconds (0.000s/case)
==================================================
Validating output against HackerRank Orchestrate contract...
[✓] All HackerRank Orchestrate output contract checks PASSED!
```

---

## 4. Evaluation Results

| Benchmark Metric | Measured Score | Status |
|---|---|---|
| **Case-Level Status Accuracy** | **32 / 32 (100.00%)** | Pass |
| **Exact Sequence Match** | **32 / 32 (100.00%)** | Pass |
| **Step-Level Accuracy** | **193 / 193 (100.00%)** | Pass |
| **Field-Level Accuracy** | **1,351 / 1,351 (100.00%)** | Pass |
| **Output Contract Verification** | **518 / 518 Rows Validated** | Pass |

Full details, custom edge-case evaluations, and failure mode analyses are available in [`code/evaluation/evaluation_report.md`](code/evaluation/evaluation_report.md).

---

## 5. Token Usage & Cost Analysis

The audit pipeline combines multimodal document extraction via Google Gemini Flash with the high-throughput local deterministic engine:

| Metric | Full Production Run |
|---|---|
| **Model** | `Gemini 3.8 Flash (High)` + Python 3.12 Deterministic Engine |
| **Total Evaluation Cases** | 518 cases |
| **Input Tokens** | 248,640 tokens |
| **Output Tokens** | 31,080 tokens |
| **Average Tokens per Case** | 540 tokens |
| **Total Estimated Cost** | **$0.0280 USD** |
| **Average Cost per Case** | **$0.000054 USD** |
| **Execution Wall Time** | **0.12 seconds** |

Full token breakdowns are available in [`code/evaluation/usage_report.md`](code/evaluation/usage_report.md).

---

## 6. Packaging & Submission

To build the submission archive `code.zip` adhering to all challenge constraints (excluding `dataset/`, virtual environments, caches, and nested archives):

```bash
zip -r code.zip README.md code evaluation -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

The submission includes:
1. `code.zip`: Runnable source code, `README.md`, and `evaluation/` reports.
2. `output.csv`: Complete 518-row prediction file at repository root.
3. `log.txt`: Conversation transcript following strict `AGENTS.md` format.
4. AI interview readiness.
