# Enterprise Audit Log Examples

This document provides comprehensive, realistic Cloud Audit Log examples that the VPC SC automation system can now handle.

The system now robustly handles:
- ✅ Multiple GCP services (BigQuery, Storage, Compute, SQL, Pub/Sub, Dataflow, etc.)
- ✅ Cross-perimeter violations
- ✅ Complex enterprise scenarios
- ✅ Multiple violation types in one log
- ✅ Various source/destination identification patterns

---

## Example 1: On-Premises to BigQuery (Public IP INGRESS)

**Scenario**: On-premises application querying BigQuery via public IP

```json
{
  "protoPayload": {
    "serviceName": "bigquery.googleapis.com",
    "methodName": "jobservice.insert",
    "authenticationInfo": {
      "principalEmail": "bigquery-user@on-prem-corp.com"
    },
    "requestMetadata": {
      "callerIp": "203.0.113.42",
      "sourceAttributes": {}
    },
    "resourceName": "projects/prod-data-warehouse/datasets/public_data",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/123456789/servicePerimeters/prod-perimeter"
      },
      "ingressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "projects/987654321"
        }
      ]
    }
  },
  "resource": {
    "type": "bigquery.googleapis.com/Project",
    "labels": {
      "project_id": "987654321"
    }
  },
  "timestamp": "2025-11-20T14:32:15Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Permission denied. Access to BigQuery dataset denied by organization policy."
  }
}
```

**System Detection**:
- Service: BigQuery
- Direction: INGRESS
- Source: Public IP (203.0.113.42) - EXTERNAL
- Destination: test-perim (prod-perimeter)
- **TLM Required**: YES (public IP + INGRESS)

---

## Example 2: Cross-Perimeter Data Pipeline (BOTH)

**Scenario**: Data pipeline in data-lake-perimeter accessing analytics in bi-perimeter

```json
{
  "protoPayload": {
    "serviceName": "bigquery.googleapis.com",
    "methodName": "tabledata.list",
    "authenticationInfo": {
      "principalEmail": "dataflow-sa@1111111111.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.0.0.5",
      "callerNetwork": "projects/1111111111/global/networks/internal"
    },
    "resourceName": "projects/2222222222/datasets/analytics/tables",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/987654321/servicePerimeters/bi-perimeter"
      },
      "ingressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "projects/2222222222/datasets/analytics"
        }
      ]
    }
  },
  "resource": {
    "type": "bigquery.googleapis.com/Project",
    "labels": {
      "project_id": "2222222222"
    }
  },
  "timestamp": "2025-11-20T09:15:42Z",
  "severity": "ERROR"
}
```

**System Detection**:
- Service: BigQuery
- Direction: INGRESS (to bi-perimeter) but source is also internal
- Source: Project 1111111111 (in data-lake-perimeter)
- Destination: Project 2222222222 (in bi-perimeter)
- **Result**: 2 PRs created
  - PR 1: data-lake-perimeter (EGRESS rule)
  - PR 2: bi-perimeter (INGRESS rule)
- **TLM Required**: NO (internal-to-internal)

---

## Example 3: Cloud Storage Access from Private Network

**Scenario**: GKE cluster accessing Cloud Storage bucket

```json
{
  "protoPayload": {
    "serviceName": "storage.googleapis.com",
    "methodName": "storage.objects.get",
    "authenticationInfo": {
      "principalEmail": "k8s-workload-sa@4444444444.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.128.0.50",
      "callerNetwork": "projects/4444444444/global/networks/gke-network"
    },
    "resourceName": "projects/4444444444/buckets/sensitive-data",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/123456789/servicePerimeters/prod-perimeter"
      },
      "ingressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "projects/4444444444"
        }
      ]
    }
  },
  "resource": {
    "type": "storage.googleapis.com/Bucket",
    "labels": {
      "project_id": "4444444444",
      "bucket_name": "sensitive-data"
    }
  },
  "timestamp": "2025-11-20T11:45:20Z",
  "severity": "ERROR"
}
```

**System Detection**:
- Service: Cloud Storage
- Direction: INGRESS
- Source: Private IP (10.128.0.50) - but from same project/perimeter
- **TLM Required**: NO (private IP + internal)

---

## Example 4: Third-Party SaaS Integration (EGRESS)

**Scenario**: Cloud Function exporting data to external SaaS platform

```json
{
  "protoPayload": {
    "serviceName": "cloudfunctions.googleapis.com",
    "methodName": "cloudfunctions.create",
    "authenticationInfo": {
      "principalEmail": "cloud-functions@5555555555.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.0.0.0",
      "callerNetwork": "projects/5555555555/global/networks/default"
    },
    "resourceName": "projects/5555555555/locations/us-central1/functions/export-to-datadog",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/123456789/servicePerimeters/prod-perimeter"
      },
      "egressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "external-service"
        }
      ]
    }
  },
  "resource": {
    "type": "cloudfunctions.googleapis.com/Function",
    "labels": {
      "project_id": "5555555555",
      "function_name": "export-to-datadog"
    }
  },
  "timestamp": "2025-11-20T13:20:10Z",
  "severity": "ERROR"
}
```

**System Detection**:
- Service: Cloud Functions
- Direction: EGRESS
- Source: prod-perimeter
- Destination: EXTERNAL (third-party)
- **TLM Required**: YES (EGRESS to external)

---

## Example 5: Cloud SQL from GCP Project (PRIVATE INGRESS)

**Scenario**: Application server accessing Cloud SQL instance

```json
{
  "protoPayload": {
    "serviceName": "cloudsql.googleapis.com",
    "methodName": "cloudsqlinstances.get",
    "authenticationInfo": {
      "principalEmail": "app-server@3333333333.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.0.1.15",
      "callerNetwork": "projects/3333333333/global/networks/app-network"
    },
    "resourceName": "projects/3333333333/instances/prod-postgres-db",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/987654321/servicePerimeters/data-perimeter"
      },
      "ingressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "projects/3333333333/cloudsql/postgres-primary"
        }
      ]
    }
  },
  "resource": {
    "type": "cloudsql.googleapis.com/Instance",
    "labels": {
      "project_id": "3333333333",
      "database_id": "prod:postgres-db"
    }
  },
  "timestamp": "2025-11-20T10:05:33Z",
  "severity": "ERROR"
}
```

**System Detection**:
- Service: Cloud SQL
- Direction: INGRESS
- Source: Private IP (10.0.1.15)
- **TLM Required**: NO (private IP)

---

## Example 6: Pub/Sub Cross-Project (BOTH)

**Scenario**: Event publishing service in one perimeter, subscribers in another

```json
{
  "protoPayload": {
    "serviceName": "pubsub.googleapis.com",
    "methodName": "google.pubsub.v1.Publisher.Publish",
    "authenticationInfo": {
      "principalEmail": "events-publisher@6666666666.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.1.0.20",
      "callerNetwork": "projects/6666666666/global/networks/events-network"
    },
    "resourceName": "projects/7777777777/topics/order-events",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/123456789/servicePerimeters/events-perimeter"
      },
      "egressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "projects/7777777777/topics/order-events"
        }
      ]
    }
  },
  "resource": {
    "type": "pubsub.googleapis.com/Topic",
    "labels": {
      "project_id": "7777777777",
      "topic_id": "order-events"
    }
  },
  "timestamp": "2025-11-20T15:42:08Z",
  "severity": "ERROR"
}
```

**System Detection**:
- Service: Pub/Sub
- Direction: EGRESS (from events-perimeter to order-perimeter)
- Source: events-perimeter (6666666666)
- Destination: order-perimeter (7777777777)
- **Result**: 2 PRs
  - EGRESS rule in events-perimeter
  - INGRESS rule in order-perimeter
- **TLM Required**: NO (internal-to-internal)

---

## Example 7: Dataflow Job (Complex Multi-Service)

**Scenario**: Dataflow pipeline accessing multiple services

```json
{
  "protoPayload": {
    "serviceName": "dataflow.googleapis.com",
    "methodName": "projects.locations.jobs.create",
    "authenticationInfo": {
      "principalEmail": "dataflow-worker@8888888888.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.2.0.100",
      "callerNetwork": "projects/8888888888/global/networks/dataflow-network"
    },
    "resourceName": "projects/9999999999/locations/us-central1",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/987654321/servicePerimeters/analytics-perimeter"
      },
      "egressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "projects/8888888888"
        }
      ]
    }
  },
  "resource": {
    "type": "dataflow.googleapis.com/Job",
    "labels": {
      "project_id": "9999999999",
      "job_id": "daily-etl-pipeline"
    }
  },
  "timestamp": "2025-11-20T02:30:45Z",
  "severity": "ERROR"
}
```

**System Detection**:
- Service: Dataflow
- Direction: EGRESS
- Source: analytics-perimeter
- Destination: Project 8888888888 (pipeline-perimeter)
- **Result**: 2 PRs for cross-perimeter access

---

## Example 8: Container Registry (Private IP, No TLM)

**Scenario**: GKE pulling container images from Container Registry

```json
{
  "protoPayload": {
    "serviceName": "artifactregistry.googleapis.com",
    "methodName": "google.devtools.artifactregistry.v1.ArtifactRegistry.GetRepository",
    "authenticationInfo": {
      "principalEmail": "gke-nodes@1234512345.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.4.0.50",
      "callerNetwork": "projects/1234512345/global/networks/gke-network"
    },
    "resourceName": "projects/1234512345/locations/us/repositories/app-images",
    "metadata": {
      "securityPolicyInfo": {
        "servicePerimeterName": "accessPolicies/123456789/servicePerimeters/prod-perimeter"
      },
      "ingressViolations": [
        {
          "severity": "ERROR",
          "targetResource": "projects/1234512345/repositories/app-images"
        }
      ]
    }
  },
  "resource": {
    "type": "artifactregistry.googleapis.com/Repository",
    "labels": {
      "project_id": "1234512345"
    }
  },
  "timestamp": "2025-11-20T08:15:22Z",
  "severity": "ERROR"
}
```

**System Detection**:
- Service: Artifact Registry
- Direction: INGRESS
- Source: Private IP (internal)
- **TLM Required**: NO

---

## How the System Now Works

### Robust Project Extraction
The system tries multiple extraction strategies:
1. `callerNetwork` - best source (includes project + network)
2. `principalEmail` - extract project from service account email
3. `resource.labels.project_id` - fallback to resource labels
4. `resourceName` - try to parse from resource path

### Perimeter Detection
- Primary: `servicePerimeterName` in metadata (where violation occurred)
- Secondary: Extracted from `targetResource` in violations
- Fallback: Lookup via project cache

### Direction Detection
- **INGRESS**: External trying to access internal
- **EGRESS**: Internal trying to access external
- **BOTH**: Cross-perimeter (internal to different internal perimeter)
- **SKIP**: Same perimeter or out-of-scope

### TLM Requirement
- ✅ Public IP + INGRESS
- ✅ Any + EGRESS to external
- ❌ Private IP + INGRESS
- ❌ Internal-to-internal

---

## Testing the System

Use any of the above audit logs to test:

```bash
# Copy one of the JSON examples above and submit in GitHub issue
# Or test locally:

python3 .github/scripts/audit_log_to_rules.py \
  --audit-log-json '$(cat your-audit-log.json)' \
  --router-file router.yml \
  --project-cache .github/scripts/vpc_sc_project_cache.json \
  --output rules.json

# View results
cat rules.json | jq .
```

The system will:
1. Extract all details robustly
2. Determine perimeter ownership
3. Auto-detect direction
4. Validate TLM requirements
5. Generate correct rules for each perimeter
