# VPC SC Automation Setup Checklist

Complete this checklist to set up the VPC SC automation system in your environment.

---

## Phase 1: Foundation Setup (Required)

### Step 1: Router Configuration
- [ ] Open `router.yml`
- [ ] List all your VPC SC perimeters
- [ ] For each perimeter:
  - [ ] Find the target GitHub repository (`your-org/perimeter-config`)
  - [ ] Verify the repository exists and is accessible
  - [ ] Find the terraform variables file (`terraform.auto.tfvars`)
  - [ ] Find the access level file (`accesslevel.tf`)
  - [ ] Get the VPC SC policy ID (numeric ID from Cloud Console)
  - [ ] Update router.yml with this information

**Example:**
```yaml
perimeters:
  prod-perimeter:
    repo: your-org/prod-perimeter-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 123456789
```

- [ ] Validate router.yml syntax
  ```bash
  python3 -c "import yaml; yaml.safe_load(open('router.yml')); print('✅ Valid')"
  ```

- [ ] Test repository access
  ```bash
  for perim in $(yq '.perimeters | keys[]' router.yml); do
    repo=$(yq ".perimeters.$perim.repo" router.yml)
    git ls-remote $repo > /dev/null && echo "✅ $repo" || echo "❌ $repo"
  done
  ```

### Step 2: Project Cache Setup (Local Testing)
- [ ] Generate local test cache
  ```bash
  python3 .github/scripts/update_project_cache_local.py
  ```

- [ ] Verify cache file was created
  ```bash
  ls -la .github/scripts/vpc_sc_project_cache.json
  ```

- [ ] Review cache contents
  ```bash
  cat .github/scripts/vpc_sc_project_cache.json
  ```

### Step 3: GitHub Secrets for PR Creation
- [ ] Create or prepare GitHub token with these scopes:
  - [ ] `repo` (full repository control)
  - [ ] `workflow` (for modifying workflows)

- [ ] Add to repository secrets:
  - [ ] Go to Settings → Secrets and variables → Actions
  - [ ] Create new secret: `CROSS_REPO_TOKEN`
  - [ ] Paste the GitHub token

- [ ] Verify secret is accessible
  - [ ] Go to Settings → Secrets and variables → Actions
  - [ ] Confirm `CROSS_REPO_TOKEN` is listed

### Step 4: Enable Core Workflow
- [ ] Go to repository Actions
- [ ] Find `audit-log-to-rules.yml` workflow
- [ ] Verify it's enabled (not grayed out)
- [ ] Verify GitHub issue templates are available
  - [ ] Go to Issues → New Issue
  - [ ] Confirm you see "VPC SC Audit Log - Auto-Generate Rules" template

---

## Phase 2: Testing (Verify Foundation Works)

### Step 1: Local Script Testing
- [ ] Test audit_log_to_rules.py:
  ```bash
  # Create a test audit log
  python3 .github/scripts/audit_log_to_rules.py \
    --audit-log-json '{"protoPayload": {"serviceName": "bigquery.googleapis.com"}}' \
    --router-file router.yml \
    --output test_rules.json
  ```

- [ ] Verify output was created
  ```bash
  ls -la test_rules.json
  cat test_rules.json
  ```

- [ ] Test with complete example (see [TESTING_GUIDE.md](./TESTING_GUIDE.md))

### Step 2: Workflow Testing
- [ ] Create a test issue in the repository
  - [ ] Click Issues → New Issue
  - [ ] Select "VPC SC Audit Log - Auto-Generate Rules"
  - [ ] Paste a test audit log JSON
  - [ ] Submit

- [ ] Monitor workflow execution
  - [ ] Go to Actions → audit-log-to-rules.yml
  - [ ] Watch for the new run
  - [ ] Verify it completes successfully

- [ ] Check issue comments for feedback
  - [ ] If TLM required: workflow should ask for it
  - [ ] If no TLM required: workflow should proceed to PR creation

### Step 3: PR Verification
- [ ] Check target perimeter repositories for new PRs
  - [ ] Go to each perimeter repo
  - [ ] Look for new pull requests
  - [ ] Verify PR title includes issue number
  - [ ] Review PR diff for expected rules

- [ ] Verify append-only safety
  - [ ] Check that only new rules were added
  - [ ] Confirm existing content wasn't modified
  - [ ] Confirm only files specified in router.yml were touched

---

## Phase 3: Production Setup (Optional but Recommended)

### Step 1: Create GCP Service Account
- [ ] In GCP Console, go to IAM & Admin → Service Accounts
- [ ] Create new service account: `vpc-sc-automation`
- [ ] Grant permissions:
  - [ ] Role: `roles/accesscontextmanager.policyEditor` OR
  - [ ] Permissions: `accesscontextmanager.policies.get` + `accesscontextmanager.servicePerimeters.list`

- [ ] Create JSON key:
  ```bash
  gcloud iam service-accounts keys create key.json \
    --iam-account vpc-sc-automation@PROJECT_ID.iam.gserviceaccount.com
  ```

- [ ] Verify service account has correct permissions
  ```bash
  gcloud projects get-iam-policy PROJECT_ID \
    --flatten="bindings[].members" \
    --filter="bindings.members:vpc-sc-automation*"
  ```

### Step 2: Add GitHub Secret for GCP
- [ ] Go to repository Settings → Secrets and variables → Actions
- [ ] Create new secret: `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON`
- [ ] Paste contents of `key.json` from Step 1
- [ ] **Secure the JSON key file** - delete local copy after adding to GitHub

### Step 3: Enable Daily Cache Sync
- [ ] Go to Actions → All workflows
- [ ] Find `update-project-cache.yml`
- [ ] Verify it's enabled

- [ ] Test the workflow manually
  - [ ] Click on the workflow
  - [ ] Click "Run workflow" → "Run workflow" (using main branch)
  - [ ] Monitor execution
  - [ ] Verify cache was updated or confirmed in sync

- [ ] Verify workflow schedule
  - [ ] Workflow runs daily at 2 AM UTC
  - [ ] Check `.github/workflows/update-project-cache.yml` for schedule:
    ```yaml
    schedule:
      - cron: '0 2 * * *'  # 2 AM UTC every day
    ```

### Step 4: Monitor Workflow Health
- [ ] Set up workflow monitoring
  - [ ] Go to Actions
  - [ ] Enable branch protection rules if desired
  - [ ] Subscribe to workflow notifications

- [ ] Create a log check
  ```bash
  # Check last cache update
  git log --oneline .github/scripts/vpc_sc_project_cache.json | head -5

  # Verify cache content
  cat .github/scripts/vpc_sc_project_cache.json | jq '.last_updated'
  ```

---

## Phase 4: Communication & Documentation

### Step 1: Share with Users
- [ ] Share [AUDIT_LOG_GUIDE.md](./AUDIT_LOG_GUIDE.md) with requestors
  - [ ] Email or Slack the guide
  - [ ] Explain: "Just paste the audit log JSON, we handle the rest"

- [ ] Create internal documentation
  - [ ] Document your perimeter names in router.yml
  - [ ] Document what audit logs look like
  - [ ] Document approval process for network security team

### Step 2: Brief Network Security Team
- [ ] Share [NETSEC_REVIEW_GUIDE.md](./NETSEC_REVIEW_GUIDE.md)
  - [ ] Explain what they're reviewing
  - [ ] Explain approval workflow
  - [ ] Explain when to reject (red flags)

- [ ] Document approval checklist
  - [ ] Who approves
  - [ ] How quickly
  - [ ] Escalation path

### Step 3: Document for Your Team
- [ ] Create internal runbook
  - [ ] How to handle TLM ID requests
  - [ ] How to debug workflow failures
  - [ ] When to manually intervene

- [ ] Schedule training session
  - [ ] Walk through a test issue
  - [ ] Show how to review PRs
  - [ ] Answer questions

---

## Phase 5: Post-Deployment Verification

### Step 1: Real-World Test (Week 1)
- [ ] Submit first real audit log from actual VPC SC error
- [ ] Monitor workflow execution
- [ ] Verify network security team receives PR
- [ ] Verify PR is reviewed and approved
- [ ] Verify rules are applied (check Terraform apply)
- [ ] Verify user can now access resource

### Step 2: Ongoing Monitoring
- [ ] Check workflow runs weekly
  - [ ] No recent failures?
  - [ ] Cache updates are recent?
  - [ ] Workflows complete in reasonable time?

- [ ] Monitor for issues
  - [ ] Review failed runs
  - [ ] Check error messages
  - [ ] Fix cache issues promptly

### Step 3: Quarterly Review
- [ ] Review router.yml
  - [ ] Any new perimeters to add?
  - [ ] Any repos renamed?
  - [ ] Any file path changes?

- [ ] Review GCP permissions
  - [ ] Service account still has correct roles?
  - [ ] Keys still valid?
  - [ ] API quota sufficient?

---

## Troubleshooting Checklist

### Cache Issues
- [ ] Cache file exists: `.github/scripts/vpc_sc_project_cache.json`
- [ ] Cache file is valid JSON: `python3 -m json.tool vpc_sc_project_cache.json`
- [ ] Cache contains expected projects: `cat vpc_sc_project_cache.json | jq '.projects'`
- [ ] Cache not too old: `cat vpc_sc_project_cache.json | jq '.last_updated'`

### Router.yml Issues
- [ ] File exists and is valid YAML
- [ ] All perimeter entries have required fields (repo, tfvars_file, accesslevel_file, policy_id)
- [ ] Repository URLs are valid and accessible
- [ ] File paths exist in target repositories

### GitHub Secret Issues
- [ ] `CROSS_REPO_TOKEN` exists and is not expired
- [ ] `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON` exists (if using production sync)
- [ ] Secrets are accessible to workflows (check Actions access in repo settings)

### Workflow Execution Issues
- [ ] Workflows are enabled in Actions settings
- [ ] Audit log JSON is valid: contains `"protoPayload"` key
- [ ] Issue template is available and correct
- [ ] GitHub Actions quota not exceeded

### GCP API Issues
- [ ] Service account exists and has correct permissions
- [ ] Access Context Manager API is enabled in GCP project
- [ ] Service account key is valid (not expired)
- [ ] Policies in router.yml match actual GCP policies

---

## Files Created/Modified

### Configuration Files
- [x] `router.yml` - Perimeter → repo mapping (USER EDITS)
- [x] `.github/scripts/vpc_sc_project_cache.json` - Project cache (auto-generated)

### Scripts
- [x] `.github/scripts/audit_log_to_rules.py` - Audit log parser
- [x] `.github/scripts/generate_cross_repo_prs.py` - PR generator
- [x] `.github/scripts/update_project_cache_local.py` - Local cache generator
- [x] `.github/scripts/sync_project_cache_from_gcp.py` - GCP API sync

### Workflows
- [x] `.github/workflows/audit-log-to-rules.yml` - Main workflow
- [x] `.github/workflows/update-project-cache.yml` - Cache sync (daily)

### Templates
- [x] `.github/ISSUE_TEMPLATE/audit-log-request.yml` - Issue template

### Documentation
- [x] `README.md` - System overview
- [x] `AUDIT_LOG_GUIDE.md` - User guide
- [x] `NETSEC_REVIEW_GUIDE.md` - Security ops guide
- [x] `ROUTING_GUIDE.md` - Routing documentation
- [x] `PROJECT_CACHE_GUIDE.md` - Cache mechanism
- [x] `TESTING_GUIDE.md` - Testing strategies
- [x] `IMPLEMENTATION_SUMMARY.md` - Implementation details
- [x] `MIGRATION_FROM_OLD_SYSTEM.md` - Migration guide
- [x] `SETUP_CHECKLIST.md` - This file

---

## Next Steps

1. **Complete Phase 1** (Foundation) - Required
2. **Complete Phase 2** (Testing) - Verify everything works
3. **Complete Phase 3** (Production) - Optional, recommended for production use
4. **Complete Phase 4** (Communication) - Get team onboard
5. **Complete Phase 5** (Verification) - Monitor real usage

---

## Support

- **User questions?** → See [AUDIT_LOG_GUIDE.md](./AUDIT_LOG_GUIDE.md)
- **Setup questions?** → See this checklist
- **How does routing work?** → See [ROUTING_GUIDE.md](./ROUTING_GUIDE.md)
- **Cache issues?** → See [PROJECT_CACHE_GUIDE.md](./PROJECT_CACHE_GUIDE.md)
- **Testing?** → See [TESTING_GUIDE.md](./TESTING_GUIDE.md)
- **Security review?** → See [NETSEC_REVIEW_GUIDE.md](./NETSEC_REVIEW_GUIDE.md)

---

**Good luck with your setup! Feel free to iterate - nothing here is destructive.**
