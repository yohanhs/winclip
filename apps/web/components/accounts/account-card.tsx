"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock,
  Loader2,
  Pencil,
  RefreshCw,
  Star,
  Trash2,
  Wifi,
  X,
} from "lucide-react";
import type { SocialAccountOut } from "@winclip/api-client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { platformAccent } from "./platform-icon";

interface AccountCardProps {
  account: SocialAccountOut;
  isChecking: boolean;
  isUpdating: boolean;
  isDeleting: boolean;
  onSetDefault: (account: SocialAccountOut) => void;
  onRenameAlias: (account: SocialAccountOut, nextAlias: string | null) => void;
  onCheck: (account: SocialAccountOut) => void;
  onReconnect: (account: SocialAccountOut) => void;
  onDelete: (account: SocialAccountOut) => void;
}

function initialsFor(label: string): string {
  const parts = label
    .trim()
    .split(/\s+/)
    .map((word) => word.replace(/^[^A-Za-z0-9À-ÿ]+/, ""))
    .filter(Boolean);
  if (parts.length === 0) return "WC";
  return parts
    .map((word) => word[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function formatLastCheck(iso: string | null | undefined): string {
  if (!iso) return "Sin verificar";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Sin verificar";
  return date.toLocaleString("es-ES", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AccountCard({
  account,
  isChecking,
  isUpdating,
  isDeleting,
  onSetDefault,
  onRenameAlias,
  onCheck,
  onReconnect,
  onDelete,
}: AccountCardProps) {
  const [editingAlias, setEditingAlias] = useState(false);
  const [aliasDraft, setAliasDraft] = useState(account.alias ?? "");

  const isExpired = account.status === "expired";
  const isError = account.status === "error";
  const isPending = account.status === "pending";
  const needsAttention = isExpired || isError;

  const caps = (account.capabilities ?? {}) as Record<string, unknown>;
  const inboxOnly = caps.inbox_only === true;

  const primaryLabel = account.alias || account.display_name || "Cuenta sin nombre";

  const handleSaveAlias = () => {
    const cleaned = aliasDraft.trim();
    onRenameAlias(account, cleaned || null);
    setEditingAlias(false);
  };

  return (
    <article
      data-testid={`account-card-${account.id}`}
      className={cn(
        "flex flex-col justify-between gap-4 rounded-xl border bg-[#111114] p-4 transition-colors",
        needsAttention
          ? "border-rose-500/35"
          : "border-white/[0.08] hover:border-white/[0.16]",
      )}
    >
      <div className="space-y-3">
        {/* Cabecera: avatar, nombre/alias, handle y estrella Default */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {account.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={account.avatar_url}
                alt={primaryLabel}
                className="size-10 shrink-0 rounded-full border border-white/[0.1] object-cover"
              />
            ) : (
              <div
                className="flex size-10 shrink-0 items-center justify-center rounded-full text-[13px] font-bold text-zinc-950"
                style={{ backgroundColor: platformAccent(account.platform) }}
                aria-hidden="true"
              >
                {initialsFor(primaryLabel)}
              </div>
            )}

            <div className="min-w-0 flex-1">
              {editingAlias ? (
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    aria-label="Editar alias"
                    value={aliasDraft}
                    onChange={(e) => setAliasDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleSaveAlias();
                      } else if (e.key === "Escape") {
                        setAliasDraft(account.alias ?? "");
                        setEditingAlias(false);
                      }
                    }}
                    placeholder={account.display_name || "Alias interno"}
                    autoFocus
                    className="h-7 w-full min-w-0 rounded border border-amber-400/60 bg-[#09090B] px-2 text-xs text-zinc-100 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleSaveAlias}
                    disabled={isUpdating}
                    aria-label="Guardar alias"
                    className="flex size-7 shrink-0 items-center justify-center rounded bg-amber-400 text-zinc-950 hover:bg-amber-300"
                  >
                    <Check className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAliasDraft(account.alias ?? "");
                      setEditingAlias(false);
                    }}
                    aria-label="Cancelar edición de alias"
                    className="flex size-7 shrink-0 items-center justify-center rounded border border-white/[0.08] text-zinc-400 hover:text-zinc-100"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <h4 className="truncate text-[14px] font-semibold text-zinc-100">
                    {primaryLabel}
                  </h4>
                  <button
                    type="button"
                    onClick={() => {
                      setAliasDraft(account.alias ?? "");
                      setEditingAlias(true);
                    }}
                    aria-label={`Renombrar alias de ${primaryLabel}`}
                    title="Renombrar alias"
                    className="rounded p-1 text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-zinc-200"
                  >
                    <Pencil className="size-3" />
                  </button>
                </div>
              )}

              <div className="flex items-center gap-2 text-[12px] text-zinc-400">
                {account.handle ? (
                  <span className="truncate font-mono">{account.handle}</span>
                ) : null}
                {account.alias && account.display_name && account.alias !== account.display_name ? (
                  <span className="truncate text-[11px] text-zinc-500">
                    · {account.display_name}
                  </span>
                ) : null}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => onSetDefault(account)}
            disabled={isUpdating || account.is_default}
            title={
              account.is_default
                ? "Cuenta predeterminada en esta plataforma"
                : "Marcar como cuenta predeterminada"
            }
            aria-label={
              account.is_default
                ? `${primaryLabel} es predeterminada`
                : `Marcar ${primaryLabel} como predeterminada`
            }
            className={cn(
              "inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors",
              account.is_default
                ? "border-amber-400/40 bg-amber-400/15 text-amber-300"
                : "cursor-pointer border-white/[0.08] bg-[#09090B] text-zinc-500 hover:text-zinc-200",
            )}
          >
            <Star
              className={cn(
                "size-3",
                account.is_default && "fill-amber-400 text-amber-400",
              )}
            />
            <span>Default</span>
          </button>
        </div>

        {/* Badges de método, estado y capacidades */}
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span
            className={cn(
              "rounded border px-2 py-0.5 font-mono",
              account.auth_method === "api"
                ? "border-sky-400/25 bg-sky-500/10 text-sky-300"
                : "border-violet-400/25 bg-violet-500/10 text-violet-300",
            )}
          >
            {account.auth_method === "api" ? "API Oficial" : "Playwright"}
          </span>

          <span
            className={cn(
              "inline-flex items-center gap-1 rounded border px-2 py-0.5 font-medium",
              needsAttention
                ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
                : isPending
                  ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
                  : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
            )}
          >
            {needsAttention ? (
              <AlertTriangle className="size-3" />
            ) : isPending ? (
              <Clock className="size-3" />
            ) : (
              <CheckCircle2 className="size-3" />
            )}
            <span>
              {isExpired
                ? "Expirada"
                : isError
                  ? "Error"
                  : isPending
                    ? "Pendiente"
                    : "Conectada"}
            </span>
          </span>

          {inboxOnly ? (
            <span className="rounded border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 font-mono text-amber-300">
              Solo inbox
            </span>
          ) : null}

          <span
            className="ml-auto font-mono text-[11px] tabular-nums text-zinc-500"
            title="Última verificación"
          >
            {formatLastCheck(account.last_check_at)}
          </span>
        </div>

        {account.last_error ? (
          <p className="rounded-md border border-rose-500/25 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-200">
            {account.last_error}
          </p>
        ) : null}
      </div>

      {/* Pie de acciones */}
      <div className="flex items-center justify-between gap-2 border-t border-white/[0.06] pt-3">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onCheck(account)}
            disabled={isChecking}
            className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-white/[0.08] bg-[#18181B] px-2.5 text-[12px] text-zinc-200 transition-colors hover:bg-zinc-800 disabled:opacity-60"
          >
            {isChecking ? (
              <Loader2 className="size-3.5 animate-spin text-amber-400" />
            ) : (
              <Wifi className="size-3.5 text-zinc-400" />
            )}
            <span>Probar conexión</span>
          </button>

          <button
            type="button"
            onClick={() => onReconnect(account)}
            className={cn(
              "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-[12px] transition-colors",
              needsAttention
                ? "border-amber-400 bg-amber-400 font-semibold text-zinc-950 hover:bg-amber-300"
                : "border-white/[0.08] bg-transparent text-zinc-300 hover:bg-white/[0.05]",
            )}
          >
            <RefreshCw className="size-3.5" />
            <span>Reconectar</span>
          </button>
        </div>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <button
              type="button"
              disabled={isDeleting}
              aria-label={`Eliminar cuenta ${primaryLabel}`}
              className="flex size-8 cursor-pointer items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-rose-500/10 hover:text-rose-400"
            >
              <Trash2 className="size-3.5" />
            </button>
          </AlertDialogTrigger>
          <AlertDialogContent className="border-white/[0.1] bg-[#111114] text-zinc-100">
            <AlertDialogHeader>
              <AlertDialogTitle>¿Eliminar cuenta {primaryLabel}?</AlertDialogTitle>
              <AlertDialogDescription className="text-zinc-400">
                Se eliminará el registro de WinClip y se borrarán sus credenciales cifradas o
                perfil de navegador local en disco. Podrás volver a conectarla más tarde.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="border-white/[0.1] bg-[#18181B] text-zinc-200 hover:bg-zinc-800">
                Cancelar
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={() => onDelete(account)}
                className="bg-rose-500 text-white hover:bg-rose-400"
              >
                Eliminar cuenta
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </article>
  );
}
