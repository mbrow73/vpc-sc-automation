# Enterprise Audit Log Examples

This document provides comprehensive, realistic Cloud Audit Log examples that the VPC SC automation system can now handle.

The system now robustly handles:
- ✅ Multiple GCP services (BigQuery, Storage, Compute, SQL, Pub/Sub, Dataflow, etc.)
- ✅ Cross-perimeter violations (with real nested ingressFrom/ingressTo structure)
- ✅ Complex enterprise scenarios
- ✅ Multiple violation types in one log
- ✅ Real project numbers from vpc_sc_project_cache.json
- ✅ Both simplified (targetResource) and real (nested) Google audit log formats

---

## Example 1: On-Premises to BigQuery (Public IP INGRESS)

**Scenario**: On-premises application querying BigQuery via public IP, attempting to access project in test-perim-a

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
    "resourceName": "projects/1111111111/datasets/public_data"
  },
  "resource": {
    "type": "bigquery.googleapis.com/Project",
    "labels": {
      "project_id": "1111111111"
    }
  },
  "timestamp": "2025-11-20T14:32:15Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Permission denied. Access to BigQuery dataset denied by organization policy."
  },
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111111",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "sourceResource": ""
        },
        "ingressTo": {
          "resource": "projects/1111111111/datasets/public_data"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: BigQuery
- Direction: INGRESS
- Source: Public IP (203.0.113.42) - EXTERNAL
- Destination: test-perim-a (project 1111111111)
- **TLM Required**: YES (public IP + INGRESS)

---

## Example 2: Cross-Perimeter Data Pipeline (BOTH)

**Scenario**: Data pipeline in test-perim-a accessing analytics in test-perim-b

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
    "resourceName": "projects/2222222222/datasets/analytics/tables"
  },
  "resource": {
    "type": "bigquery.googleapis.com/Project",
    "labels": {
      "project_id": "2222222222"
    }
  },
  "timestamp": "2025-11-20T09:15:42Z",
  "severity": "ERROR",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/987654321/servicePerimeters/test-perim-b",
    "servicePerimeterResource": "projects/2222222222",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "sourceResource": "projects/1111111111"
        },
        "ingressTo": {
          "resource": "projects/2222222222/datasets/analytics"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: BigQuery
- Direction: INGRESS (to test-perim-b) but source is internal (test-perim-a)
- Source: Project 1111111111 (in test-perim-a)
- Destination: Project 2222222222 (in test-perim-b)
- **Result**: 2 PRs created
  - PR 1: test-perim-a (EGRESS rule)
  - PR 2: test-perim-b (INGRESS rule)
- **TLM Required**: NO (internal-to-internal)

---

## Example 3: Cloud Storage Access from Private Network

**Scenario**: GKE cluster in test-perim-a accessing Cloud Storage bucket in same perimeter

```json
{
  "protoPayload": {
    "serviceName": "storage.googleapis.com",
    "methodName": "storage.objects.get",
    "authenticationInfo": {
      "principalEmail": "k8s-workload-sa@1111111112.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.128.0.50",
      "callerNetwork": "projects/1111111112/global/networks/gke-network"
    },
    "resourceName": "projects/1111111112/buckets/sensitive-data"
  },
  "resource": {
    "type": "storage.googleapis.com/Bucket",
    "labels": {
      "project_id": "1111111112",
      "bucket_name": "sensitive-data"
    }
  },
  "timestamp": "2025-11-20T11:45:20Z",
  "severity": "ERROR",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111112",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "sourceResource": "projects/1111111112"
        },
        "ingressTo": {
          "resource": "projects/1111111112/buckets/sensitive-data"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: Cloud Storage
- Direction: INGRESS
- Source: Private IP (10.128.0.50) from same project/perimeter
- **TLM Required**: NO (private IP + internal)

---

## Example 4: Third-Party SaaS Integration (EGRESS)

**Scenario**: Cloud Function in test-perim-a exporting data to external SaaS platform

```json
{
  "protoPayload": {
    "serviceName": "cloudfunctions.googleapis.com",
    "methodName": "cloudfunctions.create",
    "authenticationInfo": {
      "principalEmail": "cloud-functions@1111111113.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.0.0.0",
      "callerNetwork": "projects/1111111113/global/networks/default"
    },
    "resourceName": "projects/1111111113/locations/us-central1/functions/export-to-datadog"
  },
  "resource": {
    "type": "cloudfunctions.googleapis.com/Function",
    "labels": {
      "project_id": "1111111113",
      "function_name": "export-to-datadog"
    }
  },
  "timestamp": "2025-11-20T13:20:10Z",
  "severity": "ERROR",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111113",
    "egressViolations": [
      {
        "egressFrom": {
          "identity": "serviceAccount:cloud-functions@1111111113.iam.gserviceaccount.com",
          "sourceResource": "projects/1111111113"
        },
        "egressTo": {
          "resource": "external-service"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: Cloud Functions
- Direction: EGRESS
- Source: test-perim-a (project 1111111113)
- Destination: EXTERNAL (third-party)
- **TLM Required**: YES (EGRESS to external)

---

## Example 5: Cloud SQL from GCP Project (PRIVATE INGRESS)

**Scenario**: Application server in test-perim-b accessing Cloud SQL instance in test-perim-a

```json
{
  "protoPayload": {
    "serviceName": "cloudsql.googleapis.com",
    "methodName": "cloudsqlinstances.get",
    "authenticationInfo": {
      "principalEmail": "app-server@2222222223.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.0.1.15",
      "callerNetwork": "projects/2222222223/global/networks/app-network"
    },
    "resourceName": "projects/1111111111/instances/prod-postgres-db"
  },
  "resource": {
    "type": "cloudsql.googleapis.com/Instance",
    "labels": {
      "project_id": "1111111111",
      "database_id": "prod:postgres-db"
    }
  },
  "timestamp": "2025-11-20T10:05:33Z",
  "severity": "ERROR",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/987654321/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111111",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "sourceResource": "projects/2222222223"
        },
        "ingressTo": {
          "resource": "projects/1111111111/cloudsql/postgres-primary"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: Cloud SQL
- Direction: INGRESS (to test-perim-a) from test-perim-b
- Source: Project 2222222223 (test-perim-b)
- Destination: Project 1111111111 (test-perim-a)
- **TLM Required**: NO (private IP + internal-to-internal)

---

## Example 6: Pub/Sub Cross-Project (BOTH)

**Scenario**: Event publishing service in test-perim-a, subscribers in test-perim-b

```json
{
  "protoPayload": {
    "serviceName": "pubsub.googleapis.com",
    "methodName": "google.pubsub.v1.Publisher.Publish",
    "authenticationInfo": {
      "principalEmail": "events-publisher@1111111111.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.1.0.20",
      "callerNetwork": "projects/1111111111/global/networks/events-network"
    },
    "resourceName": "projects/2222222222/topics/order-events"
  },
  "resource": {
    "type": "pubsub.googleapis.com/Topic",
    "labels": {
      "project_id": "2222222222",
      "topic_id": "order-events"
    }
  },
  "timestamp": "2025-11-20T15:42:08Z",
  "severity": "ERROR",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-b",
    "servicePerimeterResource": "projects/2222222222",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "sourceResource": "projects/1111111111"
        },
        "ingressTo": {
          "resource": "projects/2222222222/topics/order-events"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: Pub/Sub
- Direction: INGRESS (to test-perim-b) from test-perim-a
- Source: test-perim-a (project 1111111111)
- Destination: test-perim-b (project 2222222222)
- **Result**: 2 PRs
  - EGRESS rule in test-perim-a
  - INGRESS rule in test-perim-b
- **TLM Required**: NO (internal-to-internal)

---

## Example 7: Dataflow Job (Complex Multi-Service)

**Scenario**: Dataflow pipeline in test-perim-a accessing BigQuery in test-perim-b

```json
{
  "protoPayload": {
    "serviceName": "dataflow.googleapis.com",
    "methodName": "projects.locations.jobs.create",
    "authenticationInfo": {
      "principalEmail": "dataflow-worker@1111111112.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.2.0.100",
      "callerNetwork": "projects/1111111112/global/networks/dataflow-network"
    },
    "resourceName": "projects/2222222223/locations/us-central1"
  },
  "resource": {
    "type": "dataflow.googleapis.com/Job",
    "labels": {
      "project_id": "2222222223",
      "job_id": "daily-etl-pipeline"
    }
  },
  "timestamp": "2025-11-20T02:30:45Z",
  "severity": "ERROR",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/987654321/servicePerimeters/test-perim-b",
    "servicePerimeterResource": "projects/2222222223",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "sourceResource": "projects/1111111112"
        },
        "ingressTo": {
          "resource": "projects/2222222223/locations/us-central1"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: Dataflow
- Direction: INGRESS (to test-perim-b) from test-perim-a
- Source: test-perim-a (project 1111111112)
- Destination: test-perim-b (project 2222222223)
- **Result**: 2 PRs for cross-perimeter access

---

## Example 8: Container Registry (Private IP, No TLM)

**Scenario**: GKE in test-perim-a pulling container images from Artifact Registry in same perimeter

```json
{
  "protoPayload": {
    "serviceName": "artifactregistry.googleapis.com",
    "methodName": "google.devtools.artifactregistry.v1.ArtifactRegistry.GetRepository",
    "authenticationInfo": {
      "principalEmail": "gke-nodes@1111111113.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.4.0.50",
      "callerNetwork": "projects/1111111113/global/networks/gke-network"
    },
    "resourceName": "projects/1111111113/locations/us/repositories/app-images"
  },
  "resource": {
    "type": "artifactregistry.googleapis.com/Repository",
    "labels": {
      "project_id": "1111111113"
    }
  },
  "timestamp": "2025-11-20T08:15:22Z",
  "severity": "ERROR",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111113",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "sourceResource": "projects/1111111113"
        },
        "ingressTo": {
          "resource": "projects/1111111113/repositories/app-images"
        }
      }
    ]
  }
}
```

**System Detection**:
- Service: Artifact Registry
- Direction: INGRESS
- Source: Private IP (internal, same perimeter)
- **TLM Required**: NO

---

## How the System Now Works

### Real Audit Log Format Handling
The system extracts data from realistic Google Cloud audit logs with nested violation structures:
1. **Metadata extraction**: Tries `servicePerimeter` (new format) before `servicePerimeterName` (old format)
2. **Ingress violations**: Extracts source from `ingressFrom.sourceResource`, destination from `ingressTo.resource`
3. **Egress violations**: Extracts destination from `egressTo.resource`
4. **Access denial violations**: Handles either ingressTo/egressTo structure or falls back to targetResource

### Robust Project Extraction
The system uses multiple extraction strategies:
1. `callerNetwork` - best source (includes project + network)
2. `principalEmail` - extract project from service account email
3. `resource.labels.project_id` - fallback to resource labels
4. `resourceName` - try to parse from resource path
5. `ingressFrom.sourceResource` / `ingressTo.resource` - extract from violation nested structure

### Perimeter Detection
- Primary: `servicePerimeter` in metadata (real format)
- Secondary: `servicePerimeterName` in securityPolicyInfo (old format)
- Fallback: Lookup via project cache

### Direction Detection
- **INGRESS**: External trying to access internal (or different internal perimeter)
- **EGRESS**: Internal trying to access external (or different internal perimeter)
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
1. Extract all details from real Google audit log format
2. Determine perimeter ownership using project cache
3. Auto-detect direction based on source/destination
4. Validate TLM requirements
5. Generate correct rules for each affected perimeter
