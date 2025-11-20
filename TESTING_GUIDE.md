# Testing Guide - VPC SC Automation

Complete testing strategy for the audit log-driven VPC SC rule automation.

---

## Test Levels

### Level 1: Unit Tests (Local, No GCP/GitHub needed)
Test individual components in isolation

### Level 2: Integration Tests (Local, With Mock Data)
Test the full pipeline with realistic data

### Level 3: End-to-End Tests (Staging GitHub + Test Perimeters)
Test against real GitHub and mock GCP

### Level 4: Production Dry-Run
Test against real GitHub in a non-destructive way

---

## Level 1: Unit Tests

### Test audit_log_to_rules.py

```bash
# Run all unit tests (no external dependencies)
cd vpc-sc-automation
python3 -m pytest .github/scripts/tests/test_audit_log_to_rules.py -v
```

**Tests to run:**

1. **Parse Audit Log**
   ```python
   def test_parse_audit_log_valid_json():
       """Valid audit log parses successfully"""

   def test_parse_audit_log_invalid_json():
       """Invalid JSON returns None"""

   def test_parse_audit_log_missing_protoPayload():
       """JSON without protoPayload returns None"""
   ```

2. **Extract Fields**
   ```python
   def test_extract_service_and_method():
       """Extracts serviceName and methodName"""

   def test_extract_caller_ip():
       """Extracts callerIp from requestMetadata"""

   def test_extract_perimeter_name():
       """Extracts perimeter from servicePerimeterName path"""

   def test_extract_destination_project():
       """Extracts project from ingressViolations"""
   ```

3. **IP Detection**
   ```python
   def test_is_public_ip_global():
       """Global IPs detected as public"""
       # 8.8.8.8, 1.1.1.1, 203.0.113.55 → True

   def test_is_private_ip_rfc1918():
       """RFC 1918 IPs detected as private"""
       # 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 → False

   def test_is_private_ip_special():
       """Special strings detected as private"""
       # "gce-internal-ip", "private" → False
   ```

4. **Perimeter Ownership Detection**
   ```python
   def test_project_in_cache():
       """Project found in cache returns perimeter"""
       # 1111111111 → test-perim-a

   def test_project_not_in_cache():
       """Project not in cache returns None"""

   def test_project_in_router_config():
       """Project in router.yml returns perimeter"""
   ```

5. **Direction Auto-Detection**
   ```python
   def test_direction_same_perimeter():
       """Same perimeter = SKIP"""
       assert auto_detect_direction('test-perim-a', 'test-perim-a')['direction'] == 'SKIP'

   def test_direction_both_internal():
       """Different internal perimeters = BOTH"""
       assert auto_detect_direction('test-perim-a', 'test-perim-b')['direction'] == 'BOTH'

   def test_direction_ingress():
       """External source, internal dest = INGRESS"""
       assert auto_detect_direction(None, 'test-perim-a')['direction'] == 'INGRESS'

   def test_direction_egress():
       """Internal source, external dest = EGRESS"""
       assert auto_detect_direction('test-perim-a', None)['direction'] == 'EGRESS'
   ```

6. **TLM ID Requirement**
   ```python
   def test_tlm_required_public_ingress():
       """Public IP + INGRESS = TLM required"""
       parsed = {'is_public_ip': True}
       direction = {'direction': 'INGRESS', 'source_perimeter': None}
       assert validate_tlm_requirement(parsed, direction)['requires'] == True

   def test_tlm_not_required_private_ingress():
       """Private IP + INGRESS = TLM not required"""
       parsed = {'is_public_ip': False}
       direction = {'direction': 'INGRESS', 'source_perimeter': None}
       assert validate_tlm_requirement(parsed, direction)['requires'] == False

   def test_tlm_required_egress_external():
       """EGRESS to external = TLM required"""
       parsed = {'is_public_ip': False}
       direction = {'direction': 'EGRESS', 'dest_perimeter': None}
       assert validate_tlm_requirement(parsed, direction)['requires'] == True
   ```

### Running Unit Tests

Create `.github/scripts/tests/test_audit_log_to_rules.py`:

```bash
# Install pytest
pip install pytest pytest-cov

# Run tests with coverage
pytest .github/scripts/tests/ -v --cov=.github/scripts/audit_log_to_rules

# Run specific test
pytest .github/scripts/tests/test_audit_log_to_rules.py::test_is_public_ip_global -v
```

---

## Level 2: Integration Tests (Local with Mock Data)

### Mock Audit Logs

Create `.github/scripts/tests/fixtures/audit_logs/`:

```
audit_logs/
├── public_ip_ingress.json          # On-prem to GCP
├── private_ip_cross_perim.json     # Cross-perimeter
├── external_destination.json        # GCP to external
└── invalid_format.json              # Error case
```

**Example: public_ip_ingress.json**
```json
{
  "protoPayload": {
    "serviceName": "storage.googleapis.com",
    "methodName": "storage.objects.get",
    "authenticationInfo": {
      "principalEmail": "deployer-sa@corp.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "203.0.113.55"
    },
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/123/servicePerimeters/test-perim-a"
      },
      "ingressViolations": [{
        "targetResource": "projects/999888777"
      }]
    }
  },
  "resource": {
    "labels": {
      "project_id": "source-project"
    }
  }
}
```

### Integration Test Script

Create `.github/scripts/tests/test_full_pipeline.py`:

```python
#!/usr/bin/env python3
"""Full pipeline integration tests with mock data"""

import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from audit_log_to_rules import (
    parse_audit_log_json,
    extract_from_audit_log,
    determine_perimeter_ownership,
    auto_detect_direction,
    validate_tlm_requirement,
    generate_hcl_rules
)

def test_full_pipeline_public_ip_ingress():
    """End-to-end: on-prem (public IP) to GCP = INGRESS + TLM"""

    # Load mock audit log
    with open('fixtures/audit_logs/public_ip_ingress.json') as f:
        audit_log = json.load(f)

    # Load mock project cache
    with open('fixtures/vpc_sc_project_cache.json') as f:
        project_cache = json.load(f)['projects']

    # Load router config
    import yaml
    with open('router.yml') as f:
        router = yaml.safe_load(f)

    # Parse
    parsed = extract_from_audit_log(audit_log)
    assert parsed['service'] == 'storage.googleapis.com'
    assert parsed['is_public_ip'] == True
    assert parsed['perimeter'] == 'test-perim-a'

    # Determine ownership
    src_perim = determine_perimeter_ownership(
        parsed['source_project'], project_cache, router
    )
    assert src_perim is None  # External source

    dst_perim = determine_perimeter_ownership(
        parsed['dest_project'], project_cache, router
    )
    assert dst_perim == 'test-perim-a'  # Internal destination

    # Auto-detect direction
    direction = auto_detect_direction(src_perim, dst_perim)
    assert direction['direction'] == 'INGRESS'
    assert direction['perimeters'] == ['test-perim-a']

    # Validate TLM
    tlm_validation = validate_tlm_requirement(parsed, direction)
    assert tlm_validation['requires'] == True

    # Generate rules
    rules_result = generate_hcl_rules(parsed, direction, tlm_id='TLM-DATA-OPS-01')
    assert 'rules' in rules_result
    assert len(rules_result['rules']) > 0
    assert rules_result['rules'][0]['direction'] == 'INGRESS'
    assert 'access_level_name' in rules_result['rules'][0]

def test_full_pipeline_cross_perim():
    """End-to-end: test-perim-a to test-perim-b = BOTH"""

    # Similar to above but loads cross_perim fixture
    # ...

    direction = auto_detect_direction('test-perim-a', 'test-perim-b')
    assert direction['direction'] == 'BOTH'
    assert 'test-perim-a' in direction['perimeters']
    assert 'test-perim-b' in direction['perimeters']

if __name__ == '__main__':
    test_full_pipeline_public_ip_ingress()
    test_full_pipeline_cross_perim()
    print("✅ All integration tests passed")
```

### Run Integration Tests

```bash
cd vpc-sc-automation
python3 .github/scripts/tests/test_full_pipeline.py
```

---

## Level 3: Local Workflow Simulation

### Test Without Pushing to GitHub

Create `.github/scripts/tests/test_github_actions_simulation.py`:

```python
#!/usr/bin/env python3
"""Simulate GitHub Actions workflow locally"""

import json
import yaml
from pathlib import Path
from audit_log_to_rules import parse_audit_log_json, extract_from_audit_log
from generate_cross_repo_prs import (
    load_rules, load_router, append_to_tfvars, append_access_levels
)

def simulate_workflow(audit_log_file, router_file, project_cache_file):
    """Simulate the full workflow without GitHub"""

    # Step 1: Parse audit log
    with open(audit_log_file) as f:
        audit_log_text = f.read()

    audit_log_json = parse_audit_log_json(audit_log_text)
    if not audit_log_json:
        return {'error': 'Invalid audit log'}

    # Step 2: Extract information
    parsed = extract_from_audit_log(audit_log_json)

    # Step 3: Load configuration
    with open(router_file) as f:
        router = yaml.safe_load(f)

    with open(project_cache_file) as f:
        project_cache = json.load(f)['projects']

    # Step 4: Process rules (generate HCL)
    # ... (call generate_hcl_rules) ...

    # Step 5: Simulate appending to files
    print("\n📋 Simulated Changes:\n")

    for perim, rules in rules_by_perim.items():
        print(f"Perimeter: {perim}")
        perim_info = router['perimeters'][perim]

        # Simulate reading existing files
        tfvars_path = f"repos/{perim}/{perim_info['tfvars_file']}"
        existing_tfvars = ""  # In real scenario, would read from repo

        # Generate appended content
        new_tfvars = append_to_tfvars(existing_tfvars, rules)

        print(f"\n  Would append to: {perim_info['tfvars_file']}")
        print(f"  {len(new_tfvars.split(chr(10)))} lines")

        # Show preview
        print("\n  Preview (first 500 chars):")
        print("  " + new_tfvars[:500].replace("\n", "\n  "))

if __name__ == '__main__':
    simulate_workflow(
        'fixtures/audit_logs/public_ip_ingress.json',
        'router.yml',
        '.github/scripts/test_vpc_sc_cache.json'
    )
```

---

## Level 4: Production Dry-Run Testing

### Test Against Staging GitHub Repos

**Setup:**
1. Create staging repos: `test-perim-a-staging`, `test-perim-b-staging`
2. Create staging `router.yml` pointing to staging repos
3. Run workflow against staging repos
4. Verify PRs created correctly
5. Review diffs before merging

**Steps:**

```bash
# 1. Create test issue in staging with audit log
gh issue create \
  --repo your-org/vpc-sc-automation-staging \
  --title "VPC SC Test: Public IP Ingress" \
  --body "$(cat fixtures/audit_logs/public_ip_ingress.json)"

# 2. Monitor workflow
gh run list --repo your-org/vpc-sc-automation-staging --workflow audit-log-to-rules.yml

# 3. Check generated PRs
gh pr list --repo your-org/test-perim-a-staging

# 4. Review the diff
gh pr view <pr-number> --repo your-org/test-perim-a-staging

# 5. Don't merge yet - just verify looks correct

# 6. Close the test issue
gh issue close <issue-number> --repo your-org/vpc-sc-automation-staging
```

---

## Test Data Templates

### fixture/vpc_sc_project_cache.json
```json
{
  "last_updated": "2024-01-15T02:00:00Z",
  "projects": {
    "1111111111": "test-perim-a",
    "2222222222": "test-perim-b",
    "3333333333": "test-perim-a",
    "4444444444": "test-perim-b",
    "999888777": "test-perim-a",
    "999888778": "test-perim-b"
  }
}
```

### fixtures/router_test.yml
```yaml
perimeters:
  test-perim-a:
    repo: your-org/test-perim-a-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 123456789
    projects:
      - "1111111111"
      - "3333333333"

  test-perim-b:
    repo: your-org/test-perim-b-config
    tfvars_file: terraform.auto.tfvars
    accesslevel_file: accesslevel.tf
    policy_id: 987654321
    projects:
      - "2222222222"
      - "4444444444"
```

---

## Expected Test Results

### Passing Test: Public IP Ingress
```
Test: public_ip_ingress
  ✅ Audit log parses
  ✅ Service extracted: storage.googleapis.com
  ✅ Method extracted: storage.objects.get
  ✅ Caller IP detected: 203.0.113.55
  ✅ Public IP detected: True
  ✅ Direction: INGRESS
  ✅ TLM Required: Yes
  ✅ Rules generated: 1
  ✅ Access level module generated
  ✅ HCL is valid Terraform
PASS
```

### Passing Test: Cross-Perimeter
```
Test: cross_perim
  ✅ Audit log parses
  ✅ Source perimeter: test-perim-a
  ✅ Dest perimeter: test-perim-b
  ✅ Direction: BOTH
  ✅ TLM Required: No
  ✅ Perimeters affected: 2
  ✅ EGRESS rule generated for test-perim-a
  ✅ INGRESS rule generated for test-perim-b
PASS
```

### Failing Test: Invalid JSON
```
Test: invalid_json
  ✅ Error caught: "Invalid audit log JSON"
  ✅ No rules generated
PASS (expected failure)
```

---

## CI/CD Integration

### GitHub Actions Workflow for Testing

Create `.github/workflows/test.yml`:

```yaml
name: Test VPC SC Automation

on:
  push:
    paths:
      - '.github/scripts/**'
  pull_request:

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pytest pytest-cov pyyaml
      - run: pytest .github/scripts/tests/ -v --cov

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pyyaml
      - run: python3 .github/scripts/tests/test_full_pipeline.py
```

---

## Quick Start: Run Tests Now

```bash
# 1. Install dependencies
pip install pytest pytest-cov pyyaml

# 2. Run unit tests
pytest .github/scripts/tests/test_audit_log_to_rules.py -v

# 3. Run integration tests
python3 .github/scripts/tests/test_full_pipeline.py

# 4. Simulate workflow
python3 .github/scripts/tests/test_github_actions_simulation.py
```

---

## Troubleshooting Tests

| Issue | Solution |
|-------|----------|
| Import errors | Verify file structure, use `sys.path.insert(0, ...)` |
| Missing fixtures | Check fixtures/ directory exists with test data |
| YAML parse errors | Validate YAML syntax: `python3 -m yaml router.yml` |
| Cache lookup fails | Verify project numbers in test cache match fixtures |

---

## Before Going to Production

✅ Pass all unit tests
✅ Pass all integration tests
✅ Simulate workflow successfully
✅ Test against staging repos (no merge)
✅ Have network security team review sample PRs
✅ Verify append-only logic with existing configs
✅ Test TLM ID comment interaction
✅ Test cross-perimeter BOTH direction scenario
