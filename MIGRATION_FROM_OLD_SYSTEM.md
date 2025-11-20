# Migration: Old Form-Based VPC SC to New Audit-Log-Driven System

## Summary of Changes

The VPC SC automation has been completely redesigned from a **form-based request system** to an **audit-log-driven system**.

### What Changed

**Old System (Removed):**
- ❌ GitHub issue forms with dropdowns
- ❌ Manual Terraform writing required
- ❌ Separate INGRESS/EGRESS requests
- ❌ TLM ID handling unclear
- ❌ Error-prone manual perimeter selection
- ❌ Complex form validation

**New System (vpc-sc-automation):**
- ✅ Paste Cloud Audit Log JSON
- ✅ Automatic Terraform generation
- ✅ Auto-detects direction (INGRESS/EGRESS/BOTH)
- ✅ Automatic TLM ID requirement detection
- ✅ Perimeter ownership lookup (from project cache)
- ✅ Simple, clean validation

### Files Removed (From multiboundaryautomation)

The following old VPC SC files have been **removed** because they're superseded by the new system:

```
✅ Removed: multiboundaryautomation/VPC_SC_SIMPLE_GUIDE.md
✅ Removed: multiboundaryautomation/CLEANUP_SUMMARY.md
✅ Removed: multiboundaryautomation/.github/ISSUE_TEMPLATE/vpc-sc-request-simple.yml
✅ Removed: multiboundaryautomation/.github/workflows/process-vpc-sc-request.yml
✅ Removed: multiboundaryautomation/.github/workflows/update-vpc-sc-cache.yml
✅ Removed: multiboundaryautomation/.github/scripts/validate_vpc_sc_request.py
✅ Removed: multiboundaryautomation/.github/scripts/vpc_sc_request_handler.py
✅ Removed: multiboundaryautomation/.github/scripts/extract_vpc_sc_error_info.py
✅ Removed: multiboundaryautomation/.github/scripts/test_vpc_sc_cache.json
```

**These are all replaced by the new audit-log-driven system in `vpc-sc-automation/`.**

---

## New System Location

All VPC SC automation is now in: **`vpc-sc-automation/`**

### New Documentation

| File | Purpose |
|------|---------|
| **README.md** | System overview and architecture |
| **AUDIT_LOG_GUIDE.md** | User guide - how to find and submit audit logs |
| **NETSEC_REVIEW_GUIDE.md** | Security ops guide - how to review PRs |
| **ROUTING_GUIDE.md** | How the system routes rules to correct repos |
| **TESTING_GUIDE.md** | Complete testing strategy (4 levels) |
| **IMPLEMENTATION_SUMMARY.md** | Answers to key questions about testing & routing |

### New Scripts

| File | Purpose |
|------|---------|
| **audit_log_to_rules.py** | Parse audit log, auto-detect direction, validate TLM |
| **generate_cross_repo_prs.py** | Create PRs in target repos using router.yml |
| **audit-log-to-rules.yml** | GitHub Actions workflow |

### New Configuration

| File | Purpose |
|------|---------|
| **router.yml** | Maps perimeters → repos → files (CRITICAL) |
| **audit-log-request.yml** | GitHub issue template |

---

## Migration Path for Existing Requests

If you have pending VPC SC requests from the old system:

1. **Get the VPC SC error** that the old request was trying to solve
2. **Find the audit log** in Cloud Logging
3. **Create a new issue** in vpc-sc-automation with the audit log
4. **Delete the old issue** from multiboundaryautomation

The new system will:
- ✅ Parse it correctly
- ✅ Auto-detect what you need
- ✅ Create the right rules
- ✅ Generate PRs for network security review

---

## Key Differences

### Old Way
```
User: "I need access to BigQuery in test-perim-a"
                 ↓
Form: Select perimeter, select direction, select service
                 ↓
Manual validation, error messages
                 ↓
Maybe create PR, maybe not
```

### New Way
```
User: Gets VPC SC error → finds audit log → pastes JSON
                 ↓
System: Parses audit log automatically
                 ↓
System: Detects perimeter, direction, service, TLM need
                 ↓
System: Creates PRs in correct repos
                 ↓
Network security: Reviews & approves
```

---

## What Users Need to Know

1. **New URL:** Issues go to `vpc-sc-automation` repo, not `multiboundaryautomation`
2. **New Process:** Paste audit log JSON instead of filling out a form
3. **No VPC SC Knowledge Required:** System figures it out
4. **Faster:** Automatic direction detection, no manual selection
5. **Safer:** Append-only changes, no risk of overwriting rules

---

## Configuration: router.yml

The **one critical piece** you need to configure:

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

**Every perimeter must be in router.yml** or PRs won't be created.

---

## Testing the New System

See **TESTING_GUIDE.md** for complete instructions, but quick start:

```bash
# Level 1: Unit tests (fastest, no external deps)
pip install pytest pytest-cov pyyaml
pytest .github/scripts/tests/test_audit_log_to_rules.py -v

# Level 2: Integration tests (with mock data)
python3 .github/scripts/tests/test_full_pipeline.py

# Level 3: Workflow simulation (without GitHub)
python3 .github/scripts/tests/test_github_actions_simulation.py

# Level 4: Staging test (against real GitHub)
# Create staging repos, update router.yml, create test issue
```

---

## Advantages of New System

| Aspect | Old System | New System |
|--------|-----------|-----------|
| **User Knowledge** | Required VPC SC understanding | Not required |
| **Input Method** | Form with dropdowns | Paste audit log JSON |
| **Direction Detection** | Manual selection | Automatic |
| **TLM ID** | Confusing when needed | Automatic detection |
| **Cross-Perimeter** | 2 separate requests | 1 request, 2 PRs |
| **Terraform Writing** | User does it | System generates |
| **Validation Errors** | Generic error messages | Specific, actionable |
| **Append Safety** | Risk of overwrites | Guaranteed append-only |

---

## FAQ

### Q: Can I still use the old system?
**A:** No, old files have been removed. All new requests must use the audit-log-driven system.

### Q: What if I don't know how to find an audit log?
**A:** See [AUDIT_LOG_GUIDE.md](./AUDIT_LOG_GUIDE.md) - it has step-by-step instructions.

### Q: What if my request needs both INGRESS and EGRESS?
**A:** Submit one audit log. System detects both perimeters and creates 2 PRs automatically.

### Q: Where do I create the issue now?
**A:** In `vpc-sc-automation` repo, not `multiboundaryautomation`.

### Q: Do I still need to know about router.yml?
**A:** Only if you're setting up the automation. As a requestor, you just paste the audit log.

### Q: What if perimeter isn't in router.yml?
**A:** Error message: "Perimeter 'X' not found in router.yml". Add it and try again.

---

## Cleanup Checklist

- ✅ Old VPC SC files removed from multiboundaryautomation
- ✅ New system created in vpc-sc-automation
- ✅ Documentation complete (5 guides + README)
- ✅ Scripts complete (2 core scripts + workflow)
- ✅ Testing guide created (4 levels)
- ✅ router.yml configured
- ✅ Issue template created

---

## Next Steps

1. **Review** [README.md](./README.md) for system overview
2. **Configure** router.yml with your perimeters
3. **Test** using TESTING_GUIDE.md (start with Level 1)
4. **Share** AUDIT_LOG_GUIDE.md with users
5. **Share** NETSEC_REVIEW_GUIDE.md with security team
6. **Deploy** GitHub Actions secrets (GITHUB_TOKEN)
7. **Enable** audit-log-to-rules.yml workflow

---

## Questions?

See the comprehensive guides:
- **User questions?** → [AUDIT_LOG_GUIDE.md](./AUDIT_LOG_GUIDE.md)
- **How does routing work?** → [ROUTING_GUIDE.md](./ROUTING_GUIDE.md)
- **How do I test?** → [TESTING_GUIDE.md](./TESTING_GUIDE.md)
- **Security ops questions?** → [NETSEC_REVIEW_GUIDE.md](./NETSEC_REVIEW_GUIDE.md)
- **How do I answer the key questions?** → [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)

---

## Summary

**Old System:** Form-based, error-prone, required VPC SC knowledge
**New System:** Audit-log-driven, automatic, simple, safe

**Result:** Self-service VPC SC rule requests for everyone, without needing VPC SC expertise.
