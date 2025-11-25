# Enterprise Audit Log Examples

This document provides comprehensive, **production-realistic** Cloud Audit Log examples that demonstrate all VPC SC automation features. All examples include the full structure found in actual Google Cloud audit logs.

## Feature Coverage Matrix

| Example | Service | Direction | Feature(s) Demonstrated | TLM Required |
|---------|---------|-----------|------------------------|--------------|
| 1 | BigQuery | INGRESS | Public IP detection, TLM requirement, access level creation | YES |
| 2 | BigQuery | BOTH | Cross-perimeter INGRESS+EGRESS, direction auto-detection | NO |
| 3 | Cloud Storage | INGRESS | Private IP, same-perimeter internal access | NO |
| 4 | Cloud Functions | EGRESS | External destination (unsupported service), wildcard methods | YES |
| 5 | Cloud SQL | INGRESS | Cross-perimeter, method validation for unsupported service | NO |
| 6 | Pub/Sub | INGRESS | Supported service with correct method restriction | NO |
| 7 | Dataflow | INGRESS | Unsupported service → wildcard methods ("*"), internal IP | NO |
| 8 | Artifact Registry | INGRESS | Supported service, repository-level resources | NO |

**Feature Legend:**
- **Public IP Detection**: Identifies external callers, triggers TLM requirement
- **Cross-Perimeter**: Generates BOTH INGRESS+EGRESS rules (Scenario 5)
- **Method Validation**: Validates against official VPC SC supported methods list
- **Wildcard Fallback**: Unsupported services use "*" instead of specific methods
- **Supported Services**: BigQuery, Cloud Storage, Compute, Container Registry, IAM, Cloud Logging, Pub/Sub, Cloud Run, Artifact Registry, Cloud Resource Manager
- **Unsupported Services**: Cloud SQL, Dataflow, Spanner, Firestore, Cloud Functions (use method="*")

---

## Example 1: On-Premises to BigQuery (Public IP INGRESS)

**Scenario**: On-premises application querying BigQuery via public IP, request blocked by VPC-SC

```json
{
  "protoPayload": {
    "serviceName": "bigquery.googleapis.com",
    "methodName": "google.cloud.bigquery.v2.JobService.InsertJob",
    "authenticationInfo": {
      "principalEmail": "bigquery-user@on-prem-corp.com"
    },
    "requestMetadata": {
      "callerIp": "8.8.4.42",
      "sourceAttributes": {},
      "userAgent": "google-cloud-bigquery/1.25.0"
    },
    "resourceName": "projects/1111111111/datasets/public_data"
  },
  "resource": {
    "type": "audited_resource",
    "labels": {
      "service": "bigquery.googleapis.com",
      "method": "jobservice.insert",
      "project_id": "1111111111"
    }
  },
  "timestamp": "2025-11-20T14:32:15Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Ingress violation from external network."
  },
  "logName": "projects/1111111111/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "1rh8s2m0k3f5g7h9",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111111",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "ANY_IDENTITY",
          "identity": "bigquery-user@on-prem-corp.com",
          "sourceNetwork": "8.8.4.0/24"
        },
        "ingressTo": {
          "resource": "projects/1111111111/datasets/public_data",
          "operations": [
            {
              "service": "bigquery.googleapis.com",
              "method": "jobservice.insert"
            }
          ]
        },
        "violationReason": "NETWORK_NOT_IN_SERVICE_PERIMETER_ACCESS_LEVEL"
      }
    ]
  }
}
```

**System Detection**:
- Service: BigQuery
- Method: google.cloud.bigquery.v2.JobService.InsertJob
- Direction: INGRESS
- Source: Public IP (8.8.4.42) - EXTERNAL
- Destination: test-perim-a (project 1111111111)
- Violation Reason: NETWORK_NOT_IN_SERVICE_PERIMETER_ACCESS_LEVEL
- **TLM Required**: YES (public IP + INGRESS)

---

## Example 2: Cross-Perimeter Data Pipeline (BOTH)

**Scenario**: Data pipeline in test-perim-a accessing analytics in test-perim-b, blocked at destination

```json
{
  "protoPayload": {
    "serviceName": "bigquery.googleapis.com",
    "methodName": "google.cloud.bigquery.v2.TableService.GetTable",
    "authenticationInfo": {
      "principalEmail": "dataflow-sa@1111111111.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.0.0.5",
      "callerNetwork": "projects/1111111111/global/networks/internal",
      "userAgent": "google-cloud-dataflow/apache-beam-2.45.0"
    },
    "resourceName": "projects/2222222222/datasets/analytics/tables/events"
  },
  "resource": {
    "type": "audited_resource",
    "labels": {
      "service": "bigquery.googleapis.com",
      "method": "tabledata.get",
      "project_id": "2222222222"
    }
  },
  "timestamp": "2025-11-20T09:15:42Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Ingress violation from another service perimeter."
  },
  "logName": "projects/2222222222/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "2ah9b1c4d6e8f0g2",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/987654321/servicePerimeters/test-perim-b",
    "servicePerimeterResource": "projects/2222222222",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "SERVICE_IDENTITY",
          "identity": "dataflow-sa@1111111111.iam.gserviceaccount.com",
          "sourceResource": "projects/1111111111"
        },
        "ingressTo": {
          "resource": "projects/2222222222/datasets/analytics",
          "operations": [
            {
              "service": "bigquery.googleapis.com",
              "method": "tabledata.list"
            }
          ]
        },
        "violationReason": "IDENTITY_NOT_IN_SERVICE_PERIMETER"
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
- Violation Reason: IDENTITY_NOT_IN_SERVICE_PERIMETER
- **Result**: 2 PRs created
  - PR 1: test-perim-a (EGRESS rule)
  - PR 2: test-perim-b (INGRESS rule)
- **TLM Required**: NO (internal-to-internal)

---

## Example 3: Cloud Storage Access from Private Network

**Scenario**: GKE cluster in test-perim-a accessing Cloud Storage bucket in same perimeter, access allowed

```json
{
  "protoPayload": {
    "serviceName": "storage.googleapis.com",
    "methodName": "google.storage.v1.storage.objects.get",
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
    "type": "audited_resource",
    "labels": {
      "service": "storage.googleapis.com",
      "method": "storage.objects.get",
      "bucket_name": "sensitive-data",
      "project_id": "1111111112"
    }
  },
  "timestamp": "2025-11-20T11:45:20Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Access denied by perimeter policy."
  },
  "logName": "projects/1111111112/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "3bg7c5d2e9f1g3h5",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111112",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "SERVICE_IDENTITY",
          "identity": "k8s-workload-sa@1111111112.iam.gserviceaccount.com",
          "sourceResource": "projects/1111111112"
        },
        "ingressTo": {
          "resource": "projects/1111111112/buckets/sensitive-data",
          "operations": [
            {
              "service": "storage.googleapis.com",
              "method": "storage.objects.get"
            }
          ]
        },
        "violationReason": "ACCESS_DENIED_BY_POLICY"
      }
    ]
  }
}
```

**System Detection**:
- Service: Cloud Storage
- Direction: INGRESS
- Source: Private IP (10.128.0.50) from same project/perimeter
- Violation Reason: ACCESS_DENIED_BY_POLICY
- **TLM Required**: NO (private IP + internal)

---

## Example 4: Third-Party SaaS Integration (EGRESS)

**Scenario**: Cloud Function in test-perim-a attempting to export data to external SaaS platform

```json
{
  "protoPayload": {
    "serviceName": "cloudfunctions.googleapis.com",
    "methodName": "google.cloud.functions.v1.CloudFunctionsService.CreateFunction",
    "authenticationInfo": {
      "principalEmail": "cloud-functions@1111111113.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.0.0.100",
      "callerNetwork": "projects/1111111113/global/networks/default"
    },
    "resourceName": "projects/1111111113/locations/us-central1/functions/export-to-datadog"
  },
  "resource": {
    "type": "audited_resource",
    "labels": {
      "service": "cloudfunctions.googleapis.com",
      "method": "cloudfunctions.create",
      "function_name": "export-to-datadog",
      "project_id": "1111111113"
    }
  },
  "timestamp": "2025-11-20T13:20:10Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Egress to unapproved external service."
  },
  "logName": "projects/1111111113/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "4dh8e6f3g0h2i4j6",
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
          "resource": "//datadog.com/services/monitoring-service",
          "operations": [
            {
              "service": "datadog.com",
              "method": "put.metrics"
            }
          ]
        },
        "violationReason": "DESTINATION_NOT_IN_SERVICE_PERIMETER_ALLOWED_RESOURCES"
      }
    ]
  }
}
```

**System Detection**:
- Service: Cloud Functions
- Direction: EGRESS
- Source: test-perim-a (project 1111111113)
- Destination: EXTERNAL (third-party datadog.com)
- Violation Reason: DESTINATION_NOT_IN_SERVICE_PERIMETER_ALLOWED_RESOURCES
- **TLM Required**: YES (EGRESS to external)

---

## Example 5: Cloud SQL Cross-Perimeter Access

**Scenario**: Application server in test-perim-b accessing Cloud SQL instance in test-perim-a

```json
{
  "protoPayload": {
    "serviceName": "cloudsql.googleapis.com",
    "methodName": "cloudsql.instances.get",
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
    "type": "audited_resource",
    "labels": {
      "service": "cloudsql.googleapis.com",
      "method": "cloudsql.instances.get",
      "instance_name": "prod-postgres-db",
      "project_id": "1111111111"
    }
  },
  "timestamp": "2025-11-20T10:05:33Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Ingress from cross-perimeter identity."
  },
  "logName": "projects/1111111111/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "5ei9f7g4h1i3j5k7",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/987654321/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111111",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "SERVICE_IDENTITY",
          "identity": "app-server@2222222223.iam.gserviceaccount.com",
          "sourceResource": "projects/2222222223"
        },
        "ingressTo": {
          "resource": "projects/1111111111/instances/prod-postgres-db",
          "operations": [
            {
              "service": "cloudsql.googleapis.com",
              "method": "instances.get"
            }
          ]
        },
        "violationReason": "IDENTITY_NOT_IN_SERVICE_PERIMETER"
      }
    ]
  }
}
```

**System Detection**:
- Service: Cloud SQL (not in VPC SC supported methods list)
- Direction: INGRESS (to test-perim-a) from test-perim-b
- Source: Project 2222222223 (test-perim-b)
- Destination: Project 1111111111 (test-perim-a)
- Violation Reason: IDENTITY_NOT_IN_SERVICE_PERIMETER
- **Method Validation**: `cloudsql.instances.get` → **Not supported in VPC SC** → Falls back to `"*"`
- **Generated Rule**: Method restriction set to `"*"` (all Cloud SQL methods allowed)
- **TLM Required**: NO (private IP + internal-to-internal)
- **Note**: Cloud SQL method restrictions are not officially supported by VPC SC. The system safely falls back to allowing all methods.

---

## Example 6: Pub/Sub Cross-Project

**Scenario**: Event publishing service in test-perim-a attempting to publish to subscribers in test-perim-b

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
    "type": "audited_resource",
    "labels": {
      "service": "pubsub.googleapis.com",
      "method": "publisher.publish",
      "topic_id": "order-events",
      "project_id": "2222222222"
    }
  },
  "timestamp": "2025-11-20T15:42:08Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Publisher identity not authorized to publish to topic."
  },
  "logName": "projects/2222222222/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "6fj0g8h5i2j4k6l8",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-b",
    "servicePerimeterResource": "projects/2222222222",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "SERVICE_IDENTITY",
          "identity": "events-publisher@1111111111.iam.gserviceaccount.com",
          "sourceResource": "projects/1111111111"
        },
        "ingressTo": {
          "resource": "projects/2222222222/topics/order-events",
          "operations": [
            {
              "service": "pubsub.googleapis.com",
              "method": "publisher.publish"
            }
          ]
        },
        "violationReason": "IDENTITY_NOT_IN_SERVICE_PERIMETER"
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
- Violation Reason: IDENTITY_NOT_IN_SERVICE_PERIMETER
- **Result**: 2 PRs
  - EGRESS rule in test-perim-a
  - INGRESS rule in test-perim-b
- **TLM Required**: NO (internal-to-internal)

---

## Example 7: Dataflow Job Pipeline

**Scenario**: Dataflow pipeline in test-perim-a attempting to access BigQuery in test-perim-b

```json
{
  "protoPayload": {
    "serviceName": "dataflow.googleapis.com",
    "methodName": "google.dataflow.v1beta3.FlexTemplatesService.LaunchFlexTemplate",
    "authenticationInfo": {
      "principalEmail": "dataflow-worker@1111111112.iam.gserviceaccount.com"
    },
    "requestMetadata": {
      "callerIp": "10.2.0.100",
      "callerNetwork": "projects/1111111112/global/networks/dataflow-network"
    },
    "resourceName": "projects/2222222223/locations/us-central1/jobs"
  },
  "resource": {
    "type": "audited_resource",
    "labels": {
      "service": "dataflow.googleapis.com",
      "method": "projects.locations.jobs.create",
      "job_id": "daily-etl-pipeline",
      "project_id": "2222222223"
    }
  },
  "timestamp": "2025-11-20T02:30:45Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Dataflow worker cannot access cross-perimeter resources."
  },
  "logName": "projects/2222222223/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "7gk1h9i6j3k5l7m9",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/987654321/servicePerimeters/test-perim-b",
    "servicePerimeterResource": "projects/2222222223",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "SERVICE_IDENTITY",
          "identity": "dataflow-worker@1111111112.iam.gserviceaccount.com",
          "sourceResource": "projects/1111111112"
        },
        "ingressTo": {
          "resource": "projects/2222222223/locations/us-central1",
          "operations": [
            {
              "service": "dataflow.googleapis.com",
              "method": "jobs.create"
            }
          ]
        },
        "violationReason": "IDENTITY_NOT_IN_SERVICE_PERIMETER"
      }
    ]
  }
}
```

**System Detection**:
- Service: Dataflow (not in VPC SC supported methods list)
- Direction: INGRESS (to test-perim-b) from test-perim-a
- Source: test-perim-a (project 1111111112)
- Destination: test-perim-b (project 2222222223)
- Violation Reason: IDENTITY_NOT_IN_SERVICE_PERIMETER
- **Method Validation**: `google.dataflow.v1beta3.FlexTemplatesService.LaunchFlexTemplate` → **Not supported in VPC SC** → Falls back to `"*"`
- **Generated Rules**:
  - EGRESS from test-perim-a with method restriction `"*"` (all Dataflow methods)
  - INGRESS to test-perim-b with method restriction `"*"` (all Dataflow methods)
- **TLM Required**: NO (internal IP + internal-to-internal)
- **Note**: Dataflow method restrictions are not officially supported by VPC SC. The system automatically falls back to allowing all methods while maintaining identity and resource restrictions.

---

## Example 8: Container Registry Internal Access

**Scenario**: GKE in test-perim-a pulling container images from Artifact Registry in same perimeter (no violation, shown for reference)

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
    "type": "audited_resource",
    "labels": {
      "service": "artifactregistry.googleapis.com",
      "method": "artifactregistry.getrepository",
      "repository": "app-images",
      "project_id": "1111111113"
    }
  },
  "timestamp": "2025-11-20T08:15:22Z",
  "severity": "ERROR",
  "status": {
    "code": 7,
    "message": "Policy violation. Request is prohibited by organization's policy. VPC Service Controls: Access denied by repository policy."
  },
  "logName": "projects/1111111113/logs/cloudaudit.googleapis.com%2Fpolicy",
  "insertId": "8hl2i0j7k4l6m8n0",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata",
    "violationReason": "SERVICE_PERIMETER_RESTRICTION",
    "servicePerimeter": "accessPolicies/123456789/servicePerimeters/test-perim-a",
    "servicePerimeterResource": "projects/1111111113",
    "ingressViolations": [
      {
        "ingressFrom": {
          "identityType": "SERVICE_IDENTITY",
          "identity": "gke-nodes@1111111113.iam.gserviceaccount.com",
          "sourceResource": "projects/1111111113"
        },
        "ingressTo": {
          "resource": "projects/1111111113/repositories/app-images",
          "operations": [
            {
              "service": "artifactregistry.googleapis.com",
              "method": "artifactregistry.getrepository"
            }
          ]
        },
        "violationReason": "ACCESS_DENIED_BY_POLICY"
      }
    ]
  }
}
```

**System Detection**:
- Service: Artifact Registry
- Direction: INGRESS
- Source: Private IP (internal, same perimeter)
- Violation Reason: ACCESS_DENIED_BY_POLICY
- **TLM Required**: NO

---

## Realistic VPC-SC Violation Reason Values

The system now handles all realistic `violationReason` values found in production logs:

- `NETWORK_NOT_IN_SERVICE_PERIMETER_ACCESS_LEVEL` - External network/IP not in access level
- `IDENTITY_NOT_IN_SERVICE_PERIMETER` - Service account not in perimeter member list
- `DESTINATION_NOT_IN_SERVICE_PERIMETER_ALLOWED_RESOURCES` - Resource/service not allowed for egress
- `ACCESS_DENIED_BY_POLICY` - General policy enforcement
- `SERVICE_PERIMETER_RESTRICTION` - Generic perimeter violation
- `CLOUD_NAT_IP_NOT_IN_ACCESS_LEVEL` - Cloud NAT IP not in access level

---

## Log Entry Structure Reference

All examples include the complete, realistic audit log structure:

```
logName                 - Policy log sink (cloudaudit.googleapis.com%2Fpolicy)
insertId                - Unique identifier per log entry
timestamp               - When violation occurred
severity                - ERROR for all policy violations
status.code             - 7 (PERMISSION_DENIED)
status.message          - VPC-SC specific error message
resource.type           - "audited_resource"
protoPayload.methodName - Fully qualified (google.service.v1.Service.Method)
metadata.servicePerimeter - Full perimeter path
metadata.ingressViolations / egressViolations:
  - ingressFrom / egressFrom:
      identityType: "ANY_IDENTITY", "SERVICE_IDENTITY", etc.
      identity: The principal that triggered violation
      sourceResource: The source project (if internal)
      sourceNetwork: Network/IP info (if external)
  - ingressTo / egressTo:
      resource: The target resource
      operations: Service and method that failed
  - violationReason: Specific reason for the violation
```

---

## Advanced Features Demonstrated

### Scenario 4: Wildcard Projects for Unparseable Resources
When `targetResource` cannot be parsed to extract a specific project (e.g., organization-level IAM resources), the system automatically uses `"*"` (all resources) instead of failing. This ensures rules are created for edge cases while maintaining safety through identity and method restrictions.

**Example**: `resource: "//cloudresourcemanager.googleapis.com/organizations/123456"` → `resources = ["*"]`

### Scenario 5: Rule Deduplication with Method Merging
When multiple violations involve the same source identity and destination resource but different methods, the system intelligently deduplicates by merging methods into a single rule instead of creating separate rules.

**Example**:
- Existing rule: `from: {sa: "user@proj"}, to: {resources: ["projects/*"]}, methods: ["storage.get"]`
- New violation: Same from/to but needs `storage.list`
- Result: Single merged rule with `methods: ["storage.get", "storage.list"]`

## Testing the System

Use any of the above audit logs to test:

```bash
# Copy one of the JSON examples above and submit in GitHub issue
# Or test locally:

python3 .github/scripts/audit_log_to_rules.py \
  --audit-log-json "$(cat your-audit-log.json)" \
  --router-file router.yml \
  --project-cache .github/scripts/vpc_sc_project_cache.json \
  --output rules.json

# View results
cat rules.json | jq .
```

The system will:
1. **Extract** all details from realistic Google audit log format
2. **Parse** violation reasons (identity type, network type, resource restrictions)
3. **Determine** perimeter ownership using project cache
4. **Auto-detect** direction based on source/destination (Scenario 2: BOTH detection)
5. **Validate** TLM requirements for public IP INGRESS and all EGRESS to external
6. **Validate** method against official VPC SC supported list; fallback to "*" if unsupported
7. **Fallback** to wildcard resources ("*") if project cannot be extracted (Scenario 4)
8. **Deduplicate** similar rules by method merging (Scenario 5)
9. **Generate** correct rules for each affected perimeter
10. **Create** PRs with append-only changes (no destructive modifications)
