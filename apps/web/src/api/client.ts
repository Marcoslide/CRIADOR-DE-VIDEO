import type { ComponentCheck, HealthResponse, ReadinessResponse } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${path} respondeu ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => getJSON<HealthResponse>("/health"),
  readiness: () => getJSON<ReadinessResponse>("/health/ready"),
  workerHealth: () => getJSON<ComponentCheck>("/health/worker"),
};
