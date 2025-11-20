# VPC Service Controls Automation

Self-service VPC Service Controls rule generation from Cloud Audit Logs.

**No VPC SC knowledge required.** Just paste an audit log and we generate the rules.

---

## 🚀 Quick Start

1. **You hit a VPC SC error** (permission denied from organization's policy)
2. **Get the audit log** from Cloud Logging (JSON format)
3. **Create a GitHub issue** in this repository
4. **Paste the audit log** in the issue
5. **System auto-detects:**
   - Which perimeters are involved
   - INGRESS vs EGRESS direction
   - Required service and method
   - If TLM ID is needed
6. **PRs are generated** automatically for network security review
7. **Network security approves** and rules go live

Done! No more manual Terraform writing, no more VPC SC terminology needed.

---

## 📋 What's Inside

**First time?** Start here:
- [COMPLETION_SUMMARY.md](./COMPLETION_SUMMARY.md) - Overview of what was built
- [SETUP_CHECKLIST.md](./SETUP_CHECKLIST.md) - Step-by-step setup guide

---

## 📖 Documentation

### For Requestors (Everyone)
- **[AUDIT_LOG_GUIDE.md](./AUDIT_LOG_GUIDE.md)** - How to find and submit audit logs
  - Step-by-step guide to get audit logs from Cloud Logging
  - Examples and troubleshooting
  - What happens after you submit

### For Network Security Operations Team
- **[NETSEC_REVIEW_GUIDE.md](./NETSEC_REVIEW_GUIDE.md)** - How to review and approve PRs
  - What to check before approving
  - Security validation checklist
  - Common patterns and red flags
  - Example approval/rejection comments

---

## 🏗️ Architecture

### System Flow

```
User reports VPC SC error → Audit log JSON
            ↓
Creates GitHub issue in vpc-sc-automation
            ↓
audit-log-to-rules.yml workflow triggers
            ↓
audit_log_to_rules.py:
  • Parses audit log
  • Determines perimeter ownership
  • Auto-detects INGRESS/EGRESS/BOTH
  • Checks TLM ID requirement
            ↓
If TLM needed: Request in comment, wait for reply
            ↓
generate_cross_repo_prs.py:
  • Generates HCL rules
  • Creates PRs in target perimeter repos (one per perim)
  • Each PR: append-only changes
            ↓
Network Security Team reviews & approves
            ↓
Rules deployed (Terraform apply)
            ↓
✅ User can now access resource
```

### Key Scripts

| Script | Purpose |
|--------|---------|
| **audit_log_to_rules.py** | Parse audit log, auto-detect direction, validate TLM |
| **generate_cross_repo_prs.py** | Create PRs in target repos with appended rules |
| **audit-log-to-rules.yml** | GitHub Actions workflow orchestrating everything |

### Configuration

| File | Purpose |
|------|---------|
| **router.yml** | Maps perimeter names to repo URLs and file paths |
| **vpc_sc_project_cache.json** | Lookup table: project_number → perimeter_name |

---

## 🤖 How It Works

### 1. Audit Log Parsing
Extracts from Cloud Audit Log:
- `serviceName` → GCP service
- `methodName` → Specific operation
- `callerIp` → Source IP
- `servicePerimeterName` → Destination perimeter
- `ingressViolations` / `egressViolations` → Violation type
- `principalEmail` → Service account
- Project numbers in targets

### 2. Perimeter Ownership Detection
Looks up in:
1. Project cache (project_num → perimeter)
2. Router.yml configuration
Returns: internal (yours) or external (not yours)

### 3. Direction Auto-Detection

| Source | Destination | Direction |
|--------|-------------|-----------|
| Internal, same perim | Internal, same perim | **SKIP** (already allowed) |
| Internal, diff perim | Internal, diff perim | **BOTH** |
| External | Internal | **INGRESS** |
| Internal | External | **EGRESS** |
| External | External | **SKIP** (out of scope) |

### 4. TLM ID Requirement Check

| Scenario | TLM Needed |
|----------|-----------|
| Public IP + INGRESS | ✅ YES |
| Private IP + INGRESS | ❌ NO |
| Any + EGRESS to external | ✅ YES |
| Internal-only | ❌ NO |

### 5. HCL Generation
Generates Terraform with:
- INGRESS/EGRESS policies (appended to existing)
- Access levels for public IPs (appended)
- Justification comments

### 6. Append-Only Changes
When creating PRs:
- Existing rules: **preserved**
- New rules: **appended**
- Existing access levels: **preserved**
- New access levels: **appended**
- **Zero risk** of overwriting existing configs

---

## 📋 Configuration

### router.yml
Maps perimeters to their repositories:

```yaml
perimeters:
  test-perim-a:
    repo: your-org/test-perim-a-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 123456789

  test-perim-b:
    repo: your-org/test-perim-b-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 987654321
```

### vpc_sc_project_cache.json
Updated daily, maps project numbers to perimeters:

```json
{
  "last_updated": "2024-01-15T02:00:00Z",
  "projects": {
    "1111111111": "test-perim-a",
    "2222222222": "test-perim-b"
  }
}
```

---

## 🎯 Workflow

### Create GitHub Issue
1. Click **Issues** → **New Issue**
2. Select **"VPC SC Audit Log - Auto-Generate Rules"**
3. Paste your audit log JSON
4. (Optional) Add context
5. Submit

### Automated Processing
Workflow automatically:
1. Extracts audit log from issue
2. Parses with `audit_log_to_rules.py`
3. Checks TLM ID requirement
   - If needed: Asks via comment, waits for reply
   - If not: Proceeds immediately
4. Generates HCL rules
5. Creates PRs in target repos (one per perimeter)
6. Posts summary with PR links

### Network Security Review
Each PR:
- Shows **only appended content**
- Includes **clear summary**
- Has **justification**
- Lists **TLM ID** (if applicable)

Team reviews and:
1. Validates source/destination/service/method
2. Approves if checks pass
3. Merges (rules go live immediately)

---

## 📚 Examples

### Example 1: On-Premises to GCP

**You:**
- Run BigQuery query from on-prem network
- Get permission denied error

**System:**
- Detects: Public IP (203.0.113.55) → INGRESS → need TLM ID
- Asks for TLM ID
- Creates access level + INGRESS rule
- Creates 1 PR to test-perim-a

**Result:**
- Network security approves
- PR merges
- You can now query

### Example 2: Cross-Perimeter Access

**You:**
- Project in test-perim-a tries to access BigQuery in test-perim-b
- Get permission denied

**System:**
- Detects: Internal to internal → BOTH (EGRESS + INGRESS)
- No TLM needed (both internal)
- Creates 2 PRs (one per perim)

**Result:**
- Network security approves both
- Both PRs merge
- Cross-perimeter access works

---

## 🛠️ Setup

**👉 Start with [SETUP_CHECKLIST.md](./SETUP_CHECKLIST.md) for step-by-step instructions!**

### Prerequisites
- GitHub repo with this code
- `router.yml` configured with your perimeters
- Project cache (auto-generated or synced from GCP)
- `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON` secret (for production GCP API sync)
- `CROSS_REPO_TOKEN` secret (for creating PRs in perimeter repos)

### Quick Configuration Steps

#### 1. Configure router.yml
Create `router.yml` mapping your perimeters to repositories:
```bash
# Edit router.yml with your perimeter repos
vim router.yml
```

#### 2. Generate Local Test Cache (Development)
For local testing, generate a test project cache:
```bash
python3 .github/scripts/update_project_cache_local.py
```

This creates test mappings (project_number → perimeter_name) in:
```
.github/scripts/vpc_sc_project_cache.json
```

#### 3. Set Up Production GCP Sync (Optional)
To keep cache in sync with actual GCP state:

**A. Add GitHub Secret:**
- Go to Settings → Secrets and variables → Actions
- Add `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON`
- Paste your GCP service account JSON key

**B. Create GCP Service Account:**
The service account needs these permissions:
- `accesscontextmanager.policies.get`
- `accesscontextmanager.servicePerimeters.list`

**C. Workflow Runs Automatically:**
```
.github/workflows/update-project-cache.yml
```
- Runs daily at 2 AM UTC
- Queries GCP Access Context Manager API
- Updates cache if perimeters changed
- Auto-commits to main branch

#### 4. Add GitHub Secrets for PR Creation
- `CROSS_REPO_TOKEN`: GitHub token for creating PRs
  - Must have `repo` and `workflow` scopes
  - Used to create PRs in target perimeter repos

#### 5. Enable Workflows
- Go to Actions → All workflows
- Ensure both workflows are enabled:
  - `audit-log-to-rules.yml` (processes issues)
  - `update-project-cache.yml` (syncs cache daily)

---

## 🚨 Troubleshooting

| Problem | Solution |
|---------|----------|
| Issue not processing | Check if audit log JSON is valid and contains `"protoPayload"` |
| TLM ID request missed | Reply to the bot comment with `TLM-XXXXX` |
| "Project not found in cache" | Run: `python3 .github/scripts/update_project_cache_local.py` |
| Cache outdated in production | Wait for daily sync, or manually trigger: `update-project-cache.yml` workflow |
| Perimeter not in router.yml | Add the perimeter to `router.yml` and update cache |
| Wrong rules generated | Verify audit log is complete, check it against what's in PR |
| GCP sync fails | Verify `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON` secret is valid |

---

## 📖 More Documentation

### For Everyone
- **[AUDIT_LOG_GUIDE.md](./AUDIT_LOG_GUIDE.md)** - Complete guide for requestors
  - How to find audit logs
  - What happens after you submit
  - Troubleshooting

### For Network Security Operations
- **[NETSEC_REVIEW_GUIDE.md](./NETSEC_REVIEW_GUIDE.md)** - Complete guide for network security ops
  - What to check before approving
  - Security checklist
  - Red flags
  - Example comments

### For Operators & Developers
- **[ROUTING_GUIDE.md](./ROUTING_GUIDE.md)** - How the system routes rules
  - router.yml structure
  - Perimeter → repo → files mapping
  - Routing logic explained

- **[PROJECT_CACHE_GUIDE.md](./PROJECT_CACHE_GUIDE.md)** - Project cache mechanism
  - Local testing cache (development)
  - Production GCP API sync (daily automated)
  - Troubleshooting cache issues

- **[TESTING_GUIDE.md](./TESTING_GUIDE.md)** - Testing strategy
  - Unit tests (Level 1)
  - Integration tests (Level 2)
  - Workflow simulation (Level 3)
  - Staging tests (Level 4)

- **[IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)** - Key implementation details
  - How to test the system
  - How routing works
  - Real-world examples

### Migration
- **[MIGRATION_FROM_OLD_SYSTEM.md](./MIGRATION_FROM_OLD_SYSTEM.md)** - Migration guide
  - What changed from old form-based system
  - Files removed
  - Migration path for existing requests

---

## 🔗 Resources

- [VPC Service Controls Docs](https://cloud.google.com/vpc-service-controls/docs)
- [Cloud Audit Logs](https://cloud.google.com/logging/docs/audit)
- [Access Levels](https://cloud.google.com/vpc-service-controls/docs/access-levels)

---

**Last Updated:** January 2024
**Version:** 1.0