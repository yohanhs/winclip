"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AccountPlatform,
  AccountsOAuthConfigOut,
  BrowserLoginOut,
  BrowserLoginStartRequest,
  InstagramSelectionOut,
  InstagramSelectRequest,
  OAuthStartOut,
  OAuthStartRequest,
  SocialAccountOut,
  SocialAccountUpdate,
  TokenImportRequest,
} from "@winclip/api-client";

import { useApiClient } from "./use-api-client";

/** Lista de cuentas sociales del workspace (`GET /api/accounts`). */
export function useAccounts() {
  const api = useApiClient();
  return useQuery<SocialAccountOut[]>({
    queryKey: ["accounts"],
    queryFn: async () => {
      const { data } = await api.GET("/api/accounts");
      return data ?? [];
    },
  });
}

/** Estado de configuración OAuth por plataforma (`GET /api/accounts/config`). */
export function useAccountsOAuthConfig() {
  const api = useApiClient();
  return useQuery<AccountsOAuthConfigOut>({
    queryKey: ["accounts-oauth-config"],
    queryFn: async () => {
      const { data } = await api.GET("/api/accounts/config");
      return data ?? { platforms: [] };
    },
    staleTime: 60_000,
  });
}

/** Actualiza alias y/o cuenta predeterminada (`PATCH /api/accounts/{account_id}`). */
export function useUpdateAccount() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<
    SocialAccountOut,
    Error,
    { accountId: string; body: SocialAccountUpdate }
  >({
    mutationFn: async ({ accountId, body }) => {
      const { data } = await api.PATCH("/api/accounts/{account_id}", {
        params: { path: { account_id: accountId } },
        body,
      });
      if (!data) throw new Error("Respuesta vacía al actualizar la cuenta");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** Elimina la cuenta y su directorio local (`DELETE /api/accounts/{account_id}`). */
export function useDeleteAccount() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: async (accountId) => {
      await api.DELETE("/api/accounts/{account_id}", {
        params: { path: { account_id: accountId } },
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** Comprueba la salud en vivo de una cuenta (`POST /api/accounts/{account_id}/check`). */
export function useCheckAccount() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<SocialAccountOut, Error, string>({
    mutationFn: async (accountId) => {
      const { data } = await api.POST("/api/accounts/{account_id}/check", {
        params: { path: { account_id: accountId } },
      });
      if (!data) throw new Error("Respuesta vacía al comprobar la cuenta");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** Inicia flujo OAuth oficial (`POST /api/accounts/oauth/{platform}/start`). */
export function useStartAccountOAuth() {
  const api = useApiClient();

  return useMutation<
    OAuthStartOut,
    Error,
    { platform: AccountPlatform; body?: OAuthStartRequest }
  >({
    mutationFn: async ({ platform, body }) => {
      const { data } = await api.POST("/api/accounts/oauth/{platform}/start", {
        params: { path: { platform } },
        body: body ?? { direct_post: false },
      });
      if (!data) throw new Error("Respuesta vacía al iniciar OAuth");
      return data;
    },
  });
}

/** Consulta candidatos de Instagram pendientes tras el callback Meta. */
export function usePendingInstagramSelection(selectionToken: string | null) {
  const api = useApiClient();
  return useQuery<InstagramSelectionOut>({
    queryKey: ["instagram-pending", selectionToken],
    enabled: Boolean(selectionToken),
    queryFn: async () => {
      const { data } = await api.GET(
        "/api/accounts/oauth/instagram/pending/{selection_token}",
        {
          params: { path: { selection_token: selectionToken ?? "" } },
        },
      );
      if (!data) throw new Error("Selección de Instagram no encontrada");
      return data;
    },
    retry: false,
  });
}

/** Confirma las cuentas Business/Creator de Instagram elegidas. */
export function useSelectInstagramAccounts() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<SocialAccountOut[], Error, InstagramSelectRequest>({
    mutationFn: async (body) => {
      const { data } = await api.POST("/api/accounts/oauth/instagram/select", {
        body,
      });
      return data ?? [];
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** Abre Chromium visible con perfil persistente (`POST /api/accounts/browser-login/start`). */
export function useStartBrowserLogin() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<BrowserLoginOut, Error, BrowserLoginStartRequest>({
    mutationFn: async (body) => {
      const { data } = await api.POST("/api/accounts/browser-login/start", {
        body,
      });
      if (!data) throw new Error("Respuesta vacía al iniciar navegador");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** Sondea el estado en vivo del login con navegador. */
export function useBrowserLoginStatus(accountId: string | null, active: boolean) {
  const api = useApiClient();
  return useQuery<BrowserLoginOut>({
    queryKey: ["browser-login-status", accountId],
    enabled: Boolean(accountId) && active,
    queryFn: async () => {
      const { data } = await api.GET(
        "/api/accounts/{account_id}/browser-login/status",
        {
          params: { path: { account_id: accountId ?? "" } },
        },
      );
      if (!data) throw new Error("Estado de navegador no disponible");
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.session_status === "waiting" || !query.state.data
        ? 1500
        : false,
  });
}

/** Confirma manualmente una sesión Playwright activa. */
export function useConfirmBrowserLogin() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<BrowserLoginOut, Error, string>({
    mutationFn: async (accountId) => {
      const { data } = await api.POST(
        "/api/accounts/{account_id}/browser-login/confirm",
        {
          params: { path: { account_id: accountId } },
        },
      );
      if (!data) throw new Error("Respuesta vacía al confirmar sesión");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** Cancela una sesión Playwright en curso. */
export function useCancelBrowserLogin() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<BrowserLoginOut, Error, string>({
    mutationFn: async (accountId) => {
      const { data } = await api.POST(
        "/api/accounts/{account_id}/browser-login/cancel",
        {
          params: { path: { account_id: accountId } },
        },
      );
      if (!data) throw new Error("Respuesta vacía al cancelar sesión");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}

/** Importa tokens locales en modo solo lectura (`POST /api/accounts/import`). */
export function useImportAccountTokens() {
  const api = useApiClient();
  const queryClient = useQueryClient();

  return useMutation<SocialAccountOut[], Error, TokenImportRequest>({
    mutationFn: async (body) => {
      const { data } = await api.POST("/api/accounts/import", { body });
      return data ?? [];
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}
