#!/usr/bin/env python3
"""
Generate cross-repo pull requests for VPC SC rules.

CRITICAL COMPONENT: Routes generated rules to correct perimeter repositories

This script:
1. Reads router.yml to find which repo owns each perimeter
2. Clones the target perimeter repo
3. Reads existing terraform files
4. Appends new rules (preserving existing configs)
5. Creates a PR with the changes

Router.yml example:
  perimeters:
    test-perim-a:
      repo: your-org/test-perim-a-config
      tfvars_file: terraform.auto.tfvars
      accesslevel_file: accesslevel.tf
      policy_id: 123456789

This ensures rules go to the RIGHT REPO, RIGHT FILES, EVERY TIME.
"""

import argparse
import json
import subprocess
import re
import tempfile
import os
from typing import Dict, List, Any, Optional
from pathlib import Path


def load_rules(rules_file: str) -> Dict[str, Any]:
    """Load generated rules from JSON."""
    with open(rules_file, 'r') as f:
        return json.load(f)


def load_router(router_file: str) -> Dict[str, Any]:
    """Load router configuration."""
    import yaml
    with open(router_file, 'r') as f:
        return yaml.safe_load(f) or {}


def to_hcl(value: Any, indent: int = 0) -> str:
    """Convert Python object to HCL format."""
    indent_str = "  " * indent

    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(not isinstance(v, (dict, list)) for v in value):
            return "[" + ", ".join(to_hcl(v, indent) for v in value) + "]"
        lines = ["["]
        for item in value:
            lines.append(("  " * (indent + 1)) + to_hcl(item, indent + 1) + ",")
        lines.append(indent_str + "]")
        return "\n".join(lines)
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for key, val in value.items():
            key_repr = f'"{key}"' if re.search(r"[^A-Za-z0-9_]", key) else key
            lines.append(("  " * (indent + 1)) + f"{key_repr} = {to_hcl(val, indent + 1)}")
        lines.append(indent_str + "}")
        return "\n".join(lines)
    return json.dumps(value)


def append_to_tfvars(
    existing_content: Optional[str],
    rules: List[Dict[str, Any]],
    justification: str = ""
) -> str:
    """
    Append new rules to existing terraform.auto.tfvars.

    Preserves existing content and adds new ingress/egress policies.

    Args:
        existing_content: Current content of terraform.auto.tfvars (or None)
        rules: List of rule dicts (from generate_hcl_rules)
        justification: Optional justification text

    Returns:
        New file content with appended rules
    """

    if not existing_content:
        existing_content = ""

    # Parse existing ingress/egress policies
    existing_ingress = []
    existing_egress = []

    # Simple regex-based parsing of existing rules
    ingress_match = re.search(
        r'ingress_policies\s*=\s*\[(.*?)\](?:\s*egress_policies|\s*$)',
        existing_content,
        re.DOTALL
    )
    egress_match = re.search(
        r'egress_policies\s*=\s*\[(.*?)\]',
        existing_content,
        re.DOTALL
    )

    # For now, we'll just append. More sophisticated parsing could be added.
    lines = []

    # Add existing content if any (but strip trailing newlines)
    if existing_content.strip():
        lines.append(existing_content.rstrip())
        lines.append("")

    # Separate rules by direction
    ingress_rules = [r for r in rules if r.get('direction') == 'INGRESS']
    egress_rules = [r for r in rules if r.get('direction') == 'EGRESS']

    # Add ingress policies
    if ingress_rules:
        lines.append("ingress_policies = [")
        for rule in ingress_rules:
            hcl_rule = to_hcl({'from': rule['from'], 'to': rule['to']}, indent=1)
            rule_lines = hcl_rule.split("\n")

            # Add justification comment if provided
            if justification:
                comment_lines = ["  # " + ln.strip() for ln in justification.split("\n")]
                rule_lines = [rule_lines[0]] + comment_lines + rule_lines[1:]

            lines.extend(["  " + ln for ln in rule_lines])
            lines[-1] += ","
        lines.append("]")

    # Add egress policies
    if egress_rules:
        if ingress_rules:
            lines.append("")  # Blank line between sections
        lines.append("egress_policies = [")
        for rule in egress_rules:
            hcl_rule = to_hcl({'from': rule['from'], 'to': rule['to']}, indent=1)
            rule_lines = hcl_rule.split("\n")

            # Add justification comment if provided
            if justification:
                comment_lines = ["  # " + ln.strip() for ln in justification.split("\n")]
                rule_lines = [rule_lines[0]] + comment_lines + rule_lines[1:]

            lines.extend(["  " + ln for ln in rule_lines])
            lines[-1] += ","
        lines.append("]")

    return "\n".join(lines) + "\n"


def append_access_levels(
    existing_content: Optional[str],
    rules: List[Dict[str, Any]]
) -> Optional[str]:
    """
    Append new access level modules to existing accesslevel.tf.

    Only appends if rules contain access level definitions.

    Args:
        existing_content: Current content of accesslevel.tf (or None)
        rules: List of rule dicts

    Returns:
        New file content with appended access levels, or None if no levels needed
    """

    # Extract access levels from rules
    access_levels = []
    for rule in rules:
        if 'access_level_name' in rule and 'access_level_ip' in rule:
            level_name = rule['access_level_name']
            level_ip = rule['access_level_ip']

            access_level_hcl = f'''module "vpc-service-controls-access-level_{level_name}" {{
  source  = "tfe. / /vpc-service-controls/google//modules/access_level"
  version = "0.0.4"
  policy  = var.policy
  name    = "{level_name}"
  ip_subnetworks = ["{level_ip}"]
}}'''

            access_levels.append(access_level_hcl)

    if not access_levels:
        return None

    lines = []

    # Add existing content if any
    if existing_content and existing_content.strip():
        lines.append(existing_content.rstrip())
        lines.append("")

    # Add new access levels
    lines.extend(access_levels)

    return "\n".join(lines) + "\n"


def clone_repo(repo_url: str, temp_dir: str) -> str:
    """
    Clone target repository to temp directory.

    Args:
        repo_url: GitHub repo URL (https://github.com/org/repo)
        temp_dir: Temporary directory

    Returns:
        Path to cloned repo
    """
    repo_path = Path(temp_dir) / Path(repo_url).name.replace('.git', '')

    cmd = ['git', 'clone', '--depth', '1', repo_url, str(repo_path)]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return str(repo_path)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to clone {repo_url}: {e.stderr.decode()}")


def read_file(file_path: str) -> str:
    """Read file content, return empty string if not exists."""
    if Path(file_path).exists():
        with open(file_path, 'r') as f:
            return f.read()
    return ""


def write_file(file_path: str, content: str) -> None:
    """Write content to file, creating parent dirs if needed."""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.write(content)


def create_github_branch_and_pr(
    repo_url: str,
    perimeter: str,
    rules: List[Dict[str, Any]],
    router_config: Dict[str, Any],
    issue_number: int,
    service: str,
    method: str,
    caller_ip: Optional[str],
    tlm_id: Optional[str] = None,
    github_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a GitHub branch and PR with rule changes.

    CRITICAL LOGIC: This is where router.yml routes rules to the correct repo/files

    Args:
        repo_url: Target repository URL (https://github.com/org/repo)
        perimeter: Perimeter name (used to look up router.yml)
        rules: Rules for this perimeter
        router_config: Router configuration (from router.yml)
        issue_number: Source issue number
        service: GCP service name
        method: GCP method name
        caller_ip: Caller IP (if applicable)
        tlm_id: TLM ID (if applicable)
        github_token: GitHub token for API calls

    Returns:
        Dict with PR info or error details
    """

    # STEP 1: Get perimeter config from router.yml
    perim_info = router_config.get("perimeters", {}).get(perimeter)
    if not perim_info:
        return {
            'perimeter': perimeter,
            'status': 'error',
            'error': f"Perimeter '{perimeter}' not found in router.yml"
        }

    tfvars_file = perim_info.get("tfvars_file", "terraform.auto.tfvars")
    accesslevel_file = perim_info.get("accesslevel_file", "accesslevel.tf")

    # STEP 2: Create branch name from perimeter and issue
    directions = set(r['direction'] for r in rules)
    direction_str = '-'.join(sorted(directions)).lower()
    branch_name = f"vpcsc/req-{issue_number}-{perimeter}-{direction_str}"

    try:
        # Save original working directory to restore later
        original_cwd = os.getcwd()

        # STEP 3: Clone the target perimeter repository
        # THIS IS WHERE ROUTING HAPPENS: repo_url comes from router.yml
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"🔄 Cloning {repo_url} to {temp_dir}")
            repo_path = clone_repo(repo_url, temp_dir)

            # STEP 4: Read existing terraform files
            # FILE TARGETING: paths come from router.yml
            tfvars_path = Path(repo_path) / tfvars_file
            accesslevel_path = Path(repo_path) / accesslevel_file

            existing_tfvars = read_file(str(tfvars_path))
            existing_accesslevel = read_file(str(accesslevel_path))

            print(f"📄 Reading {tfvars_file}: {len(existing_tfvars)} bytes")
            print(f"📄 Reading {accesslevel_file}: {len(existing_accesslevel)} bytes")

            # STEP 5: Append new content (preserve existing)
            new_tfvars = append_to_tfvars(existing_tfvars, rules)
            new_accesslevel = append_access_levels(existing_accesslevel, rules)

            # STEP 6: Write updated files back to repo
            write_file(str(tfvars_path), new_tfvars)
            if new_accesslevel:
                write_file(str(accesslevel_path), new_accesslevel)

            print(f"✏️  Updated {tfvars_file}: {len(new_tfvars)} bytes")
            if new_accesslevel:
                print(f"✏️  Updated {accesslevel_file}: {len(new_accesslevel)} bytes")

            # STEP 7: Create git branch
            os.chdir(repo_path)
            subprocess.run(['git', 'config', 'user.email', 'vpc-sc-automation@example.com'], check=True)
            subprocess.run(['git', 'config', 'user.name', 'VPC SC Automation'], check=True)
            subprocess.run(['git', 'checkout', '-b', branch_name], check=True)

            # STEP 8: Commit changes
            subprocess.run(['git', 'add', tfvars_file], check=True)
            if new_accesslevel:
                subprocess.run(['git', 'add', accesslevel_file], check=True)

            commit_msg = f"[VPC-SC] Add rules for {perimeter} - Issue #{issue_number}\n\n" \
                        f"Service: {service}\n" \
                        f"Method: {method}\n" \
                        f"Direction: {', '.join(directions)}\n" \
                        f"Caller: {caller_ip or 'internal'}"

            subprocess.run(['git', 'commit', '-m', commit_msg], check=True)

            # STEP 9: Push branch and create PR
            # Uses GITHUB_TOKEN from environment for authentication
            if github_token:
                # Push with token auth
                repo_name = Path(repo_url).name.replace('.git', '')
                repo_owner = Path(repo_url).parent.name

                subprocess.run(
                    ['git', 'push', '-u', f'https://{github_token}@github.com/{repo_owner}/{repo_name}.git', branch_name],
                    check=True,
                    capture_output=True
                )

                # Create PR via GitHub API
                pr_body = f"""## VPC Service Controls Rule Request

**Issue:** #{issue_number}
**Perimeter:** {perimeter}
**Direction:** {', '.join(directions)}

### Request Summary
- **Service:** {service}
- **Method:** {method}
- **Caller IP:** {caller_ip or 'Internal'}
- **TLM ID:** {tlm_id or 'N/A (internal)'}

### Changes
This PR appends new VPC Service Controls rules while preserving existing configurations.

- Updated `{tfvars_file}` with new ingress/egress policies
- Updated `{accesslevel_file}` with new access levels (if applicable)

All changes are append-only - no existing configurations are modified or removed.

### Network Security Review Checklist
- [ ] Source is known and trusted
- [ ] Destination is correct
- [ ] Service and method are appropriate
- [ ] TLM ID is valid (if applicable)
- [ ] Access level is correct (if applicable)
- [ ] Changes don't affect other rules
"""

                pr_title = f"VPC SC rules for {perimeter} - {service} from {caller_ip or 'internal'}"

                pr_response = subprocess.run(
                    ['gh', 'pr', 'create',
                     '--repo', f"{repo_owner}/{repo_name}",
                     '--head', branch_name,
                     '--title', pr_title,
                     '--body', pr_body],
                    check=True,
                    capture_output=True,
                    text=True
                )

                pr_url = pr_response.stdout.strip()

                # Restore working directory before returning
                os.chdir(original_cwd)

                return {
                    'perimeter': perimeter,
                    'branch': branch_name,
                    'pr_title': pr_title,
                    'pr_url': pr_url,
                    'status': 'created',
                    'direction': ', '.join(directions),
                    'files_modified': [tfvars_file] + ([accesslevel_file] if new_accesslevel else [])
                }
            else:
                # No token, just report what would be done
                # Restore working directory before returning
                os.chdir(original_cwd)

                return {
                    'perimeter': perimeter,
                    'branch': branch_name,
                    'pr_title': f"VPC SC rules for {perimeter} - {service}",
                    'status': 'ready_for_pr',
                    'message': 'Branch created, ready for PR (set GITHUB_TOKEN to create PR)',
                    'direction': ', '.join(directions)
                }

    except Exception as e:
        # Restore working directory on error
        try:
            os.chdir(original_cwd)
        except:
            pass

        return {
            'perimeter': perimeter,
            'status': 'error',
            'error': str(e)
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate cross-repo PRs for VPC SC rules'
    )
    parser.add_argument('--rules-file', required=True, help='Generated rules JSON')
    parser.add_argument('--router-file', required=True, help='Router configuration')
    parser.add_argument('--issue-number', required=True, type=int, help='GitHub issue number')
    parser.add_argument('--output', required=True, help='Output summary JSON')
    parser.add_argument('--github-token', help='GitHub token (from GITHUB_TOKEN or CROSS_REPO_TOKEN env var)')

    args = parser.parse_args()

    # Get GitHub token from arg or environment
    github_token = args.github_token or os.getenv('GITHUB_TOKEN') or os.getenv('CROSS_REPO_TOKEN')

    if not github_token:
        print("⚠️  No GitHub token provided. Set GITHUB_TOKEN or CROSS_REPO_TOKEN environment variable.")
        print("   Without it, branches will be created locally but PRs won't be pushed.")

    # Load data
    rules_data = load_rules(args.rules_file)
    router_config = load_router(args.router_file)

    # Check for errors in rule generation
    if 'error' in rules_data:
        result = {
            'success': False,
            'error': rules_data['error'],
            'pull_requests': []
        }
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2))
        return

    # Extract request summary
    request_summary = rules_data.get('request_summary', {})
    service = request_summary.get('service', 'unknown')
    method = request_summary.get('method', 'unknown')
    caller_ip = request_summary.get('source', {}).get('ip')
    tlm_id = None  # Would come from parsed data if applicable

    rules = rules_data.get('rules', [])

    if not rules:
        result = {
            'success': False,
            'error': 'No rules generated',
            'pull_requests': []
        }
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2))
        return

    # Group rules by perimeter
    # THIS IS THE ROUTING LOGIC: Perimeter name → which rules to apply
    rules_by_perim = {}
    for rule in rules:
        perim = rule['perimeter']
        if perim not in rules_by_perim:
            rules_by_perim[perim] = []
        rules_by_perim[perim].append(rule)

    print(f"\n📦 Processing {len(rules_by_perim)} perimeter(s):\n")

    # Generate PRs for each perimeter
    prs = []
    for perimeter, perim_rules in rules_by_perim.items():
        print(f"  ➤ {perimeter}: {len(perim_rules)} rule(s)")

        # CRITICAL ROUTING: Look up perimeter in router.yml
        perim_info = router_config.get("perimeters", {}).get(perimeter)
        if not perim_info:
            print(f"    ❌ Not found in router.yml - skipping")
            prs.append({
                'perimeter': perimeter,
                'status': 'error',
                'error': f"Perimeter not found in router.yml"
            })
            continue

        repo_url = perim_info.get("repo")
        if not repo_url:
            print(f"    ❌ No repo URL in router.yml - skipping")
            prs.append({
                'perimeter': perimeter,
                'status': 'error',
                'error': "No repo URL configured in router.yml"
            })
            continue

        # Ensure repo_url is full GitHub URL
        if not repo_url.startswith("http"):
            repo_url = f"https://github.com/{repo_url}"

        print(f"    Repository: {repo_url}")
        print(f"    TFVars file: {perim_info.get('tfvars_file', 'terraform.auto.tfvars')}")
        print(f"    Access level file: {perim_info.get('accesslevel_file', 'accesslevel.tf')}")

        # Create PR for this perimeter
        # router_config is passed so function can look up file paths
        pr_info = create_github_branch_and_pr(
            repo_url,
            perimeter,
            perim_rules,
            router_config,
            args.issue_number,
            service,
            method,
            caller_ip,
            tlm_id,
            github_token
        )

        if pr_info['status'] == 'created':
            print(f"    ✅ PR created: {pr_info['pr_url']}")
        elif pr_info['status'] == 'ready_for_pr':
            print(f"    ⏳ Branch ready, PR pending (no GitHub token)")
        else:
            print(f"    ❌ Error: {pr_info.get('error', 'Unknown error')}")

        prs.append(pr_info)

    # Generate summary report
    successful_prs = [p for p in prs if p['status'] == 'created']
    failed_prs = [p for p in prs if p['status'] == 'error']

    result = {
        'success': len(failed_prs) == 0,
        'issue_number': args.issue_number,
        'pull_requests': prs,
        'summary': {
            'total_perimeters': len(rules_by_perim),
            'successful_prs': len(successful_prs),
            'failed_prs': len(failed_prs),
            'message': f"Generated {len(successful_prs)} PR(s) for {len(rules_by_perim)} perimeter(s)"
        }
    }

    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n📊 Summary:\n")
    print(f"  Total perimeters: {len(rules_by_perim)}")
    print(f"  Successful PRs: {len(successful_prs)}")
    print(f"  Failed: {len(failed_prs)}")
    print(f"\n  Output: {args.output}\n")

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
