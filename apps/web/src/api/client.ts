import type {
  Avatar,
  AvatarCreatePayload,
  AvatarFactoryView,
  AvatarReadiness,
  AvatarStateTransition,
  ComponentCheck,
  DerivedAsset,
  DiagnosticJobStatus,
  DiagnosticJobSubmitted,
  GateActionPayload,
  HealthResponse,
  IdentityLock,
  IdentityLockUpsertPayload,
  JobContract,
  MultiviewCompleteness,
  QualityGate,
  QualityGateName,
  ReadinessResponse,
  ReferenceAsset,
  ReferenceAssetCategory,
  StorageStatus,
  SystemStatusResponse,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 10_000;
const UPLOAD_TIMEOUT_MS = 30_000;

/** `error.detail` carrega o corpo cru do 409/422 quando é um objeto (ex.: gate bloqueado
 * — `{message, missing}`) para quem precisa mostrar a lista de pendências; para todo o
 * resto, `error.message` (herdado de Error) já basta, igual antes desta extensão. */
export class ApiError extends Error {
  readonly detail: unknown;

  constructor(message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
  }
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

async function requestJSON<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      throw new ApiError(detailMessage(detail, `${path} respondeu ${response.status}`), detail);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`${path} excedeu ${timeoutMs / 1000}s`);
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

async function postForm<T>(path: string, form: FormData): Promise<T> {
  return requestJSON<T>(path, { method: "POST", body: form }, UPLOAD_TIMEOUT_MS);
}

/** URL direta (não passa por `fetch`) para usar em `<img src>` — o backend faz o proxy
 * do binário guardado no Storage (seção 29: front nunca fala com o Drive direto). */
function referenceContentUrl(avatarId: string, assetId: string): string {
  return `${API_URL}/avatars/${avatarId}/references/${assetId}/content`;
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

  // --- Avatar Factory Control Plane -----------------------------------------------------
  getFactoryView: (avatarId: string) => getJSON<AvatarFactoryView>(`/avatars/${avatarId}/factory`),

  getIdentityLock: (avatarId: string) => getJSON<IdentityLock>(`/avatars/${avatarId}/identity-lock`),
  upsertIdentityLock: (avatarId: string, payload: IdentityLockUpsertPayload) =>
    postJSON<IdentityLock>(`/avatars/${avatarId}/identity-lock`, payload),
  approveIdentityLock: (avatarId: string, expectedVersion: number, approvedBy: string) =>
    postJSON<IdentityLock>(`/avatars/${avatarId}/identity-lock/approve`, {
      expected_version: expectedVersion,
      approved_by: approvedBy,
    }),

  listReferences: (avatarId: string, category?: ReferenceAssetCategory) =>
    getJSON<ReferenceAsset[]>(
      `/avatars/${avatarId}/references${category ? `?category=${category}` : ""}`,
    ),
  uploadReference: (
    avatarId: string,
    file: File,
    fields: { category: ReferenceAssetCategory; angle?: number; captureType?: string },
  ) => {
    const form = new FormData();
    form.append("category", fields.category);
    if (fields.angle !== undefined) form.append("angle", String(fields.angle));
    if (fields.captureType) form.append("capture_type", fields.captureType);
    form.append("file", file);
    return postForm<ReferenceAsset>(`/avatars/${avatarId}/references`, form);
  },
  approveReference: (avatarId: string, assetId: string, expectedVersion: number, reviewedBy: string) =>
    postJSON<ReferenceAsset>(`/avatars/${avatarId}/references/${assetId}/approve`, {
      expected_version: expectedVersion,
      reviewed_by: reviewedBy,
    }),
  rejectReference: (
    avatarId: string,
    assetId: string,
    payload: { expected_version: number; reason: string; notes?: string; reviewed_by: string },
  ) => postJSON<ReferenceAsset>(`/avatars/${avatarId}/references/${assetId}/reject`, payload),
  referenceContentUrl,

  getMultiview: (avatarId: string) => getJSON<MultiviewCompleteness>(`/avatars/${avatarId}/multiview`),

  listQualityGates: (avatarId: string) => getJSON<QualityGate[]>(`/avatars/${avatarId}/quality-gates`),
  approveGate: (avatarId: string, gate: QualityGateName, payload: GateActionPayload) =>
    postJSON<QualityGate>(`/avatars/${avatarId}/quality-gates/${gate}/approve`, payload),
  rejectGate: (avatarId: string, gate: QualityGateName, payload: GateActionPayload) =>
    postJSON<QualityGate>(`/avatars/${avatarId}/quality-gates/${gate}/reject`, payload),

  getHistory: (avatarId: string) => getJSON<AvatarStateTransition[]>(`/avatars/${avatarId}/history`),
  getReadiness: (avatarId: string) => getJSON<AvatarReadiness>(`/avatars/${avatarId}/readiness`),
  listDerivedAssets: (avatarId: string) => getJSON<DerivedAsset[]>(`/avatars/${avatarId}/derived-assets`),
  listJobContracts: (avatarId: string) => getJSON<JobContract[]>(`/avatars/${avatarId}/job-contracts`),
};
