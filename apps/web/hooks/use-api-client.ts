"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  createApiClient,
  getApiBaseUrl,
  type HealthResponse,
} from "@winclip/api-client";

/**
 * Cliente API tipado. Se crea una sola vez por componente y es estable entre
 * renders, de modo que puede usarse como dependencia de otros hooks.
 */
export function useApiClient() {
  const [client] = useState(() => createApiClient(getApiBaseUrl()));
  return client;
}

/** Health check real contra `GET /api/health`. */
export function useHealth(options?: { enabled?: boolean }) {
  const api = useApiClient();
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => {
      const { data } = await api.GET("/api/health");
      if (!data) throw new Error("Respuesta vacía de /api/health");
      return data;
    },
    enabled: options?.enabled ?? true,
    refetchInterval: 30_000,
  });
}
