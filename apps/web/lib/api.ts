import type { components } from "@winclip/api-client";

/** URL base de la API local. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthCheck = components["schemas"]["CheckOut"];
export type HealthResponse = components["schemas"]["HealthOut"];

/**
 * Convierte una ruta relativa de media (`/api/clips/...`) en una URL absoluta
 * contra la API. Acepta también URLs absolutas y añade cache-busting opcional.
 */
export function mediaUrl(
  path: string | null | undefined,
  version?: string | null,
): string | null {
  if (!path) return null;
  const absolute = /^https?:\/\//i.test(path)
    ? path
    : `${API_URL}${path.startsWith("/") ? "" : "/"}${path}`;
  if (!version) return absolute;
  const separator = absolute.includes("?") ? "&" : "?";
  return `${absolute}${separator}v=${encodeURIComponent(version)}`;
}

/** Mensaje legible para cualquier error lanzado por el cliente API. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return "Ha ocurrido un error inesperado";
}

/** Consulta real de `GET /api/health` sin caché. */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/api/health`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(`La API respondió con estado ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}
