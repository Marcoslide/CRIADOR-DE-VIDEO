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
const REQUEST_TIMEOUT_MS = 10_000;

async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail ?? `${path} respondeu ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`${path} excedeu ${REQUEST_TIMEOUT_MS / 1000}s`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function getJSON<T>(path: string): Promise<T> {
  return requestJSON<T>(path);
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  return requestJSON<T>(path, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

async function patchJSON<T>(path: string, body: unknown): Promise<T> {
  return requestJSON<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  updateAvatarStatus: (id: string, status: string, expectedVersion: number) =>
    patchJSON<Avatar>(`/avatars/${id}`, { status, expected_version: expectedVersion }),
};
