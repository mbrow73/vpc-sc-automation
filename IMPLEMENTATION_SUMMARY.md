# Implementation Summary - VPC SC Automation

## Two Critical Questions Answered

### 1. How Can I Test This?

**Answer:** Multi-level testing strategy (complete guide in [TESTING_GUIDE.md](./TESTING_GUIDE.md))

#### Level 1: Unit Tests (Fastest, No External Dependencies)
```bash
# Test individual functions in isolation
pip install pytest pytest-cov pyyaml
pytest .github/scripts/tests/test_audit_log_to_rules.py -v

# Tests included:
# - Audit log parsing (valid/invalid JSON)
# - Field extraction (service, method, IP, perimeter)
# - Public vs private IP detection
# - Perimeter ownership lookup
# - Direction auto-detection (INGRESS/EGRESS/BOTH)
# - TLM ID requirement validation
```

#### Level 2: Integration Tests (Local, Mock Data)
```bash
# Test full pipeline with mock audit logs
python3 .github/scripts/tests/test_full_pipeline.py

# Tests scenarios:
# - Public IP ingress (on-prem to GCP)
# - Private IP cross-perimeter (test-perim-a to test-perim-b)
# - External destination (GCP to third-party)
# - Invalid/missing data handling
```

#### Level 3: Workflow Simulation (Local, Before GitHub)
```bash
# Simulate the entire workflow without pushing to GitHub
python3 .github/scripts/tests/test_github_actions_simulation.py

# Simulates:
# - Audit log extraction
# - Router.yml lookup
# - File appending
# - PR structure generation
# - No actual repos/branches created
```

#### Level 4: Staging Test (Against Real GitHub)
```bash
# Create staging repos: test-perim-a-staging, test-perim-b-staging
# Create staging router.yml pointing to staging repos

# Then:
gh issue create \
  --repo your-org/vpc-sc-automation-staging \
  --title "VPC SC Test: Public IP Ingress" \
  --body "$(cat fixtures/audit_logs/public_ip_ingress.json)"

# Monitor: gh run list --repo your-org/vpc-sc-automation-staging
# Review: gh pr list --repo your-org/test-perim-a-staging
# Verify PR diffs, don't merge
```

**Key Test Scenarios:**
- ✅ Public IP INGRESS → TLM ID required
- ✅ Private IP INGRESS → TLM not needed
- ✅ Cross-perimeter BOTH → 2 PRs created
- ✅ External egress → TLM required
- ✅ Same perimeter → SKIP (no rule needed)
- ✅ Invalid audit log → Error message
- ✅ TLM comment interaction → Re-process
- ✅ Append-only preservation → Existing rules safe

---

### 2. How Does the Pipeline Know Where to Apply Changes?

**Answer:** `router.yml` is the **routing configuration** that maps perimeter names to repositories and files.

## The Routing Mechanism

```
┌────────────────────────────────────────────────────────────┐
│ AUDIT LOG contains: servicePerimeterName = "test-perim-a"  │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼ Extract perimeter name
                  "test-perim-a"
                         │
                         ▼ Group rules by perimeter
            rules_by_perim['test-perim-a'] = [...]
                         │
                         ▼ Lookup in ROUTER.YML
    ┌────────────────────────────────────────────────┐
    │ router.yml:                                    │
    │                                                │
    │ perimeters:                                    │
    │   test-perim-a:                                │
    │     repo: org/test-perim-a-config    ◄─────┐  │
    │     tfvars_file: terraform.auto.tfvars   ◄─┼─┼┐ │
    │     accesslevel_file: accesslevel.tf     ◄─┼─┼┼┐│
    │     policy_id: 123456789                    │ │││
    │                                             │ │││
    └─────────────────────────────────────────────┼─┼┼┘
                         │                        │ ││
                ┌────────┴────────────────────────┘ ││
                │                                    ││
                ▼ Clone                  ▼ Read      ▼ Write
    git clone org/test-perim-a-config
              ├── terraform.auto.tfvars (READ)
              └── accesslevel.tf (READ/WRITE)
                         │
                         ▼
            Append new rules to files
                         │
                         ▼
            git commit & push
                         │
                         ▼
    Create PR in org/test-perim-a-config
    ✅ Correct repo, correct files, every time
```

## router.yml Structure

### Minimal Configuration

```yaml
perimeters:
  test-perim-a:
    repo: your-org/test-perim-a-config        # Which repo to target
    tfvars_file: terraform.auto.tfvars        # Where ingress/egress rules go
    accesslevel_file: accesslevel.tf          # Where access levels go
    policy_id: 123456789                      # VPC SC policy ID

  test-perim-b:
    repo: your-org/test-perim-b-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 987654321
```

### How It Routes (Step by Step)

```python
# Step 1: Generated rules have perimeter name
rule = {
    'perimeter': 'test-perim-a',  # From audit log
    'direction': 'INGRESS',
    'from': {...},
    'to': {...}
}

# Step 2: Group by perimeter
rules_by_perim = {
    'test-perim-a': [rule1, rule2],
    'test-perim-b': [rule3]
}

# Step 3: For each perimeter, lookup in router.yml
for perimeter, rules in rules_by_perim.items():
    # perimeter = 'test-perim-a'

    perim_info = router_config['perimeters']['test-perim-a']
    # Now we have:
    # - repo: "org/test-perim-a-config"
    # - tfvars_file: "terraform.auto.tfvars"
    # - accesslevel_file: "accesslevel.tf"

# Step 4: Use these to clone, read, append, commit, PR
repo_url = perim_info['repo']                      # "org/test-perim-a-config"
tfvars_path = perim_info['tfvars_file']            # "terraform.auto.tfvars"
accesslevel_path = perim_info['accesslevel_file']  # "accesslevel.tf"

# Clone
git clone https://github.com/org/test-perim-a-config

# Read from correct files
read: terraform.auto.tfvars
read: accesslevel.tf

# Append new rules
existing = read(terraform.auto.tfvars)
new = existing + rules

# Write back
write(terraform.auto.tfvars, new)

# PR in correct repo
gh pr create --repo org/test-perim-a-config
```

## Real-World Example: Cross-Perimeter Request

**Audit log shows:**
- Source: test-perim-a
- Destination: test-perim-b
- Violation type: INGRESS (crossing perimeters)

**What happens:**

```
1. Extract perimeters:
   - Source perimeter: test-perim-a
   - Destination perimeter: test-perim-b
   - Direction detected: BOTH (EGRESS + INGRESS)

2. Generate 2 rules:
   Rule 1: perimeter='test-perim-a', direction='EGRESS'
   Rule 2: perimeter='test-perim-b', direction='INGRESS'

3. Group by perimeter:
   test-perim-a: [EGRESS rule]
   test-perim-b: [INGRESS rule]

4. For test-perim-a:
   ├─ Lookup in router.yml
   │  └─ repo: org/test-perim-a-config
   │  └─ tfvars_file: terraform.auto.tfvars
   ├─ Clone org/test-perim-a-config
   ├─ Read terraform.auto.tfvars
   ├─ Append EGRESS rule
   └─ Create PR in org/test-perim-a-config

5. For test-perim-b:
   ├─ Lookup in router.yml
   │  └─ repo: org/test-perim-b-config
   │  └─ tfvars_file: terraform.auto.tfvars
   ├─ Clone org/test-perim-b-config
   ├─ Read terraform.auto.tfvars
   ├─ Append INGRESS rule
   └─ Create PR in org/test-perim-b-config

6. Result:
   ✅ PR #1: test-perim-a-config with EGRESS rule
   ✅ PR #2: test-perim-b-config with INGRESS rule
   Both linked to source issue
```

## File Targeting

The pipeline reads/writes to files specified in router.yml:

```yaml
perimeters:
  test-perim-a:
    repo: org/test-perim-a-config
    tfvars_file: terraform.auto.tfvars    # ← Modified
    accesslevel_file: accesslevel.tf      # ← Modified (if public IP)
```

**Files modified:**
```
test-perim-a-config/
├── terraform.auto.tfvars        ← Rules appended here
├── accesslevel.tf               ← Access levels appended here
└── (other files untouched)
```

**Append-only logic:**
```python
# Read existing
existing_tfvars = read("terraform.auto.tfvars")

# Append new (preserve existing)
new_tfvars = existing_tfvars + "\n\ningress_policies = [\n  { ... new rule ... }\n]\n"

# Write back (file grows, never shrinks)
write("terraform.auto.tfvars", new_tfvars)
```

## Guaranteed Correctness

The routing is **100% deterministic** because:

1. ✅ **Perimeter name comes from audit log** - Can't be wrong (that's what the error is about)
2. ✅ **Router.yml is source of truth** - One configuration, all perimeters
3. ✅ **Lookup happens for every perimeter** - No hardcoding, no guessing
4. ✅ **File paths from router.yml** - Dynamic, not hardcoded
5. ✅ **Repo URL from router.yml** - Can have multiple repos, all handled

**If router.yml is correct, routing is correct.**

## Validation Before Running

```bash
# 1. Verify router.yml syntax
python3 -c "import yaml; yaml.safe_load(open('router.yml')); print('✅ Valid YAML')"

# 2. Verify all perimeters have required fields
python3 << 'EOF'
import yaml
with open('router.yml') as f:
    router = yaml.safe_load(f)

required = ['repo', 'tfvars_file', 'accesslevel_file']
for perim, config in router['perimeters'].items():
    for field in required:
        if field not in config:
            print(f"❌ {perim} missing '{field}'")
        else:
            print(f"✅ {perim}.{field} = {config[field]}")
EOF

# 3. Verify repos are accessible
for perim in $(yq '.perimeters | keys[]' router.yml); do
  repo=$(yq ".perimeters.$perim.repo" router.yml)
  git ls-remote $repo > /dev/null && echo "✅ $repo accessible" || echo "❌ $repo not accessible"
done
```

## Summary

| Question | Answer |
|----------|--------|
| **Where does routing config come from?** | `router.yml` file in vpc-sc-automation repo |
| **What maps perimeter to repo?** | `perimeters:<name>.repo` in router.yml |
| **What maps perimeter to files?** | `perimeters:<name>.tfvars_file` and `accesslevel_file` |
| **How does system know which repo?** | Looks up perimeter name extracted from audit log |
| **How does it know which files?** | Reads file paths from router.yml for that perimeter |
| **What if perimeter not in router.yml?** | Error: "Perimeter not found in router.yml" |
| **Can rules go to wrong repo?** | Only if router.yml has wrong URL for that perimeter |
| **Can rules modify wrong files?** | Only if router.yml has wrong file paths |

---

## Next Steps

1. **Configure router.yml** with your perimeter repos
2. **Run Level 1 tests** to validate logic locally
3. **Run Level 2 tests** with mock data
4. **Run Level 3 tests** with workflow simulation
5. **Run Level 4 tests** against staging repos
6. **Deploy to production** when confident

See [TESTING_GUIDE.md](./TESTING_GUIDE.md) for complete testing instructions.
See [ROUTING_GUIDE.md](./ROUTING_GUIDE.md) for detailed routing documentation.
