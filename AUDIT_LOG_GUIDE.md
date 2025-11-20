# VPC Service Controls - Audit Log-Driven Rule Automation

> **TL;DR**: When you get a VPC SC permission error, paste the audit log and automation creates the rules for you.

## Overview

This system lets you request VPC Service Controls rule changes **without knowing VPC SC terminology**. Just:

1. Get the audit log when you hit a VPC SC error
2. Paste it in a GitHub issue
3. System auto-detects direction (INGRESS/EGRESS), perimeters, services, and methods
4. Requests TLM ID only if needed
5. Creates pull requests for network security team to review

No dropdowns. No guessing. No VPC SC knowledge required.

---

## Part 1: Getting Your Audit Log

### Scenario: You get a VPC SC permission error

You're running a query, deploying code, or accessing a resource and get an error like:

```
PERMISSION_DENIED: Request is prohibited by organization's policy.
vpcServiceControlsUniqueIdentifier: 1A2B3C4D-5E6F-7G8H-9I0J-K1L2M3N4O5P6
```

### Step-by-Step: Find the Audit Log

#### Method 1: Google Cloud Console (Recommended)

1. Go to **Cloud Console** → **Logging** → **Logs Explorer**
   - URL: `https://console.cloud.google.com/logs/query`

2. In the query box, paste one of these filters:

   **For recent errors (last hour):**
   ```
   severity="ERROR"
   protoPayload.status.code=7
   ```

   **For a specific perimeter:**
   ```
   severity="ERROR"
   protoPayload.metadata.securityPolicyInfo.servicePerimeterName=~"prod-perimeter"
   ```

   **For a specific service:**
   ```
   severity="ERROR"
   protoPayload.serviceName="storage.googleapis.com"
   ```

3. Click **Run Query**

4. Look for the error entry that matches your error:
   - Check the timestamp
   - Look for your service name (e.g., `storage.googleapis.com`)
   - Look for your method (e.g., `storage.objects.get`)

5. Click on the log entry to expand it

6. Click **Expand All** (or the arrow icon) to see the full JSON

7. **Copy the entire JSON** (not just the error message)
   - Select all the JSON
   - Copy it

#### Method 2: Using gcloud CLI

```bash
# List recent VPC SC violations for a project
gcloud logging read \
  'severity="ERROR" AND protoPayload.status.code=7' \
  --project=YOUR_PROJECT_ID \
  --limit=10 \
  --format=json | head -100
```

---

## Part 2: Understanding the Audit Log

Here's what a typical VPC SC violation audit log looks like:

```json
{
  "protoPayload": {
    "status": {
      "code": 7,
      "message": "PERMISSION_DENIED: Request is prohibited by organization's policy."
    },
    "serviceName": "storage.googleapis.com",
    "methodName": "storage.objects.get",
    "authenticationInfo": {
      "principalEmail": "deployer-sa@my-project.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "203.0.113.55",
      "callerNetwork": "//compute.googleapis.com/projects/123456789/global/networks/default"
    },
    "resourceName": "projects/_/buckets/secure-bucket/objects/data.csv"
  },
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "securityPolicyInfo": {
      "servicePerimeterName": "accessPolicies/123/servicePerimeters/prod-data-perimeter"
    },
    "ingressViolations": [
      {
        "targetResource": "projects/999888777"
      }
    ]
  },
  "resource": {
    "type": "gcs_bucket",
    "labels": {
      "project_id": "my-project-123"
    }
  },
  "timestamp": "2024-01-15T10:00:00.123456Z"
}
```

**Key fields the system extracts:**

| Field | What it means | Example |
|-------|---------------|---------|
| `protoPayload.serviceName` | Which GCP service you tried to access | `storage.googleapis.com` |
| `protoPayload.methodName` | Which operation failed | `storage.objects.get` |
| `protoPayload.requestMetadata.callerIp` | Where the request came from | `203.0.113.55` (public) or `10.0.0.5` (private) |
| `metadata.securityPolicyInfo.servicePerimeterName` | Which perimeter blocked it | `prod-data-perimeter` |
| `metadata.ingressViolations[0].targetResource` | What resource was accessed | `projects/999888777` |
| `protoPayload.authenticationInfo.principalEmail` | Who made the request | `deployer-sa@my-project.iam.gserviceaccount.com` |

---

## Part 3: Submitting Your Request

### Create a GitHub Issue

1. Go to the **vpc-sc-automation** repository
2. Click **Issues** → **New Issue**
3. Select **"VPC SC Audit Log - Auto-Generate Rules"**
4. **Paste the full JSON** audit log in the "Cloud Audit Log JSON" field
5. (Optional) Add context about what you're trying to do
6. Click **Submit**

---

## Part 4: What Happens Automatically

### The System Detects:

**Direction (INGRESS vs EGRESS):**
- If coming FROM outside TO inside: **INGRESS**
- If going FROM inside TO outside: **EGRESS**
- If crossing between two internal perimeters: **BOTH**

**TLM ID Requirement:**
- If **public IP** (non-RFC-1918) + INGRESS: ✅ TLM required
- If EGRESS to **external organization**: ✅ TLM required
- If internal to internal: ❌ TLM not needed
- If private IP (10.x, 172.16-31.x, 192.168.x): ❌ TLM not needed

**Perimeter Ownership:**
- Checks project cache to determine which perimeters you control
- Auto-creates rules in affected perimeters

### If TLM ID Needed

The bot will comment on your issue:

```
⚠️ TLM ID Required

This request needs a TLM ID (it involves third-party access or public IPs).

Reason: Ingress from public IP requires TLM ID

Please reply with: `TLM-XXXXX`
```

Just reply with your TLM ID like: `TLM-18273645`

The automation will then proceed automatically.

### Rules are Generated

The system creates pull requests for each affected perimeter:

```
📋 PR: test-perim-a
├─ Direction: INGRESS
├─ Service: storage.googleapis.com
├─ Method: storage.objects.get
├─ Added rules to terraform.auto.tfvars
└─ Added access level to accesslevel.tf (if public IP)

📋 PR: test-perim-b
├─ Direction: EGRESS
├─ Service: storage.googleapis.com
├─ Method: storage.objects.get
└─ Added rules to terraform.auto.tfvars
```

---

## Part 5: Network Security Team Review

Each PR includes:

✅ **Clear summary** of what access is being granted
✅ **Diff showing only added content** (append-only, nothing deleted)
✅ **Service name and method** that will be allowed
✅ **Caller IP or project** that will have access
✅ **Justification** from the issue context
✅ **TLM ID** (if applicable)

Network security team reviews and approves. Once merged, rules are live immediately.

---

## Examples

### Example 1: On-Premises to GCP (Public IP)

**Error:** Your on-prem DataOps team can't run BigQuery jobs against a GCP project

**Audit Log shows:**
- `callerIp`: 203.0.113.0/24 (your corporate network)
- `servicePerimeterName`: test-perim-a
- `serviceName`: bigquery.googleapis.com
- `methodName`: google.cloud.bigquery.v2.JobService.InsertJob
- `ingressViolations`: projects/123456789

**System determines:**
- ✅ Public IP detected → TLM ID required
- ✅ INGRESS only (not from any perimeter we control)
- ✅ Need to add 1 rule to test-perim-a

**Action:**
- Bot asks for TLM ID
- You provide: `TLM-DATA-OPS-01`
- Bot creates access level with 203.0.113.0/24
- Bot creates 1 INGRESS rule in test-perim-a
- Network security reviews and merges

---

### Example 2: Cross-Perimeter (Both Internal)

**Error:** Project in test-perim-a can't access bucket in test-perim-b

**Audit Log shows:**
- `callerIp`: 10.128.0.50 (private, from test-perim-a)
- `servicePerimeterName`: test-perim-b
- `serviceName`: storage.googleapis.com
- `methodName`: storage.objects.get
- `ingressViolations`: projects/999888777 (in test-perim-b)

**System determines:**
- ✅ Private IP (no TLM needed)
- ✅ BOTH: EGRESS from test-perim-a + INGRESS to test-perim-b
- ✅ Need to add rules to 2 perimeters

**Action:**
- Bot creates 2 PRs (one per perimeter)
- Network security reviews both
- Both merged simultaneously
- Rules take effect immediately

---

### Example 3: GCP to External SaaS (Third-Party)

**Error:** Your application can't reach a third-party SaaS data warehouse

**Audit Log shows:**
- `callerIp`: 10.1.0.10 (private, from your perimeter)
- `servicePerimeterName`: test-perim-a
- `serviceName`: storage.googleapis.com (or other)
- `egressViolations`: projects/123456789 (third-party, not in your perimeters)

**System determines:**
- ✅ Destination is external → TLM ID required
- ✅ EGRESS only (from test-perim-a)
- ✅ Need 1 rule in test-perim-a

**Action:**
- Bot asks for TLM ID
- You provide: `TLM-SAAS-VENDOR-001`
- Bot creates 1 EGRESS rule
- Network security reviews and merges

---

## Troubleshooting

### "I can't find my audit log"

**Try:**
1. Make sure you're looking in the right project (where the resource is, not where the request came from)
2. Check the timestamp - was the error recent?
3. Use a broader filter: `severity="ERROR" AND protoPayload.status.code=7`
4. Look for your service name (e.g., `storage.googleapis.com`)

### "The JSON looks truncated"

**Try:**
1. Click **Expand All** button in Cloud Logging
2. Click the **View as Raw JSON** button
3. Copy the entire output
4. Make sure you're not copying just the error message

### "Automation says TLM ID required but I'm not sure what it is"

**Ask:**
- Your network security team
- Your organization's identity management team
- Check if you have a TLM ID format standard (e.g., TLM-12345 or TLM-TEAM-001)

### "I'm stuck waiting for approval"

**Reach out:**
- Post in the GitHub issue with `@network-security-team`
- Mention the business urgency
- Network security team will prioritize

---

## FAQ

**Q: Do I need to know VPC SC terminology?**
A: No. Just paste the audit log and let the system figure it out.

**Q: What if my request needs both INGRESS and EGRESS?**
A: The system auto-detects and creates both. You get one issue but two PRs (one per perimeter).

**Q: Can I request changes to multiple perimeters at once?**
A: Yes! If your request affects multiple perimeters, you'll get multiple PRs automatically.

**Q: What if I make a mistake in the audit log?**
A: Just close the issue and create a new one with the correct audit log. No harm done.

**Q: How long until the rules are live?**
A: Once network security approves and merges the PR, rules are live in seconds.

**Q: Can the rules be reverted?**
A: Yes. Each PR is isolated to one rule addition. Network security can revert by removing the rule block.

**Q: What's a TLM ID?**
A: A tracking identifier for third-party access. Required for security/compliance when accessing from outside your organization. Ask your security team for your format.

---

## Related Documentation

- [VPC Service Controls Overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Service Perimeters](https://cloud.google.com/vpc-service-controls/docs/service-perimeters)
- [Access Levels](https://cloud.google.com/vpc-service-controls/docs/access-levels)
- [Troubleshooting VPC SC](https://cloud.google.com/vpc-service-controls/docs/troubleshooting)
