"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  usePendingInstagramSelection,
  useSelectInstagramAccounts,
} from "@/hooks/use-accounts";
import { errorMessage } from "@/lib/api";

interface InstagramSelectionDialogProps {
  selectionToken: string | null;
  onClose: () => void;
}

export function InstagramSelectionDialog({
  selectionToken,
  onClose,
}: InstagramSelectionDialogProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const pending = usePendingInstagramSelection(selectionToken);
  const selectMutation = useSelectInstagramAccounts();

  const candidates = pending.data?.candidates ?? [];

  const toggleId = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const handleConfirm = () => {
    if (!selectionToken || selectedIds.length === 0) return;
    selectMutation.mutate(
      {
        selection_token: selectionToken,
        external_account_ids: selectedIds,
      },
      {
        onSuccess: (saved) => {
          toast.success(
            saved.length === 1
              ? "Cuenta de Instagram conectada"
              : `${saved.length} cuentas de Instagram conectadas`,
          );
          setSelectedIds([]);
          onClose();
        },
        onError: (err) => {
          toast.error("No se pudieron guardar las cuentas", {
            description: errorMessage(err),
          });
        },
      },
    );
  };

  return (
    <Dialog open={Boolean(selectionToken)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="border-white/[0.12] bg-[#111114] text-zinc-100 sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Selecciona las cuentas de Instagram</DialogTitle>
          <DialogDescription className="text-zinc-400">
            Tu sesión de Meta tiene acceso a varias cuentas Business o Creator vinculadas a
            páginas de Facebook. Elige cuáles registrar en WinClip.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          {pending.isLoading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-zinc-400">
              <Loader2 className="size-4 animate-spin text-amber-400" />
              <span>Cargando cuentas disponibles…</span>
            </div>
          ) : pending.isError ? (
            <p className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
              {errorMessage(pending.error)}
            </p>
          ) : (
            candidates.map((candidate) => {
              const checked = selectedIds.includes(candidate.external_account_id);
              return (
                <label
                  key={candidate.external_account_id}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-white/[0.08] bg-[#09090B] p-3 hover:border-white/[0.16]"
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => toggleId(candidate.external_account_id)}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-100">
                      {candidate.display_name}
                    </p>
                    <p className="truncate font-mono text-xs text-zinc-400">
                      @{candidate.username} · Página: {candidate.page_name}
                    </p>
                  </div>
                </label>
              );
            })
          )}
        </div>

        <DialogFooter>
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded-md px-3.5 text-sm text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={selectedIds.length === 0 || selectMutation.isPending}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-amber-400 px-4 text-sm font-semibold text-zinc-950 hover:bg-amber-300 disabled:opacity-50"
          >
            {selectMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
            <span>Conectar seleccionadas ({selectedIds.length})</span>
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
