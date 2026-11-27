"use client";

import { useState } from "react";
import {
  BookOpen,
  Copy,
  Megaphone,
  Plus,
  Trash2,
} from "lucide-react";
import type {
  CampaignOut,
  CampaignTemplateOut,
} from "@winclip/api-client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface CampaignListProps {
  campaigns: CampaignOut[];
  templates: CampaignTemplateOut[];
  selectedId: string | "new";
  isLoading: boolean;
  duplicatingId: string | null;
  deletingId: string | null;
  onSelect: (campaign: CampaignOut) => void;
  onCreateNew: () => void;
  onApplyTemplate: (template: CampaignTemplateOut) => void;
  onDuplicate: (campaign: CampaignOut) => void;
  onDelete: (campaign: CampaignOut) => void;
}

const LANGUAGE_LABELS: Record<string, string> = {
  auto: "AUTO",
  es: "ES",
  en: "EN",
};

export function CampaignList({
  campaigns,
  templates,
  selectedId,
  isLoading,
  duplicatingId,
  deletingId,
  onSelect,
  onCreateNew,
  onApplyTemplate,
  onDuplicate,
  onDelete,
}: CampaignListProps) {
  const [confirmTarget, setConfirmTarget] = useState<CampaignOut | null>(null);

  const esTemplates = templates.filter((tpl) => tpl.language === "es");
  const enTemplates = templates.filter((tpl) => tpl.language === "en");

  return (
    <aside className="space-y-3 lg:col-span-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[14px] font-semibold text-zinc-200">
          Campañas guardadas{" "}
          <span className="font-mono text-xs tabular-nums text-zinc-500">
            ({campaigns.length})
          </span>
        </h2>
        <div className="flex items-center gap-1.5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 border-white/10 bg-[#111114] text-xs text-zinc-200 hover:bg-white/[0.06]"
                disabled={templates.length === 0}
              >
                <BookOpen className="size-3.5 text-amber-400" aria-hidden="true" />
                <span>Plantillas ES/EN</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="w-80 border-white/10 bg-[#141418] text-zinc-100"
            >
              {esTemplates.length > 0 ? (
                <>
                  <DropdownMenuLabel className="font-mono text-[11px] uppercase text-zinc-400">
                    Español (ES)
                  </DropdownMenuLabel>
                  {esTemplates.map((tpl) => (
                    <DropdownMenuItem
                      key={tpl.id}
                      onSelect={() => onApplyTemplate(tpl)}
                      className="flex cursor-pointer flex-col items-start gap-0.5 py-2 focus:bg-white/[0.06]"
                    >
                      <span className="text-xs font-semibold text-zinc-100">
                        {tpl.title}
                      </span>
                      <span className="line-clamp-2 text-[11px] text-zinc-400">
                        {tpl.description}
                      </span>
                    </DropdownMenuItem>
                  ))}
                </>
              ) : null}

              {esTemplates.length > 0 && enTemplates.length > 0 ? (
                <DropdownMenuSeparator className="bg-white/10" />
              ) : null}

              {enTemplates.length > 0 ? (
                <>
                  <DropdownMenuLabel className="font-mono text-[11px] uppercase text-zinc-400">
                    English (EN)
                  </DropdownMenuLabel>
                  {enTemplates.map((tpl) => (
                    <DropdownMenuItem
                      key={tpl.id}
                      onSelect={() => onApplyTemplate(tpl)}
                      className="flex cursor-pointer flex-col items-start gap-0.5 py-2 focus:bg-white/[0.06]"
                    >
                      <span className="text-xs font-semibold text-zinc-100">
                        {tpl.title}
                      </span>
                      <span className="line-clamp-2 text-[11px] text-zinc-400">
                        {tpl.description}
                      </span>
                    </DropdownMenuItem>
                  ))}
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            type="button"
            size="sm"
            onClick={onCreateNew}
            className="h-8 gap-1 bg-amber-400 px-3 text-xs font-semibold text-zinc-950 hover:bg-amber-300"
          >
            <Plus className="size-3.5 stroke-[2.5]" aria-hidden="true" />
            <span>Nueva campaña</span>
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2.5">
          {Array.from({ length: 3 }).map((_, idx) => (
            <Skeleton key={idx} className="h-32 w-full rounded-lg" />
          ))}
        </div>
      ) : campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-white/10 bg-[#111114] px-5 py-10 text-center">
          <div className="flex size-10 items-center justify-center rounded-full bg-amber-400/10 text-amber-400">
            <Megaphone className="size-5" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-zinc-200">
              Aún no tienes campañas guardadas
            </p>
            <p className="text-xs text-zinc-500">
              Crea una desde cero, pega un brief para extraer reglas con IA o
              carga una plantilla ES/EN.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-2.5">
          {campaigns.map((camp) => {
            const active = selectedId === camp.id;
            const rules = camp.rules;
            const lang = LANGUAGE_LABELS[rules.language ?? "auto"] ?? "AUTO";
            const minDur = rules.min_duration ?? 20;
            const maxDur = rules.max_duration ?? 60;
            const reqCount = rules.required_keywords?.length ?? 0;
            const bannedCount = rules.banned_words?.length ?? 0;
            const platforms = rules.target_platforms ?? [];

            return (
              <div
                key={camp.id}
                data-testid={`campaign-item-${camp.id}`}
                onClick={() => onSelect(camp)}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(camp);
                  }
                }}
                className={cn(
                  "cursor-pointer space-y-2 rounded-lg border p-4 transition-all",
                  active
                    ? "border-amber-400/55 bg-[#16161B]"
                    : "border-white/[0.08] bg-[#111114] hover:border-white/[0.16]",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="truncate text-[14px] font-semibold text-zinc-100">
                      {camp.name}
                    </h3>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-400">
                      <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
                        {lang}
                      </span>
                      {rules.subtitle_preset ? (
                        <span className="font-mono text-zinc-400">
                          {rules.subtitle_preset}
                        </span>
                      ) : null}
                      {platforms.length > 0 ? (
                        <span className="font-mono text-zinc-500">
                          · {platforms.join(", ")}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <span className="shrink-0 font-mono text-[11px] tabular-nums text-zinc-400">
                    {minDur}–{maxDur}s
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[11px] text-zinc-500">
                  <span>
                    {rules.max_clips ? `Máx ${rules.max_clips} clips` : "Sin tope"}
                  </span>
                  <span>·</span>
                  <span>{reqCount} obligatorias</span>
                  <span>·</span>
                  <span>{bannedCount} prohibidas</span>
                </div>

                <div className="flex items-center justify-between border-t border-white/[0.06] pt-2 text-[11px]">
                  <span className="text-zinc-500">
                    {camp.projects_count ?? 0}{" "}
                    {(camp.projects_count ?? 0) === 1 ? "proyecto" : "proyectos"}{" "}
                    · {formatDate(camp.updated_at)}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={duplicatingId === camp.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDuplicate(camp);
                      }}
                      className="rounded p-1 text-zinc-400 transition-colors hover:bg-white/[0.06] hover:text-amber-300 disabled:opacity-50"
                      aria-label={`Duplicar campaña ${camp.name}`}
                      title="Duplicar campaña"
                    >
                      <Copy className="size-3.5" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      disabled={deletingId === camp.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        setConfirmTarget(camp);
                      }}
                      className="rounded p-1 text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-rose-400 disabled:opacity-50"
                      aria-label={`Eliminar campaña ${camp.name}`}
                      title="Eliminar campaña"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <AlertDialog
        open={confirmTarget !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar esta campaña?</AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminará «{confirmTarget?.name}». Los proyectos que ya usaron
              esta campaña conservarán sus clips intactos y quedarán sin campaña
              asociada.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!confirmTarget) return;
                onDelete(confirmTarget);
                setConfirmTarget(null);
              }}
            >
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}
