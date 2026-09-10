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
