/**
 * Cliente tipado para la API de WinClip usando openapi-fetch.
 */

import createClient from "openapi-fetch";
import type { Middleware } from "openapi-fetch";

import { ApiError } from "./errors";
import type { paths } from "./schema";

const DEFAULT_API_URL = "http://localhost:8000";

/**
 * Crea una instancia del cliente API tipada.
 *
 * @param baseUrl URL base de la API (por ejemplo `http://localhost:8000`).
 */
export function createApiClient(baseUrl: string = getApiBaseUrl()) {
  const client = createClient<paths>({
    baseUrl,
  });

  const errorMiddleware: Middleware = {
    async onResponse({ response }) {
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => null);
        throw new ApiError(response.status, data);
      }
    },
  };

  client.use(errorMiddleware);

  return client;
}

type EnvGlobal = typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};

/**
 * URL base de la API. En el navegador Next.js sustituye
 * `NEXT_PUBLIC_API_URL` en tiempo de compilación.
 */
export function getApiBaseUrl(): string {
  const env = (globalThis as EnvGlobal).process?.env;
  return env?.NEXT_PUBLIC_API_URL || env?.API_BASE_URL || DEFAULT_API_URL;
}

export { ApiError };
