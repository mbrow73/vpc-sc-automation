# Enterprise Audit Log Examples

This document provides comprehensive, **production-realistic** Cloud Audit Log examples that the VPC SC automation system can handle. All examples include the full structure found in actual Google Cloud audit logs.

The system now robustly handles:
- ✅ Multiple GCP services (BigQuery, Storage, Compute, SQL, Pub/Sub, Dataflow, etc.)
- ✅ Cross-perimeter violations (with real nested ingressFrom/ingressTo structure)
- ✅ Complex enterprise scenarios with violation reasons
- ✅ Real project numbers from vpc_sc_project_cache.json
- ✅ Full log metadata (logName, insertId, status)
- ✅ Violation-specific denial reasons (NETWORK_NOT_IN_SERVICE_PERIMETER_ACCESS_LEVEL, etc.)

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
      "callerIp": "203.0.113.42",
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
          "sourceNetwork": "203.0.113.0/24"
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
- Source: Public IP (203.0.113.42) - EXTERNAL
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
- Service: Cloud SQL
- Direction: INGRESS (to test-perim-a) from test-perim-b
- Source: Project 2222222223 (test-perim-b)
- Destination: Project 1111111111 (test-perim-a)
- Violation Reason: IDENTITY_NOT_IN_SERVICE_PERIMETER
- **TLM Required**: NO (private IP + internal-to-internal)

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
- Service: Dataflow
- Direction: INGRESS (to test-perim-b) from test-perim-a
- Source: test-perim-a (project 1111111112)
- Destination: test-perim-b (project 2222222223)
- Violation Reason: IDENTITY_NOT_IN_SERVICE_PERIMETER
- **Result**: 2 PRs for cross-perimeter access

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
1. Extract all details from realistic Google audit log format
2. Parse violation reasons (identity type, network type, resource restrictions)
3. Determine perimeter ownership using project cache
4. Auto-detect direction based on source/destination
5. Validate TLM requirements
6. Generate correct rules for each affected perimeter
