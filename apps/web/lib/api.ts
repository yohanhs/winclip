export type CheckStatus = "ok" | "warn" | "error";

export interface HealthCheck {
  name: string;
  status: CheckStatus;
  detail: string;
  hint: string | null;
}

export interface HealthResponse {
  app: string;
  version: string;
  checks: HealthCheck[];
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`La API respondió con estado ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}
