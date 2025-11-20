#!/usr/bin/env python3
"""
sync_project_cache_from_gcp.py

Sync project cache from actual GCP API (Access Context Manager).
Maps project numbers to perimeter names based on current GCP state.

USAGE:
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
  python3 .github/scripts/sync_project_cache_from_gcp.py

This script:
1. Reads router.yml to get list of perimeters and their policy_ids
2. Queries GCP Access Context Manager API for each perimeter
3. Extracts all projects from each perimeter
4. Builds project_number → perimeter_name mapping
5. Writes to .github/scripts/vpc_sc_project_cache.json
6. Returns exit code 0 if successful, non-zero if errors

For GitHub Actions:
- Set GOOGLE_APPLICATION_CREDENTIALS to the service account JSON key
- Add GCP secret to repository settings
- Workflow will auto-commit changes if cache updated
"""

import json
import os
import sys
import yaml
from datetime import datetime

try:
    from google.cloud import accesscontextmanager_v1
    from google.oauth2 import service_account
except ImportError:
    print("❌ Google Cloud libraries not installed.")
    print("   Install: pip install google-cloud-access-context-manager google-auth")
    sys.exit(1)


def load_router_config():
    """Load router.yml to get perimeter configs."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    router_path = os.path.join(script_dir, '..', '..', 'router.yml')

    if not os.path.exists(router_path):
        raise FileNotFoundError(f"router.yml not found at {router_path}")

    with open(router_path, 'r') as f:
        router = yaml.safe_load(f)

    return router


def get_projects_from_perimeter(policy_id, credentials=None):
    """
    Query GCP Access Context Manager API to get all projects in a perimeter.

    Args:
        policy_id: The numeric policy ID (e.g., "123456789")
        credentials: google.auth credentials object (optional)

    Returns:
        List of project numbers as strings
    """
    try:
        # Create client
        if credentials:
            client = accesscontextmanager_v1.AccessContextManagerClient(
                credentials=credentials
            )
        else:
            client = accesscontextmanager_v1.AccessContextManagerClient()

        # Get the policy
        policy_name = f"accessPolicies/{policy_id}"
        policy = client.get_access_policy(request={"name": policy_name})

        # Extract all projects from all perimeters
        projects = []
        if hasattr(policy, 'service_perimeters') and policy.service_perimeters:
            for perim in policy.service_perimeters:
                if hasattr(perim, 'status') and perim.status:
                    if hasattr(perim.status, 'resources') and perim.status.resources:
                        # Resources contain project IDs like "projects/1234567890"
                        for resource in perim.status.resources:
                            if resource.startswith('projects/'):
                                project_num = resource.replace('projects/', '')
                                projects.append(project_num)

        return list(set(projects))  # Remove duplicates

    except Exception as e:
        print(f"⚠️  Error querying policy {policy_id}: {str(e)}")
        return []


def sync_cache_from_gcp():
    """Main function to sync cache from GCP API."""

    try:
        # Load router config
        router = load_router_config()
        perimeters = router.get('perimeters', {})

        if not perimeters:
            print("❌ No perimeters found in router.yml")
            return False

        print(f"📍 Found {len(perimeters)} perimeters in router.yml")

        # Build project → perimeter mapping
        projects_map = {}

        for perim_name, perim_config in perimeters.items():
            policy_id = perim_config.get('policy_id')

            if not policy_id:
                print(f"⚠️  Perimeter '{perim_name}' missing policy_id, skipping")
                continue

            print(f"\n  Querying {perim_name} (policy_id: {policy_id})...")

            try:
                projects = get_projects_from_perimeter(str(policy_id))
                print(f"    ✅ Found {len(projects)} projects")

                for proj in projects:
                    projects_map[proj] = perim_name
                    print(f"       - {proj} → {perim_name}")

            except Exception as e:
                print(f"    ❌ Error: {str(e)}")
                # Continue with other perimeters

        if not projects_map:
            print("\n❌ No projects found in any perimeter")
            return False

        # Write cache
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cache_path = os.path.join(script_dir, 'vpc_sc_project_cache.json')

        cache = {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "cache_source": "gcp_api",
            "note": "Auto-generated from GCP Access Context Manager API. DO NOT EDIT MANUALLY.",
            "projects": projects_map
        }

        with open(cache_path, 'w') as f:
            json.dump(cache, f, indent=2)

        print(f"\n✅ Cache updated: {cache_path}")
        print(f"   Total projects: {len(projects_map)}")
        print(f"   Last updated: {cache['last_updated']}")

        return True

    except FileNotFoundError as e:
        print(f"❌ {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


if __name__ == '__main__':
    success = sync_cache_from_gcp()
    sys.exit(0 if success else 1)
