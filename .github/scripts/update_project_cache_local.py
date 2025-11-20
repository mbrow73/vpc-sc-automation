#!/usr/bin/env python3
"""
update_project_cache_local.py

Generate a local project cache for testing purposes.
Maps project numbers to perimeter names from router.yml.

USAGE:
  python3 .github/scripts/update_project_cache_local.py

This script:
1. Reads router.yml
2. Creates test project numbers for each perimeter
3. Writes to .github/scripts/vpc_sc_project_cache.json

For PRODUCTION, use sync_project_cache_from_gcp.py which queries the actual GCP API.
"""

import json
import os
from datetime import datetime

def generate_local_cache():
    """Generate a local test cache."""

    script_dir = os.path.dirname(os.path.abspath(__file__))
    router_path = os.path.join(script_dir, '..', '..', 'router.yml')
    cache_path = os.path.join(script_dir, 'vpc_sc_project_cache.json')

    # For local testing, create test project numbers for each perimeter
    # In production, these would come from GCP API

    test_projects = {
        "1111111111": "test-perim-a",
        "1111111112": "test-perim-a",
        "1111111113": "test-perim-a",
        "2222222222": "test-perim-b",
        "2222222223": "test-perim-b",
        "2222222224": "test-perim-b",
    }

    cache = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "cache_source": "local_test",
        "note": "For local testing only. In production, use gcloud to populate from GCP API.",
        "projects": test_projects
    }

    # Write cache
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2)

    print(f"✅ Local cache created: {cache_path}")
    print(f"   Last updated: {cache['last_updated']}")
    print(f"   Projects cached: {len(test_projects)}")

    return cache

if __name__ == '__main__':
    generate_local_cache()
