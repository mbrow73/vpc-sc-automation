# Network Security Operations - VPC SC Rule Review Guide

> **For:** Network Security Operations team reviewing automatically-generated VPC SC rule PRs

## Overview

This guide explains how to review pull requests automatically generated from VPC Service Controls audit logs. The automation handles the tedious parsing and rule generation, allowing your team to focus on security validation.

---

## How the Automation Works

### The Flow

```
User reports VPC SC error (GitHub issue)
         ↓
System extracts audit log data
         ↓
System determines perimeter ownership
         ↓
System detects INGRESS/EGRESS/BOTH
         ↓
System validates TLM ID requirement
         ↓
System generates PRs (one per affected perimeter)
         ↓
YOUR TEAM REVIEWS & APPROVES
         ↓
Rules deployed (append-only, non-destructive)
```

### Advantages for Your Team

✅ **All rules are append-only** - No existing rules are modified or deleted
✅ **Automatic direction detection** - Reduced human error
✅ **Clear audit trail** - Each PR links back to the source issue and audit log
✅ **Consistent formatting** - All rules follow the same HCL structure
✅ **Built-in perimeter isolation** - Each PR affects only one perimeter
✅ **TLM ID validation** - Public IP + third-party access automatically flagged

---

## Reviewing a PR

### Step 1: Understand the Change

Each PR title will look like:
```
VPC SC rules for test-perim-a - storage.googleapis.com from 203.0.113.1
```

The PR body contains:
- **Perimeter:** Which perimeter will be modified
- **Direction:** INGRESS, EGRESS, or BOTH
- **Service:** GCP service (e.g., `bigquery.googleapis.com`)
- **Method:** Specific operation (e.g., `BigQueryStorage.CreateReadSession`)
- **Caller IP or Source:** Where the request is coming from
- **TLM ID:** If applicable

### Step 2: Check the Diff

The diff will show **only appended content** (new rules). Look for:

**terraform.auto.tfvars additions:**
```hcl
# New ingress rule appended to existing list
ingress_policies = [
  { ... existing rules ... },
  {
    # New rule added below
    from = {
      sources = {
        resources = ["projects/123456"]
        access_levels = []
      }
      identities = ["serviceAccount:deployer@project.iam.gserviceaccount.com"]
    }
    to = {
      resources = ["projects/999888777"]
      operations = {
        "storage.googleapis.com" = {
          methods = ["storage.objects.get"]
          permissions = []
        }
      }
    }
  }
]
```

**accesslevel.tf additions (if public IP):**
```hcl
# New access level module appended
module "vpc-service-controls-access-level_tlm-data-ops-01" {
  source  = "tfe. / /vpc-service-controls/google//modules/access_level"
  version = "0.0.4"
  policy  = var.policy
  name    = "tlm-data-ops-01"
  ip_subnetworks = ["203.0.113.0/24"]
}
```

### Step 3: Validate Security Requirements

Use this checklist:

#### Source Validation

- [ ] **If public IP source:**
  - ✅ TLM ID is present and valid format
  - ✅ IP address is in access level module
  - ✅ IP address matches audit log callerIp
  - ✅ IP is the actual source (not a NAT or proxy you don't control)

- [ ] **If private IP source:**
  - ✅ Source project is identified
  - ✅ Source project belongs to a perimeter you control
  - ✅ Service account is appropriate (not a generic/shared SA)

- [ ] **If external project source (cross-org):**
  - ✅ TLM ID is present (org policy compliance)
  - ✅ Project number is correct
  - ✅ Relationship with external org is approved

#### Destination Validation

- [ ] **Destination project is correct**
  - ✅ Project number matches what's in the rule
  - ✅ Project is the intended target
  - ✅ Project is in the perimeter being modified

#### Service & Method Validation

- [ ] **Service name is expected**
  - ✅ Is the GCP service that should be accessed
  - ✅ Service is commonly used (storage, bigquery, compute, etc.)

- [ ] **Method is specific (not wildcard `*`)**
  - ✅ Rule limits to specific operation (best practice)
  - ✅ Method makes sense (e.g., `storage.objects.get` for read-only)
  - ✅ Not overly permissive (e.g., not all BigQuery methods if only read needed)

#### Identity Validation

- [ ] **Service account exists and is identified**
  - ✅ Email format is correct
  - ✅ Project component is in allowed list
  - ✅ Not a generic or shared service account

#### Perimeter Validation

- [ ] **Perimeter exists and is known**
  - ✅ Perimeter name is in your router.yml
  - ✅ Only one perimeter affected per PR
  - ✅ If BOTH direction, verify both perimeters exist

---

## Security Review Questions

Ask yourself these questions for each PR:

### 1. **Do we trust this source?**

| Source Type | Ask | Example |
|------------|-----|---------|
| **Public IP** | Is this IP known and trusted? | Corporate network, partner office |
| **Private IP** | Is this from a perimeter we control? | Another internal GCP perimeter |
| **External Org** | Do we have an approved relationship? | Known vendor, partner, customer |

### 2. **Is the access minimal and appropriate?**

| Aspect | Ask | Red Flag |
|--------|-----|----------|
| **Service** | Is this the correct service? | Unexpected service (e.g., Compute when they asked for Storage) |
| **Method** | Does method match the need? | Wildcard `*` when specific methods available |
| **Scope** | Limited to necessary resources? | All projects instead of one |

### 3. **Is the TLM ID valid (if applicable)?**

| Scenario | Check |
|----------|-------|
| **Public IP + INGRESS** | ✅ TLM ID must be present |
| **EGRESS to external org** | ✅ TLM ID must be present |
| **Internal to internal** | ✅ TLM ID should be absent |

### 4. **Does the justification match the rule?**

- Does the business reason match what's in the rule?
- Is the context clear enough to understand the need?
- Any red flags in the explanation?

### 5. **Is this a one-time change or ongoing?**

- If one-time: Approve with understanding it might be removed later
- If ongoing: Ensure perimeter ownership is correct and sustainable

---

## Common Patterns You'll See

### Pattern 1: On-Premises to GCP (INGRESS)

**What it looks like:**
```
Caller IP: 203.0.113.0/24 (public)
Direction: INGRESS
Service: bigquery.googleapis.com
TLM ID: Present
```

**What to check:**
- ✅ TLM ID is provided
- ✅ Public IP range is correctly specified
- ✅ Destination project is internal
- ✅ Service and method are expected

**Approve if:** Trust the on-prem network, TLM ID is valid, method is appropriate

---

### Pattern 2: Cross-Perimeter Internal (BOTH)

**What it looks like:**
```
Source: test-perim-a (private IP)
Destination: test-perim-b (internal)
Direction: BOTH (EGRESS + INGRESS)
TLM ID: Not present (internal, not needed)
```

**What to check:**
- ✅ Both perimeters are yours
- ✅ Source and destination projects are identified
- ✅ Service/method matches the use case
- ✅ No TLM ID (correctly omitted for internal)

**Approve if:** Cross-perimeter relationship is approved, service is expected

---

### Pattern 3: GCP to External SaaS (EGRESS)

**What it looks like:**
```
Source: test-perim-a (internal)
Destination: projects/999888777 (external/third-party)
Direction: EGRESS
TLM ID: Present
```

**What to check:**
- ✅ TLM ID is provided
- ✅ External project is known (vendor, partner, customer)
- ✅ Service makes sense for external access (often storage, pubsub)
- ✅ Method is specific

**Approve if:** External relationship is known, TLM ID is valid, method is appropriate

---

## Red Flags 🚩

| Flag | Concern | Action |
|------|---------|--------|
| **Public IP without TLM ID** | Compliance violation | Request TLM ID before merge |
| **Wildcard methods (`*`)** | Overly permissive | Request specific methods |
| **Unexpected service** | May indicate error in audit log | Ask requester to verify |
| **Unknown source IP** | Potential security risk | Request verification/documentation |
| **All projects as destination** | Too broad | Request specific project numbers |
| **Cross-org access without TLM** | Compliance issue | Request TLM ID and verification |
| **Generic service account** | Shared credential risk | Request more specific SA |
| **Same perimeter source & dest** | Waste of rules | Inform it shouldn't be needed |

---

## Approval Workflow

### For Straightforward PRs

1. ✅ Verify checklist items above
2. ✅ Approve with comment: "LGTM - approving for deployment"
3. ✅ Merge (usually auto-merges immediately)

### For PRs Needing Clarification

1. 🤔 Comment with specific questions
2. ⏳ Give requester 24-48 hours to respond
3. 👀 Re-review if they provide additional context
4. ✅ Approve and merge when satisfied

### For PRs You Need to Reject

1. ❌ Comment explaining why (missing TLM, overly broad, unexpected source, etc.)
2. 📝 Provide clear instructions on what needs to change
3. 🔗 Link to this guide if helpful
4. Close the PR (requester can reopen with fixes)

---

## Useful Queries for Verification

### Verify the source IP is legitimate

```bash
# Search audit logs for recent activity from this IP
gcloud logging read 'protoPayload.requestMetadata.callerIp="203.0.113.1"' \
  --format=json --limit=5
```

### Verify the source project

```bash
# Check if project exists
gcloud projects describe 123456789
```

### Verify the destination is in the right perimeter

```bash
# List all projects in a perimeter
gcloud access-context-manager perimeters describe test-perim-a \
  --policy=YOUR_POLICY_ID --format=json
```

### Verify the service supports method restrictions

```bash
# List supported services with method-level restrictions
# These are: bigquery, storage, compute, logging, iam, etc.
```

---

## After Merge

### What Happens Next

1. **Immediately:** Terraform applies the new rules
2. **Within seconds:** Rules are live in the perimeter
3. **Users can retry:** Their access now works

### Monitoring

Keep an eye on:
- **Audit logs** for any unexpected behavior from new rules
- **Perimeter metrics** for traffic patterns
- **Issues** for any complaints about the new rules

If something looks wrong:
1. Communicate with requester
2. Remove the rule (revert the PR)
3. Request more specific rule details

---

## Tips for Efficient Reviews

1. **Batch similar reviews** - If you have multiple PRs, review together
2. **Use comments wisely** - Approve with suggestions vs. request changes
3. **Trust the automation** - The system handles parsing and formatting correctly
4. **Focus on security** - Not on format or structure (automation handles that)
5. **Document decisions** - Leave comments explaining why you approved/rejected
6. **Set expectations** - Let requesters know typical review time (e.g., 24-48 hours)

---

## Troubleshooting Common Issues

### "The rule looks wrong but I can't figure out why"

**Try:**
1. Check the source audit log (linked in the PR)
2. Verify the audit log format is complete
3. Compare with the PR content
4. Ask the requester to verify the audit log

### "The requester disappeared and left a PR hanging"

**Options:**
1. Auto-reject after 1 week of no response
2. Reach out to their manager
3. Close with comment explaining timeout

### "Multiple PRs for the same rule"

**Why:** If a rule affects both perimeters (BOTH direction), you get 2 PRs
**Action:** Approve both - they're meant to be merged together

---

## Escalation Paths

**If you need help:**
- 🔗 Security questions: Contact your Chief Information Security Officer (CISO)
- 📋 Policy questions: Contact your org's VPC SC policy owner
- 🛠️ Technical questions: Contact the platform engineering team
- 📧 Workflow questions: Reach out to the VPC SC automation maintainer

---

## Example Review Comments

### Approving a Standard Request

```
✅ Approved - Standard INGRESS rule from known corporate network.

Verified:
- TLM ID valid (TLM-DATA-OPS-01)
- Source IP matches CalOps corporate gateway
- Service (BigQuery) and method (CreateSession) match audit log
- Destination project confirmed as data-warehouse-prod
- BigQuery access for nightly ETL is approved use case

Ready to merge.
```

### Requesting Clarification

```
⏸️ Needs clarification before approval

Questions:
1. The audit log shows IP 203.0.113.0/24 but PR has 203.0.113.1/32 - which is correct?
2. Is this a one-time access or permanent? Rule looks permanent.
3. Can the method be more specific than `*`? (e.g., `storage.objects.get` instead of all storage methods)

Please reply with clarifications and I'll approve.
```

### Rejecting a Request

```
❌ Cannot approve - Missing required TLM ID

This rule uses a public IP (203.0.113.1) for INGRESS access, which requires a TLM ID for compliance.

Please:
1. Provide a valid TLM ID (ask your org's TLM coordinator)
2. Reply in this PR with the TLM ID
3. The automation will re-process and regenerate the rule

Once TLM ID is provided, reopen this issue and I'll review again.
```

---

## Glossary

| Term | Meaning |
|------|---------|
| **VPC SC** | VPC Service Controls (Google Cloud's perimeter-based access control) |
| **Perimeter** | Security boundary that isolates and controls access to GCP resources |
| **Ingress** | Traffic entering a perimeter (from outside to inside) |
| **Egress** | Traffic leaving a perimeter (from inside to outside) |
| **TLM ID** | Third-party Licensing/Management ID, tracking identifier for external access |
| **Access Level** | Named conditions (e.g., IP ranges) that define who can access resources |
| **CIDR** | Classless Inter-Domain Routing notation for IP ranges (e.g., 203.0.113.0/24) |
| **Audit Log** | GCP's record of all API calls, used to detect VPC SC violations |

---

## Questions?

- 📚 See [AUDIT_LOG_GUIDE.md](./AUDIT_LOG_GUIDE.md) for requestor documentation
- 🔗 See [VPC SC Troubleshooting](https://cloud.google.com/vpc-service-controls/docs/troubleshooting)
- 📧 Reach out to your VPC SC automation team
