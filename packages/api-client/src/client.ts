/**
 * Cliente tipado para la API de WinClip usando openapi-fetch
 */

import createClient from "openapi-fetch";
import type { Middleware } from "openapi-fetch";
import type { paths } from "./schema.js";

/**
 * Crea una instancia del cliente API tipada
 * @param baseUrl URL base de la API (ej: "http://localhost:8000")
 * @returns Cliente tipado con métodos para cada endpoint
 */
export function createApiClient(baseUrl: string) {
  const client = createClient<paths>({
    baseUrl,
    // Headers por defecto
    headers: {
      "Content-Type": "application/json",
    },
  });

  // Middleware para manejo de errores HTTP
  const errorMiddleware: Middleware = {
    async onResponse({ response }) {
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ApiError(response.status, errorData);
      }
    },
  };

  client.use(errorMiddleware);

  return client;
}

/**
 * Error tipado de la API
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly data: unknown
  ) {
    super(`API Error ${status}: ${JSON.stringify(data)}`);
    this.name = "ApiError";
  }
}

/**
 * Helper para obtener la URL base de la API desde variables de entorno
 */
export function getApiBaseUrl(): string {
  // En el navegador, usar NEXT_PUBLIC_API_URL
  if (typeof globalThis !== "undefined" && "window" in globalThis) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const env = (globalThis as any).process?.env;
    return env?.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  }
  // En Node (tests, scripts), usar variable de entorno o default
  return process.env.API_BASE_URL || "http://localhost:8000";
}