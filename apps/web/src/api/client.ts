import type {
  Avatar,
  AvatarCreatePayload,
  ComponentCheck,
  DiagnosticJobStatus,
  DiagnosticJobSubmitted,
  HealthResponse,
  ReadinessResponse,
  StorageStatus,
  SystemStatusResponse,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${path} respondeu ${response.status}`);
  }
  return (await response.json()) as T;
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `${path} respondeu ${response.status}`);
  }
  return (await response.json()) as T;
}

async function patchJSON<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `${path} respondeu ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => getJSON<HealthResponse>("/health"),
  readiness: () => getJSON<ReadinessResponse>("/health/ready"),
  workerHealth: () => getJSON<ComponentCheck>("/health/worker"),
  storageStatus: () => getJSON<StorageStatus>("/storage/status"),
  systemStatus: () => getJSON<SystemStatusResponse>("/status/system"),

  submitDiagnosticJob: () => postJSON<DiagnosticJobSubmitted>("/jobs/diagnostic"),
  diagnosticJobStatus: (jobId: string) =>
    getJSON<DiagnosticJobStatus>(`/jobs/diagnostic/${jobId}`),

  listAvatars: () => getJSON<Avatar[]>("/avatars"),
  getAvatar: (id: string) => getJSON<Avatar>(`/avatars/${id}`),
  createAvatar: (payload: AvatarCreatePayload) => postJSON<Avatar>("/avatars", payload),
  updateAvatarStatus: (id: string, status: string) =>
    patchJSON<Avatar>(`/avatars/${id}`, { status }),
};
