// Espelha packages/schemas/dhf_schemas/health.py — mantenha em sincronia manualmente
// até termos geração automática de client a partir do OpenAPI (fase futura).

export type ComponentStatus = "connected" | "error" | "timeout" | "not_configured";

export interface ComponentCheck {
  name: string;
  status: ComponentStatus;
  latency_ms: number | null;
  detail: string | null;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  app_env: string;
}

export interface ReadinessResponse {
  ready: boolean;
  checks: ComponentCheck[];
  checked_at: string;
}

// Espelha packages/schemas/dhf_schemas/storage.py
export type StorageConnectionStatus = "not_configured" | "connecting" | "connected" | "degraded" | "error";

export interface TreeValidationResult {
  expected: string[];
  found: string[];
  missing: string[];
  unexpected: string[];
  valid: boolean;
}

export interface StorageStatus {
  status: StorageConnectionStatus;
  detail: string | null;
  root_folder_id: string | null;
  tree: TreeValidationResult | null;
  checked_at: string;
}

// Espelha packages/schemas/dhf_schemas/system_status.py
export type EngineStatusValue = "connected" | "not_configured" | "not_installed" | "error";

export interface GpuStatus {
  status: EngineStatusValue;
  detail: string | null;
  device_name: string | null;
  driver_version: string | null;
  vram_total_mb: number | null;
  vram_used_mb: number | null;
}

export interface OpenAIStatus {
  status: EngineStatusValue;
  detail: string | null;
  error_code: string | null;
}

export interface EngineStubStatus {
  name: string;
  status: EngineStatusValue;
  detail: string | null;
}

export interface SystemStatusResponse {
  checked_at: string;
  api: ComponentCheck;
  postgres: ComponentCheck;
  redis: ComponentCheck;
  worker: ComponentCheck;
  storage: StorageStatus;
  gpu: GpuStatus;
  openai: OpenAIStatus;
  unreal: EngineStubStatus;
  audio2face: EngineStubStatus;
  metahuman: EngineStubStatus;
}

// Espelha packages/schemas/dhf_schemas/jobs.py
export type JobState = "pending" | "started" | "success" | "failure" | "unknown";

export interface DiagnosticJobSubmitted {
  job_id: string;
  triggered_at: string;
}

export interface DiagnosticJobStatus {
  job_id: string;
  state: JobState;
  result: Record<string, unknown> | null;
}

// Espelha core/avatars/dhf_avatars/schemas.py
export type AvatarStatus =
  | "draft"
  | "identity_locked"
  | "multiview_in_progress"
  | "multiview_approved"
  | "mesh_in_progress"
  | "mesh_approved"
  | "rigged"
  | "materials_approved"
  | "face_approved"
  | "voice_approved"
  | "motion_approved"
  | "master_approved"
  | "production_ready";

export interface Avatar {
  id: string;
  name: string;
  slug: string;
  version: number;
  status: AvatarStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AvatarCreatePayload {
  name: string;
  slug: string;
  metadata?: Record<string, unknown>;
}
