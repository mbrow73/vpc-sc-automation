# VPC SC Automation - Routing & Repository Targeting Guide

## How the System Knows Where to Apply Changes

The **router.yml** file is the critical routing configuration that ensures rules go to the correct repository and the correct files every time.

---

## The Routing Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Audit Log submitted in GitHub issue                      │
│    ↓                                                         │
│    "Destination perimeter: test-perim-a"                    │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 2. audit_log_to_rules.py extracts perimeter name            │
│    ↓                                                         │
│    extracted_perimeter = "test-perim-a"                     │
│    direction = "INGRESS"                                    │
│    rules = [...]  (HCL policy blocks)                       │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 3. generate_cross_repo_prs.py receives rules                │
│    ↓                                                         │
│    - Loads router.yml                                       │
│    - Groups rules by perimeter name                         │
│    - For each perimeter: look up in router.yml              │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 4. CRITICAL: ROUTING LOOKUP                                 │
│                                                             │
│    router.yml:                                              │
│    perimeters:                                              │
│      test-perim-a:                 ← Perimeter name         │
│        repo: org/test-perim-a-config   ← REPO URL (TARGET) │
│        tfvars_file: terraform.auto.tfvars  ← FILE PATH      │
│        accesslevel_file: accesslevel.tf    ← FILE PATH      │
│        policy_id: 123456789                                 │
│                                                             │
│    Logic: perimeter_name → repo_url + file_paths            │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 5. Clone target repository                                  │
│    ↓                                                         │
│    git clone https://github.com/org/test-perim-a-config    │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 6. Read existing files (paths from router.yml)              │
│    ↓                                                         │
│    read: terraform.auto.tfvars                              │
│    read: accesslevel.tf                                     │
│    [Preserve existing content]                              │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 7. Append new rules                                         │
│    ↓                                                         │
│    new_tfvars = existing + newrules                         │
│    write back to terraform.auto.tfvars                      │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 8. Create branch, commit, push                              │
│    ↓                                                         │
│    git branch vpcsc/req-123-test-perim-a-ingress            │
│    git add terraform.auto.tfvars accesslevel.tf             │
│    git commit "Add VPC SC rules..."                         │
│    git push                                                 │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│ 9. Create PR in correct repo                                │
│    ↓                                                         │
│    gh pr create --repo org/test-perim-a-config              │
│                                                             │
│    ✅ PR created in test-perim-a-config repo                │
│    ✅ Changes only in terraform.auto.tfvars                 │
│    ✅ Existing rules preserved                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## router.yml Structure

The router file maps each perimeter to its repository and file locations.

### Minimal Example

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

### Complete Example with All Options

```yaml
perimeters:
  prod-data-perimeter:
    # ← Perimeter name (must match VPC SC perimeter name)
    repo: your-org/prod-data-perimeter-config
    # ← GitHub repo URL (where terraform files are)
    # Can be: "org/repo" or "https://github.com/org/repo"

    tfvars_file: terraform.auto.tfvars
    # ← Path to tfvars file within repo
    # File that will receive new ingress/egress policies

    accesslevel_file: accesslevel.tf
    # ← Path to access level file within repo
    # File that will receive new access level modules

    policy_id: 123456789
    # ← VPC SC policy ID (for reference)

    projects:
      # ← Optional: list of projects in this perimeter
      - "1111111111"
      - "2222222222"
      - "3333333333"
```

### Example with Multiple Perimeters

```yaml
perimeters:
  test-perim-a:
    repo: your-org/test-perim-a-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 123456789
    projects: ["1111111111", "3333333333"]

  test-perim-b:
    repo: your-org/test-perim-b-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 987654321
    projects: ["2222222222", "4444444444"]

  prod-perimeter:
    repo: your-org/prod-perimeter-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 555666777
```

---

## Routing Logic in Code

### Step 1: Perimeter Extraction

**audit_log_to_rules.py** extracts the perimeter name from the audit log:

```python
# From audit log metadata
perimeter_path = "accessPolicies/123/servicePerimeters/test-perim-a"

# Regex extracts perimeter name
match = re.search(r'servicePerimeters/([a-zA-Z0-9_-]+)', perimeter_path)
perimeter_name = match.group(1)  # "test-perim-a"

# Included in generated rules
rule = {
    'perimeter': 'test-perim-a',  # ← Perimeter name
    'direction': 'INGRESS',
    'from': {...},
    'to': {...}
}
```

### Step 2: Rule Grouping by Perimeter

**generate_cross_repo_prs.py** groups rules by perimeter:

```python
rules_by_perim = {}
for rule in rules:
    perim = rule['perimeter']  # 'test-perim-a'
    if perim not in rules_by_perim:
        rules_by_perim[perim] = []
    rules_by_perim[perim].append(rule)

# Result:
# {
#   'test-perim-a': [rule1, rule2],
#   'test-perim-b': [rule3]
# }
```

### Step 3: CRITICAL ROUTING - Lookup in router.yml

```python
for perimeter, perim_rules in rules_by_perim.items():
    # perimeter = 'test-perim-a'

    # ROUTING: Look up in router.yml
    perim_info = router_config.get("perimeters", {}).get(perimeter)

    # perim_info = {
    #   'repo': 'your-org/test-perim-a-config',
    #   'tfvars_file': 'terraform.auto.tfvars',
    #   'accesslevel_file': 'accesslevel.tf',
    #   'policy_id': '123456789'
    # }

    repo_url = perim_info.get("repo")
    # repo_url = 'your-org/test-perim-a-config'

    tfvars_file = perim_info.get("tfvars_file")
    # tfvars_file = 'terraform.auto.tfvars'

    accesslevel_file = perim_info.get("accesslevel_file")
    # accesslevel_file = 'accesslevel.tf'

    # Now we KNOW:
    # - Which repo to clone
    # - Which files to modify
    # - EVERYTHING from router.yml
```

### Step 4: Clone & Modify

```python
# Clone using repo URL from router.yml
repo_path = clone_repo(repo_url, temp_dir)
# Clones: https://github.com/your-org/test-perim-a-config

# Read using file paths from router.yml
tfvars_path = Path(repo_path) / tfvars_file
# Reads: <repo>/terraform.auto.tfvars

existing_tfvars = read_file(str(tfvars_path))

# Append new rules
new_tfvars = append_to_tfvars(existing_tfvars, perim_rules)

# Write back using same path
write_file(str(tfvars_path), new_tfvars)
```

---

## Real-World Example

### Scenario: Cross-Perimeter Request

**Audit log shows:**
- Source: test-perim-a (private IP)
- Destination: test-perim-b
- Service: bigquery
- Direction detected: BOTH (EGRESS + INGRESS)

**Routing:**

```
1. audit_log_to_rules.py generates 2 rules:
   Rule 1: perimeter='test-perim-a', direction='EGRESS'
   Rule 2: perimeter='test-perim-b', direction='INGRESS'

2. generate_cross_repo_prs.py groups by perimeter:
   test-perim-a: [Rule 1 (EGRESS)]
   test-perim-b: [Rule 2 (INGRESS)]

3. For test-perim-a:
   - Look up in router.yml → find test-perim-a config
   - repo = 'your-org/test-perim-a-config'
   - tfvars_file = 'terraform.auto.tfvars'
   - Clone repo
   - Read terraform.auto.tfvars
   - Append Rule 1 (EGRESS)
   - Create PR in test-perim-a-config

4. For test-perim-b:
   - Look up in router.yml → find test-perim-b config
   - repo = 'your-org/test-perim-b-config'
   - tfvars_file = 'terraform.auto.tfvars'
   - Clone repo
   - Read terraform.auto.tfvars
   - Append Rule 2 (INGRESS)
   - Create PR in test-perim-b-config

5. Result:
   - PR #1 in test-perim-a-config with EGRESS rule
   - PR #2 in test-perim-b-config with INGRESS rule
   - Each modifying only its own perimeter's rules
   - Both PRs linked to source issue
```

---

## File Targeting

The file paths are **determined dynamically** based on router.yml:

### Scenario 1: Standard Layout

```yaml
perimeters:
  test-perim-a:
    repo: your-org/test-perim-a-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
```

**Files modified:**
- `test-perim-a-config/terraform.auto.tfvars`
- `test-perim-a-config/accesslevel.tf`

### Scenario 2: Custom File Paths

```yaml
perimeters:
  test-perim-a:
    repo: your-org/test-perim-a-config
    tfvars_file: env/prod/terraform.auto.tfvars
    accesslevel_file: env/prod/accesslevel.tf
```

**Files modified:**
- `test-perim-a-config/env/prod/terraform.auto.tfvars`
- `test-perim-a-config/env/prod/accesslevel.tf`

### Scenario 3: Different Files Per Perimeter

```yaml
perimeters:
  test-perim-a:
    repo: your-org/test-perim-a-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: access-levels.tf

  test-perim-b:
    repo: your-org/test-perim-b-config
    tfvars_file: rules.auto.tfvars
    accesslevel_file: security-levels.tf
```

**For test-perim-a:**
- `test-perim-a-config/terraform.auto.tfvars`
- `test-perim-a-config/access-levels.tf`

**For test-perim-b:**
- `test-perim-b-config/rules.auto.tfvars`
- `test-perim-b-config/security-levels.tf`

---

## Error Handling

What happens if perimeter not in router.yml:

```
1. audit_log extracted: perimeter = "unknown-perim"

2. generate_cross_repo_prs.py looks up:
   perim_info = router_config.get("perimeters", {}).get("unknown-perim")
   # Returns: None (not found)

3. Error handling:
   return {
       'perimeter': 'unknown-perim',
       'status': 'error',
       'error': "Perimeter 'unknown-perim' not found in router.yml"
   }

4. Result:
   - No PR created
   - Issue comments with error
   - User knows to check router.yml
```

---

## Validation Checklist

Before running automation, verify router.yml:

- [ ] Perimeter names match actual VPC SC perimeter names
- [ ] Repo URLs are correct (can clone)
- [ ] File paths exist in target repos
- [ ] Repos are accessible with GITHUB_TOKEN
- [ ] File names match actual terraform file names
- [ ] Policy IDs are correct (for reference)

**Test routing:**

```bash
# Verify router.yml syntax
python3 -c "import yaml; yaml.safe_load(open('router.yml'))" && echo "✅ Valid"

# Test lookup
python3 << 'EOF'
import yaml
with open('router.yml') as f:
    router = yaml.safe_load(f)

perimeter = 'test-perim-a'
if perimeter in router.get('perimeters', {}):
    print(f"✅ {perimeter} found")
    print(f"   Repo: {router['perimeters'][perimeter]['repo']}")
else:
    print(f"❌ {perimeter} not found")
EOF
```

---

## Summary: How It Works

| Component | Lookup | Purpose |
|-----------|--------|---------|
| **Audit Log** | Perimeter name | Source of truth |
| **audit_log_to_rules.py** | Extracts perimeter name from audit log | Knows which perimeter is affected |
| **generate_cross_repo_prs.py** | Groups rules by perimeter name | Organizes rules for routing |
| **router.yml** | Perimeter → Repo + Files | **CRITICAL: Routes to correct repo/files** |
| **Git Clone** | Repo URL from router.yml | Clones correct repo |
| **File Read** | File path from router.yml | Reads correct files |
| **File Write** | File path from router.yml | Writes to correct files |
| **PR Create** | Repo URL from router.yml | Creates PR in correct repo |

**The entire routing depends on router.yml being accurate and up-to-date.**

---

## Updating router.yml

When you add a new perimeter:

1. Create the new perimeter repo (e.g., `test-perim-c-config`)
2. Add to router.yml:
   ```yaml
   test-perim-c:
     repo: your-org/test-perim-c-config
     tfvars_file: terraform.auto.tfvars
     accesslevel_file: accesslevel.tf
     policy_id: YOUR_POLICY_ID
   ```
3. Commit and push
4. Automation will now route requests for test-perim-c to the correct repo

---

## Troubleshooting Routing Issues

| Problem | Solution |
|---------|----------|
| PR goes to wrong repo | Check perimeter name spelling in router.yml |
| File not modified | Check tfvars_file path in router.yml |
| Access level not created | Check accesslevel_file path in router.yml |
| Perimeter not found error | Add to router.yml under `perimeters:` section |
| Repo clone fails | Verify repo URL is accessible with GITHUB_TOKEN |

---

## Diagram: Routing Flow

```
┌─────────────────────┐
│ Audit Log Submitted │
│ perimeter: test-a   │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────┐
│ Extract Perimeter Name       │
│ ➜ "test-perim-a"             │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ Create rules with perimeter  │
│ rule.perimeter = "test-perim-a" │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ Group by perimeter           │
│ rules_by_perim['test-perim-a']  │
└──────────┬───────────────────┘
           │
           ▼
       ┏━━━━━━━━━━━┓
       ┃ router.yml ┃ ◄─── LOOKUP: "test-perim-a"
       ┗━━━━━━━━━━━┛
           │
           ▼ Returns:
       ┌─────────────────────────┐
       │ repo: org/test-perim-a  │
       │ tfvars_file: terraform.auto.tfvars │
       │ accesslevel_file: accesslevel.tf │
       └────────────┬────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
    Clone Repo  Read Files  Get File Paths
        │           │           │
        └───────────┼───────────┘
                    │
                    ▼
            Append New Rules
                    │
                    ▼
            Create Branch & PR
                    │
                    ▼
            ✅ PR in Correct Repo
```
