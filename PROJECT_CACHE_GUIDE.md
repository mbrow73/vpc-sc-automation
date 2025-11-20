# Project Cache Guide

## Overview

The **project cache** is a critical component that maps GCP project numbers to VPC Service Control perimeter names. This enables the system to determine if a project is internal (yours) or external (third-party).

```
Project Number → Perimeter Name
1111111111    → test-perim-a
2222222222    → test-perim-b
3333333333    → (not in your perimeters - external)
```

The cache is stored as JSON:

```json
{
  "last_updated": "2024-01-15T02:00:00Z",
  "cache_source": "gcp_api",
  "projects": {
    "1111111111": "test-perim-a",
    "2222222222": "test-perim-b"
  }
}
```

## Two Approaches

### 1. Local Testing (Development)

For development and testing, use **static test cache**:

```bash
python3 .github/scripts/update_project_cache_local.py
```

This generates test data with hard-coded project numbers for each perimeter in `router.yml`:

```json
{
  "projects": {
    "1111111111": "test-perim-a",
    "1111111112": "test-perim-a",
    "2222222222": "test-perim-b",
    "2222222223": "test-perim-b"
  }
}
```

**When to use:**
- ✅ Local development and testing
- ✅ Unit/integration test environments
- ✅ Before setting up GCP API sync
- ✅ Testing without GCP credentials

**File location:**
```
.github/scripts/vpc_sc_project_cache.json
```

---

### 2. Production GCP Sync

For production, **sync automatically from GCP API**:

The system queries actual VPC SC perimeters in GCP and builds the cache from real data.

#### How It Works

```
┌─────────────────────────────┐
│  GitHub Actions Workflow    │
│  (Scheduled daily @ 2 AM)   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ sync_project_cache_from_gcp │
│  Reads router.yml          │
│  For each perimeter:       │
│  - Get policy_id           │
│  - Query GCP API           │
│  - Extract projects        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Update vpc_sc_project_cache │
│ Write to JSON file          │
│ Git commit & push           │
└─────────────────────────────┘
```

#### Setup

**Step 1: Create GCP Service Account**

The service account needs these permissions:
- `roles/accesscontextmanager.policyEditor` OR
- `accesscontextmanager.policies.get`
- `accesscontextmanager.servicePerimeters.list`

```bash
# Create service account
gcloud iam service-accounts create vpc-sc-automation \
  --display-name "VPC SC Automation Cache Sync"

# Grant Access Context Manager read permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member serviceAccount:vpc-sc-automation@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/accesscontextmanager.policyEditor
```

**Step 2: Create JSON Key**

```bash
gcloud iam service-accounts keys create key.json \
  --iam-account vpc-sc-automation@PROJECT_ID.iam.gserviceaccount.com
```

**Step 3: Add GitHub Secret**

1. Go to repository Settings
2. Secrets and variables → Actions
3. Create new secret: `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON`
4. Paste the contents of `key.json`

**Step 4: Verify Workflow**

The workflow runs automatically:
```
.github/workflows/update-project-cache.yml
```

- Triggered: Daily at 2 AM UTC
- Manually: Actions → Update Project Cache → Run workflow

#### What Gets Cached

For each perimeter in `router.yml`, the script:

1. Reads the `policy_id`
2. Queries GCP Access Context Manager API
3. Extracts all projects from that perimeter
4. Maps project_number → perimeter_name

**Example:**

If `router.yml` has:
```yaml
perimeters:
  test-perim-a:
    policy_id: 123456789
  test-perim-b:
    policy_id: 987654321
```

The GCP API returns:
- Policy 123456789 contains projects: [1111111111, 1111111112, 1111111113]
- Policy 987654321 contains projects: [2222222222, 2222222223]

Result in cache:
```json
{
  "projects": {
    "1111111111": "test-perim-a",
    "1111111112": "test-perim-a",
    "1111111113": "test-perim-a",
    "2222222222": "test-perim-b",
    "2222222223": "test-perim-b"
  }
}
```

---

## File Usage

### During Audit Log Processing

When `audit_log_to_rules.py` runs:

```python
# 1. Load cache
cache = load_project_cache('vpc_sc_project_cache.json')

# 2. Extract projects from audit log
source_project = extract(audit_log, 'source_project')  # e.g., "1111111111"
dest_project = extract(audit_log, 'dest_project')      # e.g., "2222222222"

# 3. Lookup perimeters
src_perim = cache.get(source_project)  # "test-perim-a"
dst_perim = cache.get(dest_project)    # "test-perim-b"

# 4. Determine if internal or external
if src_perim:
    source_is_internal = True
else:
    source_is_internal = False
```

### Cache Miss Handling

If a project is not in the cache:

```python
if project_num not in cache:
    # Project is external (not in any of your perimeters)
    perimeter = None
```

This is intentional - projects without cache entries are treated as external.

---

## Troubleshooting

### Cache File Not Found

```
⚠️  Project cache not found: .github/scripts/vpc_sc_project_cache.json
   Run: python3 .github/scripts/update_project_cache_local.py
```

**Solution:**
```bash
cd vpc-sc-automation
python3 .github/scripts/update_project_cache_local.py
```

### Cache Outdated (Development)

Update the test cache:
```bash
python3 .github/scripts/update_project_cache_local.py
```

### Cache Outdated (Production)

Manually trigger the workflow:

```bash
gh workflow run update-project-cache.yml \
  --repo your-org/vpc-sc-automation
```

Or wait for the next daily sync at 2 AM UTC.

### Project Not In Cache

If audit log references project `9999999999` but it's not in cache:

1. **Is it in your perimeter?**
   - Check your GCP console: VPC Service Controls
   - Find the perimeter, view associated projects
   - If yes: Sync the cache (see above)

2. **Is it external?**
   - If not in your perimeters: This is correct behavior
   - System treats it as external
   - Rules will be generated accordingly

### GCP Sync Fails

Check workflow logs:
```bash
gh run list --repo your-org/vpc-sc-automation --workflow update-project-cache.yml
gh run view RUN_ID --log
```

Common errors:

| Error | Solution |
|-------|----------|
| `Credential error` | Verify `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON` secret is valid |
| `Policy not found` | Verify policy_id in router.yml is correct (numeric, not string) |
| `Permission denied` | Verify service account has required roles |

---

## File Locations

```
vpc-sc-automation/
├── router.yml                                    # Perimeter → repo mapping
├── .github/
│   ├── scripts/
│   │   ├── vpc_sc_project_cache.json            # Cache (generated)
│   │   ├── update_project_cache_local.py        # Generate test cache
│   │   ├── sync_project_cache_from_gcp.py       # Sync from GCP API
│   │   ├── audit_log_to_rules.py                # Uses cache
│   │   └── generate_cross_repo_prs.py           # Uses router.yml (indirectly via audit_log_to_rules)
│   └── workflows/
│       ├── audit-log-to-rules.yml               # Main workflow
│       └── update-project-cache.yml             # Daily cache sync
└── (other files)
```

---

## Workflow

```
1. User submits audit log via GitHub issue
                 ↓
2. audit-log-to-rules.yml workflow triggers
                 ↓
3. audit_log_to_rules.py:
   - Loads cache from vpc_sc_project_cache.json
   - Looks up projects to determine ownership
   - Generates rules
                 ↓
4. generate_cross_repo_prs.py:
   - Creates PRs in target repos
                 ↓
5. (Separately) Daily at 2 AM UTC:
   - update-project-cache.yml triggers
   - Syncs cache from GCP API
   - Commits if changed
```

---

## Best Practices

### Development

1. Start with local test cache:
   ```bash
   python3 .github/scripts/update_project_cache_local.py
   ```

2. Test with mock audit logs

3. Once confident, move to production setup

### Production

1. **Set up GCP service account** with minimal permissions

2. **Enable daily sync workflow** for automatic updates

3. **Monitor the workflow** for failures:
   ```bash
   gh run list --repo your-org/vpc-sc-automation \
     --workflow update-project-cache.yml
   ```

4. **Verify cache periodically**:
   ```bash
   git log --oneline .github/scripts/vpc_sc_project_cache.json
   ```

5. **When adding new perimeters**:
   - Add to router.yml
   - Sync cache immediately
   - Don't wait for daily scheduled run

---

## FAQ

**Q: Can I manually edit vpc_sc_project_cache.json?**
A: Not recommended. In production, changes will be overwritten by the daily sync. For testing, regenerate it with `update_project_cache_local.py`.

**Q: How often is the cache updated?**
A: Development: manually when you run the script. Production: daily at 2 AM UTC (configurable in workflow).

**Q: What if I add a new perimeter?**
A: Update router.yml, then sync the cache to include projects from the new perimeter.

**Q: Does the cache need to be committed to git?**
A: Yes. It should be in version control so all contributors have it.

**Q: What if GCP sync fails for a day?**
A: Cache keeps old values. Next sync (24 hours later) will update. New perimeters won't be recognized until sync succeeds.

**Q: Can I use this with multiple GCP projects?**
A: Yes, if you have service accounts in each GCP project, each can have its own cache. For simplicity, use one service account with access to all projects containing VPC SC policies.

---

## Next Steps

- **Development**: Run `python3 .github/scripts/update_project_cache_local.py`
- **Production**: Follow GCP setup steps above
- **Testing**: Create test audit logs with known project numbers
- **Monitoring**: Check workflow logs for cache update status
