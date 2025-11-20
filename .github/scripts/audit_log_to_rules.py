#!/usr/bin/env python3
"""
Convert VPC SC audit log → automatically generated ingress/egress rules.

This script:
1. Parses a VPC SC violation from a Cloud Audit Log (JSON)
2. Determines source & destination perimeter ownership
3. Auto-detects if rule needs INGRESS, EGRESS, or BOTH
4. Validates TLM ID requirement for third-party access
5. Generates Terraform HCL for all affected perimeters
6. Creates cross-repo pull requests with append-only changes

No user knowledge of VPC SC terminology required - just paste the audit log!

Example:
  python3 audit_log_to_rules.py \
    --audit-log-json '{"protoPayload": {...}}' \
    --router-file router.yml \
    --project-cache vpc_sc_project_cache.json \
    --output rules.json
"""

import argparse
import json
import re
import sys
from typing import Dict, List, Optional, Any
from pathlib import Path

# Add parent directory to import extract_vpc_sc_error_info if needed
sys.path.insert(0, str(Path(__file__).parent))


def parse_audit_log_json(audit_log_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse and validate audit log JSON.

    Args:
        audit_log_text: Raw JSON string from Cloud Logging

    Returns:
        Parsed audit log dict, or None if invalid
    """
    try:
        data = json.loads(audit_log_text)
        if "protoPayload" in data:
            return data
        return None
    except (json.JSONDecodeError, ValueError):
        return None


def extract_from_audit_log(audit_log: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract VPC SC violation details from structured audit log.

    Robust extraction that handles:
    - Multiple GCP services (BigQuery, Storage, Compute, SQL, Pub/Sub, etc.)
    - Cross-perimeter violations
    - Complex enterprise scenarios
    - Various audit log structures

    Args:
        audit_log: Parsed audit log JSON

    Returns:
        Dict with extracted fields
    """
    import ipaddress

    def is_public_ip(ip_str: str) -> bool:
        """Check if IP is public (not RFC 1918 private)."""
        if not ip_str or ip_str.lower() in ["gce-internal-ip", "private", ""]:
            return False
        try:
            ip = ipaddress.ip_address(ip_str)
            # is_global covers public IPs, excludes private, loopback, etc.
            return ip.is_global
        except ValueError:
            return False

    def extract_project_from_string(s: str) -> Optional[str]:
        """Extract project number from various resource strings."""
        if not s:
            return None
        # Try different patterns
        patterns = [
            r'projects/(\d+)',          # projects/123456789
            r'projects/([a-z0-9-]+)',   # projects/my-project (by ID)
        ]
        for pattern in patterns:
            match = re.search(pattern, s)
            if match:
                result = match.group(1)
                # Return only if it's numeric (project number)
                if result.isdigit():
                    return result
        return None

    def extract_perimeter_from_string(s: str) -> Optional[str]:
        """Extract perimeter name from resource path."""
        if not s:
            return None
        match = re.search(r'servicePerimeters/([a-zA-Z0-9_-]+)', s)
        if match:
            return match.group(1)
        return None

    result = {
        "perimeter": None,
        "source_perimeter": None,
        "dest_perimeter": None,
        "service": None,
        "method": None,
        "source_project": None,
        "dest_project": None,
        "service_account": None,
        "caller_ip": None,
        "is_public_ip": False,
        "violation_type": None,  # INGRESS, EGRESS, or BOTH
    }

    proto = audit_log.get("protoPayload", {})

    # Service and method
    result["service"] = proto.get("serviceName", "").lower()
    result["method"] = proto.get("methodName", "").lower()

    # Service account / Principal
    auth_info = proto.get("authenticationInfo", {})
    result["service_account"] = auth_info.get("principalEmail")

    # Caller IP - check multiple sources
    request_metadata = proto.get("requestMetadata", {})
    caller_ip = request_metadata.get("callerIp")
    if not caller_ip:
        # Try sourceAttributes (newer format)
        source_attrs = request_metadata.get("sourceAttributes", {})
        caller_ip = source_attrs.get("sourceIp")

    if caller_ip:
        result["caller_ip"] = caller_ip
        result["is_public_ip"] = is_public_ip(caller_ip)

    # Perimeter from multiple possible sources in metadata
    metadata = proto.get("metadata", {})
    perimeter_path = None

    # Try new format first (real Google audit logs)
    if "servicePerimeter" in metadata:
        perimeter_path = metadata.get("servicePerimeter", "")
    # Try old format (simplified/test audit logs)
    elif "securityPolicyInfo" in metadata:
        security_policy = metadata.get("securityPolicyInfo", {})
        perimeter_path = security_policy.get("servicePerimeterName", "")

    if perimeter_path:
        result["perimeter"] = extract_perimeter_from_string(perimeter_path)

    # Extract source project from multiple possible locations
    # Priority: callerNetwork > authentication > principalEmail project > resource labels
    source_project = None

    # 1. Try callerNetwork (best source)
    caller_network = request_metadata.get("callerNetwork", "")
    if caller_network:
        source_project = extract_project_from_string(caller_network)

    # 2. Try principalEmail if service account from same project
    if not source_project and result["service_account"]:
        # Service account format: name@project-id.iam.gserviceaccount.com
        if "@" in result["service_account"]:
            parts = result["service_account"].split("@")
            if len(parts) > 1:
                project_part = parts[1].split(".")[0]
                # Try to extract numeric project number
                if project_part.isdigit():
                    source_project = project_part

    # 3. Try resource.labels.project_id
    if not source_project:
        resource = audit_log.get("resource", {})
        resource_labels = resource.get("labels", {})
        project_id = resource_labels.get("project_id", "")
        if project_id.isdigit():
            source_project = project_id

    # 4. Try resourceName in protoPayload
    if not source_project:
        resource_name = proto.get("resourceName", "")
        source_project = extract_project_from_string(resource_name)

    result["source_project"] = source_project

    # Determine violation type and extract destination
    ingress_violations = metadata.get("ingressViolations", [])
    egress_violations = metadata.get("egressViolations", [])
    access_denial_violations = metadata.get("accessDenialViolations", [])

    # Collect all violations
    violations_present = {
        "ingress": len(ingress_violations) > 0,
        "egress": len(egress_violations) > 0,
        "access_denial": len(access_denial_violations) > 0,
    }

    # Determine direction
    if ingress_violations and egress_violations:
        result["violation_type"] = "BOTH"
    elif ingress_violations:
        result["violation_type"] = "INGRESS"
    elif egress_violations:
        result["violation_type"] = "EGRESS"
    elif access_denial_violations:
        # Access denial can be either, default to INGRESS
        result["violation_type"] = "INGRESS"

    # Extract destination project and perimeter from violations
    # Handle BOTH new format (nested ingressFrom/To) AND old format (targetResource)
    for violation_type, violations in [
        ("ingress", ingress_violations),
        ("egress", egress_violations),
        ("access_denial", access_denial_violations),
    ]:
        if violations:
            violation = violations[0]
            target_resource = None

            # NEW FORMAT: Real Google audit logs use nested structure
            if violation_type == "ingress":
                # Extract from ingressTo.resource
                ingress_to = violation.get("ingressTo", {})
                target_resource = ingress_to.get("resource")

                # Also extract source from ingressFrom.sourceResource if available
                if not result["source_project"]:
                    ingress_from = violation.get("ingressFrom", {})
                    source_resource = ingress_from.get("sourceResource")
                    if source_resource:
                        src_proj = extract_project_from_string(source_resource)
                        if src_proj:
                            result["source_project"] = src_proj

            elif violation_type == "egress":
                # Extract from egressTo.resource
                egress_to = violation.get("egressTo", {})
                target_resource = egress_to.get("resource")

            elif violation_type == "access_denial":
                # Access denial may have different structure, try both
                if "ingressTo" in violation:
                    ingress_to = violation.get("ingressTo", {})
                    target_resource = ingress_to.get("resource")
                elif "egressTo" in violation:
                    egress_to = violation.get("egressTo", {})
                    target_resource = egress_to.get("resource")
                else:
                    # Fallback to targetResource if available
                    target_resource = violation.get("targetResource", "")

            # If new format didn't work, try old format
            if not target_resource:
                target_resource = violation.get("targetResource", "")

            if target_resource:
                dest_project = extract_project_from_string(target_resource)
                if dest_project:
                    result["dest_project"] = dest_project

                # Also try to extract destination perimeter
                dest_perim = extract_perimeter_from_string(target_resource)
                if dest_perim:
                    result["dest_perimeter"] = dest_perim

    # For cross-perimeter scenarios, try to identify both perimeters
    # If we have targetResource with perimeter info, that's the other perimeter
    if result["dest_perimeter"] and result["perimeter"]:
        result["source_perimeter"] = result["perimeter"]

    return result


def load_router_config(router_file: str) -> Dict[str, Any]:
    """Load router.yml configuration."""
    import yaml
    try:
        with open(router_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as e:
        print(f"ERROR: Cannot load router file: {e}")
        return {}


def load_project_cache(cache_file: str) -> Dict[str, str]:
    """
    Load project → perimeter cache (project_num → perimeter_name).

    Args:
        cache_file: Path to vpc_sc_project_cache.json
                   If relative, resolved from script directory

    Returns:
        Dict of project_num → perimeter_name mappings
    """
    try:
        # Make path absolute if relative
        cache_path = Path(cache_file)
        if not cache_path.is_absolute():
            script_dir = Path(__file__).parent
            cache_path = script_dir / cache_file

        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("projects", {})
    except FileNotFoundError:
        print(f"⚠️  Project cache not found: {cache_path}", file=sys.stderr)
        print(f"   Run: python3 .github/scripts/update_project_cache_local.py", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"⚠️  Error loading project cache: {str(e)}", file=sys.stderr)
        return {}


def determine_perimeter_ownership(
    project_num: Optional[str],
    project_cache: Dict[str, str],
    router_config: Dict[str, Any]
) -> Optional[str]:
    """
    Determine if a project is in any of our perimeters.

    Args:
        project_num: GCP project number
        project_cache: Dict of project_num → perimeter_name
        router_config: Router configuration from router.yml

    Returns:
        Perimeter name if found, None otherwise
    """
    if not project_num:
        return None

    # First check cache
    if project_num in project_cache:
        return project_cache[project_num]

    # Fallback: check router config
    for perim_name, perim_info in router_config.get("perimeters", {}).items():
        # Check if we have a projects list in router
        if "projects" in perim_info and project_num in perim_info.get("projects", []):
            return perim_name

    return None


def auto_detect_direction(
    src_perim: Optional[str],
    dst_perim: Optional[str]
) -> Dict[str, Any]:
    """
    Determine rule direction based on source/destination perimeter ownership.

    Returns:
        {
            'direction': 'INGRESS' | 'EGRESS' | 'BOTH' | 'SKIP',
            'perimeters': [list of affected perimeters],
            'meaning': str,
            'skip_reason': str (if SKIP)
        }
    """

    # Same perimeter = no rule needed (resources can already communicate)
    if src_perim and dst_perim and src_perim == dst_perim:
        return {
            'direction': 'SKIP',
            'skip_reason': f'Communication within {src_perim} is allowed by default'
        }

    # Both in different perimeters = INGRESS + EGRESS
    if src_perim and dst_perim:
        return {
            'direction': 'BOTH',
            'perimeters': [src_perim, dst_perim],
            'meaning': f'EGRESS from {src_perim} + INGRESS to {dst_perim}',
            'source_perimeter': src_perim,
            'dest_perimeter': dst_perim
        }

    # Source internal, destination external = EGRESS only
    if src_perim and not dst_perim:
        return {
            'direction': 'EGRESS',
            'perimeters': [src_perim],
            'meaning': f'EGRESS from {src_perim} to external project',
            'source_perimeter': src_perim,
            'dest_perimeter': None
        }

    # Source external, destination internal = INGRESS only
    if not src_perim and dst_perim:
        return {
            'direction': 'INGRESS',
            'perimeters': [dst_perim],
            'meaning': f'INGRESS to {dst_perim} from external source',
            'source_perimeter': None,
            'dest_perimeter': dst_perim
        }

    # Both external = impossible
    return {
        'direction': 'SKIP',
        'skip_reason': 'Both source and destination are external'
    }


def validate_tlm_requirement(
    parsed: Dict[str, Any],
    direction_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Determine if TLM ID is required for this rule.

    TLM ID is required if:
    - INGRESS from public IP (third-party external source)
    - EGRESS to external project (third-party external destination)

    Args:
        parsed: Extracted audit log data
        direction_info: Direction detection result

    Returns:
        {
            'requires': bool,
            'reason': str,
            'tlm_id': None (user must provide)
        }
    """

    if direction_info['direction'] == 'SKIP':
        return {'requires': False, 'reason': None}

    is_public = parsed.get('is_public_ip', False)
    source_external = direction_info.get('source_perimeter') is None
    dest_external = direction_info.get('dest_perimeter') is None

    # INGRESS from public/external = TLM required
    if direction_info['direction'] in ['INGRESS', 'BOTH']:
        if source_external:
            if is_public:
                return {
                    'requires': True,
                    'reason': 'Ingress from public IP requires TLM ID',
                    'tlm_id': None
                }

    # EGRESS to external = TLM required
    if direction_info['direction'] in ['EGRESS', 'BOTH']:
        if dest_external:
            return {
                'requires': True,
                'reason': 'Egress to external/third-party project requires TLM ID',
                'tlm_id': None
            }

    return {'requires': False, 'reason': None}


def generate_hcl_rules(
    parsed: Dict[str, Any],
    direction_info: Dict[str, Any],
    tlm_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate Terraform HCL rules for affected perimeters.

    Args:
        parsed: Extracted audit log data
        direction_info: Direction detection result
        tlm_id: TLM ID (if applicable)

    Returns:
        {
            'rules': [
                {
                    'perimeter': str,
                    'direction': 'INGRESS' | 'EGRESS',
                    'hcl_policy': str,
                    'hcl_access_level': str (if applicable)
                }
            ]
        }
    """

    rules = []

    if direction_info['direction'] == 'SKIP':
        return {'error': direction_info.get('skip_reason')}

    service = parsed.get('service', '')
    method = parsed.get('method', '')
    source_project = parsed.get('source_project')
    dest_project = parsed.get('dest_project')
    service_account = parsed.get('service_account', '')
    caller_ip = parsed.get('caller_ip')

    # Build operations dict
    operations = {}
    if service and method:
        operations[service] = {
            "methods": [method],
            "permissions": []
        }

    # Generate INGRESS rule if needed
    if direction_info['direction'] in ['INGRESS', 'BOTH']:
        perim = direction_info.get('dest_perimeter')

        ingress_from = {"identity_type": ""}

        # If source is external, may need access level
        if not direction_info.get('source_perimeter'):
            # External source
            if caller_ip and parsed.get('is_public_ip'):
                # Public IP = create access level
                if tlm_id:
                    access_level_name = tlm_id.lower().replace('_', '-')
                    ingress_from["sources"] = {
                        "resources": [],
                        "access_levels": [access_level_name]
                    }

                    # Generate access level HCL
                    access_level_hcl = f'''module "vpc-service-controls-access-level_{access_level_name}" {{
  source  = "tfe. / /vpc-service-controls/google//modules/access_level"
  version = "0.0.4"
  policy  = var.policy
  name    = "{access_level_name}"
  ip_subnetworks = ["{caller_ip}"]
}}
'''
                else:
                    # No TLM ID provided for public IP
                    return {'error': 'TLM ID required for public IP ingress'}
            else:
                # Private IP from external - just use project resource
                if source_project:
                    ingress_from["sources"] = {
                        "resources": [f"projects/{source_project}"],
                        "access_levels": []
                    }
        else:
            # Source is internal (cross-perimeter)
            if source_project:
                ingress_from["sources"] = {
                    "resources": [f"projects/{source_project}"],
                    "access_levels": []
                }

        # Add service account if available
        if service_account:
            ingress_from["identities"] = [f"serviceAccount:{service_account}"]

        # Build to section
        ingress_to = {}
        if dest_project:
            ingress_to["resources"] = [f"projects/{dest_project}"]
        if operations:
            ingress_to["operations"] = operations

        rule = {
            "perimeter": perim,
            "direction": "INGRESS",
            "from": ingress_from,
            "to": ingress_to
        }

        if tlm_id and caller_ip and parsed.get('is_public_ip'):
            rule['access_level_name'] = tlm_id.lower().replace('_', '-')
            rule['access_level_ip'] = caller_ip

        rules.append(rule)

    # Generate EGRESS rule if needed
    if direction_info['direction'] in ['EGRESS', 'BOTH']:
        perim = direction_info.get('source_perimeter')

        egress_from = {"identity_type": ""}

        if service_account:
            egress_from["identities"] = [f"serviceAccount:{service_account}"]

        egress_to = {}
        if dest_project:
            egress_to["resources"] = [f"projects/{dest_project}"]
        if operations:
            egress_to["operations"] = operations

        rule = {
            "perimeter": perim,
            "direction": "EGRESS",
            "from": egress_from,
            "to": egress_to
        }

        rules.append(rule)

    return {'rules': rules}


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Convert VPC SC audit log to auto-generated rules'
    )
    parser.add_argument(
        '--audit-log-json',
        required=True,
        help='Audit log JSON (from Cloud Logging)'
    )
    parser.add_argument(
        '--router-file',
        default='router.yml',
        help='Path to router.yml'
    )
    parser.add_argument(
        '--project-cache',
        default='vpc_sc_project_cache.json',
        help='Path to project cache'
    )
    parser.add_argument(
        '--tlm-id',
        help='TLM ID (required if using public IP for ingress)'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output JSON file'
    )

    args = parser.parse_args()

    # Parse audit log
    audit_log_json = parse_audit_log_json(args.audit_log_json)
    if not audit_log_json:
        result = {
            'error': 'Invalid audit log JSON',
            'help': 'Must provide valid JSON audit log from Cloud Logging'
        }
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        return

    # Extract information
    parsed = extract_from_audit_log(audit_log_json)

    # Load configuration
    router_config = load_router_config(args.router_file)
    project_cache = load_project_cache(args.project_cache)

    # Determine ownership (check parsed data first, then projects)
    # For cross-perimeter scenarios, the audit log may already have perimeter info
    src_perim = parsed.get('source_perimeter')
    dst_perim = parsed.get('dest_perimeter')

    # If not in audit log, derive from projects
    if not src_perim and parsed['source_project']:
        src_perim = determine_perimeter_ownership(
            parsed['source_project'],
            project_cache,
            router_config
        )

    if not dst_perim and parsed['dest_project']:
        dst_perim = determine_perimeter_ownership(
            parsed['dest_project'],
            project_cache,
            router_config
        )

    # Also use the perimeter from the violation itself (where error occurred)
    if not src_perim and not dst_perim and parsed.get('perimeter'):
        # If we don't have source/dest but we have the perimeter where violation occurred,
        # this is where rules need to be applied
        if parsed['violation_type'] == 'INGRESS':
            dst_perim = parsed['perimeter']
        elif parsed['violation_type'] == 'EGRESS':
            src_perim = parsed['perimeter']

    # Auto-detect direction
    direction_info = auto_detect_direction(src_perim, dst_perim)

    # Add perimeter info for TLM validation
    direction_info['source_perimeter'] = src_perim
    direction_info['dest_perimeter'] = dst_perim

    # Debug: Log extraction results for troubleshooting
    import sys
    debug_info = {
        'extracted_service': parsed.get('service'),
        'violation_type_from_log': parsed.get('violation_type'),
        'source_project': parsed.get('source_project'),
        'dest_project': parsed.get('dest_project'),
        'source_perimeter': src_perim,
        'dest_perimeter': dst_perim,
        'detected_direction': direction_info.get('direction'),
        'public_ip': parsed.get('is_public_ip'),
        'caller_ip': parsed.get('caller_ip'),
    }
    print(f"\n📋 DEBUG: Direction Detection\n{json.dumps(debug_info, indent=2)}\n", file=sys.stderr)

    # Validate TLM requirement
    tlm_validation = validate_tlm_requirement(parsed, direction_info)

    # Check if TLM is required but not provided
    if tlm_validation['requires'] and not args.tlm_id:
        result = {
            'error': 'TLM ID required',
            'reason': tlm_validation['reason'],
            'help': 'Please provide TLM ID using --tlm-id flag'
        }
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        return

    # Generate rules
    rules_result = generate_hcl_rules(parsed, direction_info, args.tlm_id)

    if 'error' in rules_result:
        result = rules_result
    else:
        result = {
            'success': True,
            'request_summary': {
                'source': {
                    'ip': parsed.get('caller_ip'),
                    'is_public': parsed.get('is_public_ip'),
                    'project': parsed.get('source_project'),
                    'perimeter': src_perim
                },
                'destination': {
                    'project': parsed.get('dest_project'),
                    'perimeter': dst_perim
                },
                'service': parsed.get('service'),
                'method': parsed.get('method'),
                'service_account': parsed.get('service_account')
            },
            'direction_info': direction_info,
            'tlm_validation': tlm_validation,
            'rules': rules_result.get('rules', [])
        }

    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)


if __name__ == '__main__':
    main()
