"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import type { AccountPlatform, SocialAccountOut } from "@winclip/api-client";

import { Skeleton } from "@/components/ui/skeleton";
import {
  useAccounts,
  useCheckAccount,
  useDeleteAccount,
  useUpdateAccount,
} from "@/hooks/use-accounts";
import { errorMessage } from "@/lib/api";
import { AccountCard } from "./account-card";
import { ConnectAccountDialog } from "./connect-account-dialog";
import { InstagramSelectionDialog } from "./instagram-selection-dialog";
import { PlatformIcon, platformTitle } from "./platform-icon";

const PLATFORM_GROUPS: AccountPlatform[] = ["youtube", "tiktok", "instagram"];

export function AccountsWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [searchQuery, setSearchQuery] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogPlatform, setDialogPlatform] = useState<AccountPlatform>("youtube");
  const [dialogNonce, setDialogNonce] = useState(0);
  const [reconnectAccount, setReconnectAccount] = useState<SocialAccountOut | null>(null);
  const [dismissedIgToken, setDismissedIgToken] = useState<string | null>(null);
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const accountsQuery = useAccounts();
  const updateAccount = useUpdateAccount();
  const deleteAccount = useDeleteAccount();
  const checkAccount = useCheckAccount();

  const urlIgSelection = searchParams.get("ig_selection");
  const igSelectionToken =
    urlIgSelection && urlIgSelection !== dismissedIgToken ? urlIgSelection : null;

  useEffect(() => {
    const connected = searchParams.get("connected");
    const oauthError = searchParams.get("oauth_error");

    if (connected) {
      toast.success("Cuenta conectada correctamente");
      router.replace("/accounts");
    } else if (oauthError) {
      toast.error("Error al conectar cuenta OAuth", {
        description: oauthError,
      });
      router.replace("/accounts");
    }
  }, [searchParams, router]);

  const accounts = accountsQuery.data ?? [];
  const q = searchQuery.trim().toLowerCase();
  const expiredCount = accounts.filter(
    (item) => item.status === "expired" || item.status === "error",
  ).length;

  const openConnectFor = (platform: AccountPlatform) => {
    setReconnectAccount(null);
    setDialogPlatform(platform);
    setDialogNonce((n) => n + 1);
    setDialogOpen(true);
  };

  const handleSetDefault = (account: SocialAccountOut) => {
    setUpdatingId(account.id);
    updateAccount.mutate(
      { accountId: account.id, body: { is_default: true } },
      {
        onSuccess: () => {
          toast.success(
            `${account.alias || account.display_name} es ahora la cuenta predeterminada de ${platformTitle(account.platform)}`,
          );
        },
        onError: (err) => {
          toast.error("No se pudo cambiar la cuenta predeterminada", {
            description: errorMessage(err),
          });
        },
        onSettled: () => setUpdatingId(null),
      },
    );
  };

  const handleRenameAlias = (account: SocialAccountOut, nextAlias: string | null) => {
    setUpdatingId(account.id);
    updateAccount.mutate(
      { accountId: account.id, body: { alias: nextAlias } },
      {
        onSuccess: () => {
          toast.success("Alias actualizado");
        },
        onError: (err) => {
          toast.error("No se pudo renombrar el alias", {
            description: errorMessage(err),
          });
        },
        onSettled: () => setUpdatingId(null),
      },
    );
  };

  const handleCheck = (account: SocialAccountOut) => {
    setCheckingId(account.id);
    checkAccount.mutate(account.id, {
      onSuccess: (updated) => {
        if (updated.status === "connected") {
          toast.success(`Conexión verificada · ${updated.alias || updated.display_name}`, {
            description:
              updated.auth_method === "api"
                ? "Token OAuth vigente."
                : "Sesión persistente de Playwright activa.",
          });
        } else {
          toast.warning(`Atención en ${updated.alias || updated.display_name}`, {
            description:
              updated.last_error || "Pulsa Reconectar para renovar credenciales o sesión.",
          });
        }
      },
      onError: (err) => {
        toast.error("Error al comprobar la conexión", {
          description: errorMessage(err),
        });
      },
      onSettled: () => setCheckingId(null),
    });
  };

  const handleReconnect = (account: SocialAccountOut) => {
    setReconnectAccount(account);
    setDialogPlatform(account.platform);
    setDialogNonce((n) => n + 1);
    setDialogOpen(true);
  };

  const handleDelete = (account: SocialAccountOut) => {
    setDeletingId(account.id);
    deleteAccount.mutate(account.id, {
      onSuccess: () => {
        toast.success(`Cuenta ${account.alias || account.display_name} eliminada`);
      },
      onError: (err) => {
        toast.error("No se pudo eliminar la cuenta", {
          description: errorMessage(err),
        });
      },
      onSettled: () => setDeletingId(null),
    });
  };

  return (
    <div className="mx-auto max-w-[1440px] space-y-6 p-6">
      {/* Cabecera */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[18px] font-semibold text-zinc-100">
            Cuentas conectadas ({accounts.length})
          </h1>
          <p className="mt-0.5 text-[13px] text-zinc-400">
            Gestiona múltiples canales por red usando API oficial OAuth, sesiones locales de
            Playwright o importación de tokens.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative">
            <Search
              className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-zinc-500"
              aria-hidden="true"
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar cuenta, alias o @handle…"
              aria-label="Buscar cuentas"
              className="h-9 w-56 rounded-md border border-white/[0.08] bg-[#111114] pr-3 pl-8 text-xs text-zinc-100 placeholder:text-zinc-500 focus:border-amber-400/60 focus:outline-none"
            />
          </div>

          <button
            type="button"
            onClick={() => openConnectFor("youtube")}
            className="inline-flex h-9 cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-md bg-amber-400 px-4 text-[13px] font-semibold text-zinc-950 transition-colors hover:bg-amber-300"
          >
            <Plus className="size-4 stroke-[2.5]" />
            <span>Conectar cuenta</span>
          </button>
        </div>
      </div>

      {expiredCount > 0 ? (
        <div className="flex items-center gap-2.5 rounded-lg border border-rose-500/35 bg-rose-500/10 px-4 py-2.5 text-xs text-rose-200">
          <AlertTriangle className="size-4 shrink-0 text-rose-400" />
          <span>
            {expiredCount === 1
              ? "Hay 1 cuenta expirada o con error que requiere reconexión."
              : `Hay ${expiredCount} cuentas expiradas o con error que requieren reconexión.`}
          </span>
        </div>
      ) : null}

      {accountsQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, idx) => (
            <Skeleton key={idx} className="h-44 rounded-xl bg-white/[0.05]" />
          ))}
        </div>
      ) : accountsQuery.isError ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-200">
          No se pudieron cargar las cuentas: {errorMessage(accountsQuery.error)}
        </div>
      ) : (
        <div className="space-y-6">
          {PLATFORM_GROUPS.map((platform) => {
            const group = accounts.filter((acc) => {
              if (acc.platform !== platform) return false;
              if (!q) return true;
              return (
                acc.display_name.toLowerCase().includes(q) ||
                (acc.alias ?? "").toLowerCase().includes(q) ||
                acc.handle.toLowerCase().includes(q)
              );
            });

            return (
              <section
                key={platform}
                aria-label={platformTitle(platform)}
                className="space-y-3"
              >
                <div className="flex items-center justify-between border-b border-white/[0.08] pb-2">
                  <div className="flex items-center gap-2.5">
                    <PlatformIcon platform={platform} className="size-5" />
                    <h2 className="text-[14px] font-semibold text-zinc-100">
                      {platformTitle(platform)}
                    </h2>
                    <span className="font-mono text-[12px] text-zinc-500">
                      ({group.length})
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => openConnectFor(platform)}
                    className="cursor-pointer text-[12px] text-zinc-400 transition-colors hover:text-amber-300"
                  >
                    + Añadir cuenta
                  </button>
                </div>

                {group.length === 0 ? (
                  <div className="rounded-lg border border-white/[0.06] bg-[#111114] p-5 text-[12px] text-zinc-500">
                    {q
                      ? "Sin cuentas que coincidan con la búsqueda en esta plataforma."
                      : `Aún no has conectado ninguna cuenta de ${platformTitle(platform)}.`}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {group.map((account) => (
                      <AccountCard
                        key={account.id}
                        account={account}
                        isChecking={checkingId === account.id}
                        isUpdating={updatingId === account.id}
                        isDeleting={deletingId === account.id}
                        onSetDefault={handleSetDefault}
                        onRenameAlias={handleRenameAlias}
                        onCheck={handleCheck}
                        onReconnect={handleReconnect}
                        onDelete={handleDelete}
                      />
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}

      <ConnectAccountDialog
        key={`${reconnectAccount?.id ?? dialogPlatform}-${dialogNonce}`}
        open={dialogOpen}
        initialPlatform={dialogPlatform}
        reconnectAccount={reconnectAccount}
        onOpenChange={(nextOpen) => {
          setDialogOpen(nextOpen);
          if (!nextOpen) setReconnectAccount(null);
        }}
      />

      <InstagramSelectionDialog
        selectionToken={igSelectionToken}
        onClose={() => {
          if (urlIgSelection) {
            setDismissedIgToken(urlIgSelection);
            router.replace("/accounts");
          }
        }}
      />
    </div>
  );
}
