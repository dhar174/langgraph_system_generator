# Review-only staging module. Nothing in repository CI applies this configuration.
terraform {
  required_version = ">= 1.13, < 2.0"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 7.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" { type = string }
variable "project_number" { type = string }
variable "region" { type = string }
variable "prefix" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.prefix))
    error_message = "Use 2 to 16 lowercase prefix characters for bounded service-account IDs."
  }
}
variable "bucket_name" { type = string }
variable "database_id" { type = string }
variable "image" {
  type = string
  validation {
    condition     = can(regex("@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Use a reviewed image digest built with LNF_INSTALL_GCP=true."
  }
}
variable "hmac_secret_id" { type = string }
variable "hmac_secret_version" {
  type = string
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.hmac_secret_version))
    error_message = "Pin an existing numeric Secret Manager version; never put secret payloads in state."
  }
}
variable "iap_members" {
  type = set(string)
  validation {
    condition     = length(var.iap_members) > 0 && alltrue([for member in var.iap_members : can(regex("^(user|group):[^ ]+$", member))])
    error_message = "Supply a nonempty reviewed IAP user/group allowlist."
  }
}
variable "enable_submissions" {
  type    = bool
  default = false
}
variable "enable_scheduler" {
  type    = bool
  default = false
}
variable "model_secrets" {
  type    = map(object({ secret_id = string, version = string }))
  default = {}
  validation {
    condition     = alltrue([for name, secret in var.model_secrets : (name == "OPENAI_API_KEY" || can(regex("^LNF_LLM_[A-Z0-9_]+_API_KEY$", name))) && can(regex("^[1-9][0-9]*$", secret.version))])
    error_message = "Only approved provider credentials with pinned numeric versions belong on workers."
  }
}
variable "trusted_endpoints" {
  type    = string
  default = "{}"
}
variable "provider_bindings" {
  type    = string
  default = "{\"openai-v1\":\"openai\"}"
}
variable "provider_refs" {
  type    = string
  default = "[\"openai-v1\"]"
}

locals {
  # Deterministic default run.app URLs. Staging must read back each actual URI
  # and token audience before activation; do not use custom domains for Tasks.
  worker_url      = "https://${var.prefix}-worker-${var.project_number}.${var.region}.run.app"
  maintenance_url = "https://${var.prefix}-maintenance-${var.project_number}.${var.region}.run.app"
  common = {
    LNF_JOB_BACKEND               = "firestore", LNF_JOB_GCP_PROJECT = var.project_id,
    LNF_JOB_FIRESTORE_DATABASE    = var.database_id, LNF_JOB_ARTIFACT_BUCKET = var.bucket_name,
    LNF_JOB_TASK_QUEUE            = "projects/${var.project_id}/locations/${var.region}/queues/${var.prefix}",
    LNF_WORKER_URL                = local.worker_url, LNF_WORKER_AUDIENCE = local.worker_url,
    LNF_TASK_SERVICE_ACCOUNT      = google_service_account.identity["tasks"].email,
    LNF_SCHEDULER_SERVICE_ACCOUNT = google_service_account.identity["scheduler"].email,
    LNF_LLM_ENDPOINT_POLICY       = "hosted", LNF_TRUSTED_LLM_ENDPOINTS = var.trusted_endpoints,
    LNF_JOB_PROVIDER_BINDINGS     = var.provider_bindings, LNF_JOB_PROVIDER_REFS = var.provider_refs,
    LNF_JOB_MAX_PENDING           = "100", LNF_JOB_MAX_ACTIVE = "2",
    LNF_JOB_OWNER_PENDING         = "5", LNF_JOB_OWNER_ACTIVE = "1",
    LNF_OUTPUT_BASE               = "/app/output", LNF_WORKER_OUTPUT_ROOT = "/app/output/worker",
    LANGCHAIN_TRACING_V2          = "false", LANGSMITH_TRACING = "false",
    # Keep object-only readback free of SDK background bucket metadata RPCs.
    DISABLE_GCS_PYTHON_CLIENT_OTEL_BUCKET_METADATA = "true"
  }
  api_env = merge(local.common, {
    LNF_API_ACCESS_MODE = "iap", LNF_DURABLE_SUBMISSIONS_ENABLED = tostring(var.enable_submissions),
    LNF_IAP_AUDIENCE    = "/projects/${var.project_number}/locations/${var.region}/services/${var.prefix}-api"
  })
}

resource "google_project_service" "required" {
  for_each           = toset(["run.googleapis.com", "iap.googleapis.com", "firestore.googleapis.com", "cloudtasks.googleapis.com", "cloudscheduler.googleapis.com", "secretmanager.googleapis.com", "storage.googleapis.com", "iamcredentials.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "identity" {
  for_each     = toset(["api", "worker", "maintenance", "tasks", "scheduler"])
  account_id   = "${var.prefix}-${each.key}"
  display_name = "${var.prefix} ${each.key} (durable jobs)"
}

resource "google_firestore_database" "jobs" {
  name                    = var.database_id
  location_id             = var.region
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "PREVENT"
  depends_on              = [google_project_service.required]
}

resource "google_project_iam_member" "database" {
  project  = var.project_id
  for_each = toset(["api", "worker", "maintenance"])
  role     = "roles/datastore.user"
  member   = "serviceAccount:${google_service_account.identity[each.key].email}"
  condition {
    title      = "dedicated_jobs_database"
    expression = "resource.name == 'projects/${var.project_id}/databases/${var.database_id}'"
  }
}

resource "google_firestore_index" "dispatch" {
  database    = google_firestore_database.jobs.name
  collection  = "dispatch"
  query_scope = "COLLECTION"
  fields {
    field_path = "deadline_at"
    order      = "ASCENDING"
  }
  fields {
    field_path = "due_at"
    order      = "ASCENDING"
  }
}

resource "google_firestore_field" "ttl" {
  for_each   = toset(["events", "idempotency", "dispatch"])
  database   = google_firestore_database.jobs.name
  collection = each.value
  field      = "delete_after"
  ttl_config {}
  index_config {}
}

# Parent inventory and run mappings have NO TTL: cleanup deletes events and
# exact-generation private objects before the job, run and dispatch documents.
resource "google_firestore_field" "exempt" {
  for_each   = { request = ["jobs", "request"], owner = ["jobs", "owner"], result = ["jobs", "result"], parent_ttl = ["jobs", "delete_after"], capacity = ["capacity", "jobs"] }
  database   = google_firestore_database.jobs.name
  collection = each.value[0]
  field      = each.value[1]
  index_config {}
}

resource "google_storage_bucket" "artifacts" {
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  # Acceptance-to-expiry is 7d; even the latest 15m claim + 300s attempt
  # leaves >23h margin before object creation age 8d can remove a current object.
  lifecycle_rule {
    action { type = "Delete" }
    condition {
      age            = 8
      matches_prefix = ["runs/"]
    }
  }
  # Keep 7d soft-delete recovery. This adds retained bytes/cost after deletion.
  soft_delete_policy { retention_duration_seconds = 604800 }
  lifecycle { prevent_destroy = true }
}

resource "google_project_iam_custom_role" "objects" {
  for_each = {
    api         = ["storage.objects.get"],
    worker      = ["storage.objects.create", "storage.objects.get"],
    maintenance = ["storage.objects.get", "storage.objects.list", "storage.objects.delete"]
  }
  role_id     = "${replace(var.prefix, "-", "_")}_${each.key}_objects"
  title       = "${var.prefix} ${each.key} private objects"
  permissions = each.value
}
resource "google_storage_bucket_iam_member" "objects" {
  for_each = google_project_iam_custom_role.objects
  bucket   = google_storage_bucket.artifacts.name
  role     = each.value.name
  member   = "serviceAccount:${google_service_account.identity[each.key].email}"
}

resource "google_secret_manager_secret_iam_member" "hmac" {
  for_each  = toset(["api", "worker", "maintenance"])
  secret_id = var.hmac_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.identity[each.key].email}"
}
resource "google_secret_manager_secret_iam_member" "model" {
  for_each  = var.model_secrets
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.identity["worker"].email}"
}

resource "google_cloud_tasks_queue" "generation" {
  name     = var.prefix
  location = var.region
  rate_limits {
    max_dispatches_per_second = 1
    max_concurrent_dispatches = 2
  }
  retry_config {
    max_attempts       = 5
    max_retry_duration = "900s"
    min_backoff        = "5s"
    max_backoff        = "60s"
    max_doublings      = 4
  }
  depends_on = [google_project_service.required]
}
resource "google_cloud_tasks_queue_iam_member" "enqueue" {
  name     = google_cloud_tasks_queue.generation.name
  location = var.region
  role     = google_project_iam_custom_role.dispatch.name
  member   = "serviceAccount:${google_service_account.identity["maintenance"].email}"
}
resource "google_project_iam_custom_role" "dispatch" {
  role_id     = "${replace(var.prefix, "-", "_")}_dispatch"
  title       = "${var.prefix} bounded task create and ambiguous-response readback"
  permissions = ["cloudtasks.tasks.create", "cloudtasks.tasks.get"]
}
resource "google_service_account_iam_member" "task_creator" {
  service_account_id = google_service_account.identity["tasks"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.identity["maintenance"].email}"
}
resource "google_service_account_iam_member" "task_agent" {
  service_account_id = google_service_account.identity["tasks"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${var.project_number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
  depends_on         = [google_project_service.required]
}

resource "google_cloud_run_v2_service" "internal" {
  for_each            = toset(["worker", "maintenance"])
  name                = "${var.prefix}-${each.key}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = true
  scaling {
    max_instance_count = each.key == "worker" ? 2 : 1
    min_instance_count = 0
  }
  template {
    service_account                  = google_service_account.identity[each.key].email
    timeout                          = each.key == "worker" ? "330s" : "60s"
    max_instance_request_concurrency = each.key == "worker" ? 2 : 1
    scaling {
      min_instance_count = 0
      max_instance_count = each.key == "worker" ? 2 : 1
    }
    containers {
      image   = var.image
      command = ["uvicorn"]
      args    = ["langgraph_system_generator.api.worker_server:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "3"]
      ports { container_port = 8080 }
      resources {
        limits   = { cpu = "1", memory = "2Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = merge(local.common, { LNF_INTERNAL_SERVICE_ROLE = each.key, LNF_INTERNAL_AUDIENCE = each.key == "worker" ? local.worker_url : local.maintenance_url })
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "LNF_JOB_IDEMPOTENCY_SECRET"
        value_source {
          secret_key_ref {
            secret  = var.hmac_secret_id
            version = var.hmac_secret_version
          }
        }
      }
      dynamic "env" {
        for_each = each.key == "worker" ? var.model_secrets : {}
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = env.value.version
            }
          }
        }
      }
    }
  }
  depends_on = [google_project_service.required, google_secret_manager_secret_iam_member.hmac, google_secret_manager_secret_iam_member.model, google_storage_bucket_iam_member.objects, google_project_iam_member.database]
}

resource "google_cloud_run_v2_service_iam_member" "internal" {
  for_each = { worker = "tasks", maintenance = "scheduler" }
  name     = google_cloud_run_v2_service.internal[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.identity[each.value].email}"
}

resource "google_cloud_run_v2_service" "api" {
  name                = "${var.prefix}-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  iap_enabled         = true
  deletion_protection = true
  scaling {
    max_instance_count = 2
    min_instance_count = 0
  }
  template {
    service_account                  = google_service_account.identity["api"].email
    timeout                          = "300s"
    max_instance_request_concurrency = 8
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.image
      ports { container_port = 8000 }
      resources {
        limits   = { cpu = "1", memory = "2Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = local.api_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "LNF_JOB_IDEMPOTENCY_SECRET"
        value_source {
          secret_key_ref {
            secret  = var.hmac_secret_id
            version = var.hmac_secret_version
          }
        }
      }
    }
  }
  depends_on = [google_project_service.required, google_secret_manager_secret_iam_member.hmac, google_cloud_tasks_queue.generation, google_firestore_index.dispatch, google_project_iam_member.database, google_storage_bucket_iam_member.objects]
}
resource "google_cloud_run_v2_service_iam_member" "iap" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${var.project_number}@gcp-sa-iap.iam.gserviceaccount.com"
}
resource "google_iap_web_cloud_run_service_iam_member" "users" {
  for_each               = var.iap_members
  cloud_run_service_name = google_cloud_run_v2_service.api.name
  location               = var.region
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}

resource "google_cloud_scheduler_job" "reconcile" {
  name             = "${var.prefix}-reconcile"
  region           = var.region
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  paused           = !var.enable_scheduler
  attempt_deadline = "55s"
  retry_config {
    retry_count          = 1
    max_retry_duration   = "120s"
    min_backoff_duration = "15s"
    max_backoff_duration = "60s"
    max_doublings        = 2
  }
  http_target {
    uri         = "${local.maintenance_url}/internal/reconcile"
    http_method = "POST"
    headers     = { "Content-Type" = "application/json" }
    body        = base64encode("{}")
    oidc_token {
      service_account_email = google_service_account.identity["scheduler"].email
      audience              = local.maintenance_url
    }
  }
  depends_on = [google_cloud_run_v2_service_iam_member.internal]
}

output "api_url" { value = google_cloud_run_v2_service.api.uri }
output "worker_url" { value = google_cloud_run_v2_service.internal["worker"].uri }
output "maintenance_url" { value = google_cloud_run_v2_service.internal["maintenance"].uri }
