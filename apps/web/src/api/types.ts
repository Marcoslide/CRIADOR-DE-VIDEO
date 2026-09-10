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
