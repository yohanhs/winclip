"use client";

import { useState } from "react";
import {
  AlertCircle,
  Check,
  Circle,
  Loader2,
  X,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
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
import { PIPELINE_STAGES, clamp, stageLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { JobSummary } from "@winclip/api-client";

export interface PipelineStepperProps {
  job: JobSummary | null;
  projectStatus: string;
  onCancel?: () => void;
  canceling?: boolean;
}

type StageState = "pending" | "active" | "done" | "failed" | "cancelled";

function isCancelledStatus(status: string | null | undefined): boolean {
  return status === "cancelled" || status === "canceled";
}

function stageState(
  stageId: string,
  stageIndex: number,
  job: JobSummary | null,
  projectStatus: string,
): { state: StageState; percent: number } {
  if (!job) {
    if (projectStatus === "ready") return { state: "done", percent: 100 };
    if (isCancelledStatus(projectStatus)) {
      return { state: "cancelled", percent: 0 };
    }
    return { state: "pending", percent: 0 };
  }
  if (job.status === "done") return { state: "done", percent: 100 };

  const currentIndex = PIPELINE_STAGES.findIndex((item) => item.id === job.stage);

  if (job.status === "failed") {
    if (stageId === job.stage) return { state: "failed", percent: 100 };
    if (currentIndex > -1 && stageIndex < currentIndex) {
      return { state: "done", percent: 100 };
    }
    return { state: "pending", percent: 0 };
  }

  if (isCancelledStatus(job.status) || isCancelledStatus(projectStatus)) {
    if (stageId === job.stage) return { state: "cancelled", percent: 0 };
    if (currentIndex > -1 && stageIndex < currentIndex) {
      return { state: "done", percent: 100 };
    }
    return { state: "pending", percent: 0 };
  }

  if (job.status === "queued") return { state: "pending", percent: 0 };

  const stage = PIPELINE_STAGES[stageIndex];
  if (!stage) return { state: "pending", percent: 0 };

  const progress = clamp(job.progress, 0, 100);
  if (currentIndex > -1) {
    if (stageIndex < currentIndex) return { state: "done", percent: 100 };
    if (stageIndex === currentIndex) {
      const within = ((progress - stage.from) / (stage.to - stage.from)) * 100;
      return { state: "active", percent: clamp(within, 0, 100) };
    }
    return { state: "pending", percent: 0 };
  }

  if (progress >= stage.to) return { state: "done", percent: 100 };
  if (progress >= stage.from) {
    const within = ((progress - stage.from) / (stage.to - stage.from)) * 100;
    return { state: "active", percent: clamp(within, 0, 100) };
  }
  return { state: "pending", percent: 0 };
}

export function PipelineStepper({
  job,
  projectStatus,
  onCancel,
  canceling = false,
}: PipelineStepperProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const isCancelled =
    isCancelledStatus(projectStatus) || isCancelledStatus(job?.status);
  const isFailed = projectStatus === "failed" || job?.status === "failed";
  const isActive =
    !isCancelled &&
    !isFailed &&
    (projectStatus === "processing" ||
      projectStatus === "queued" ||
      job?.status === "running" ||
      job?.status === "queued");
  const progress = clamp(job?.progress ?? (projectStatus === "ready" ? 100 : 0), 0, 100);
  const error = job?.error ?? null;

  return (
    <section
      className="rounded-xl border border-white/10 bg-[#111114] p-4 md:p-5"
      aria-label="Progreso del pipeline"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-zinc-100">
            Procesamiento
          </h2>
          <span className="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[11px] tabular-nums text-zinc-400">
            {Math.round(progress)}%
          </span>
          <span className="text-xs text-zinc-500">
            {isCancelled
              ? "Cancelado"
              : job
                ? stageLabel(job.stage)
                : projectStatus === "ready"
                  ? "Completado"
                  : "En cola"}
          </span>
        </div>

        {isActive && onCancel ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setConfirmOpen(true)}
            disabled={canceling}
            className="border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20 hover:text-rose-200"
          >
            <X aria-hidden="true" />
            {canceling ? "Cancelando…" : "Cancelar"}
          </Button>
        ) : null}
      </div>

      <Progress value={progress} className="mb-4 h-1.5" />

      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {PIPELINE_STAGES.map((stage, index) => {
          const { state, percent } = stageState(
            stage.id,
            index,
            job,
            projectStatus,
          );
          return (
            <li
              key={stage.id}
              data-stage={stage.id}
              data-state={state}
              className={cn(
                "rounded-lg border px-3 py-2.5 transition-colors",
                state === "active" && "border-amber-500/40 bg-amber-500/5",
                state === "done" && "border-emerald-500/25 bg-emerald-500/5",
                state === "failed" && "border-rose-500/40 bg-rose-500/5",
                state === "cancelled" && "border-zinc-500/40 bg-zinc-500/10",
                state === "pending" && "border-white/10 bg-[#0d0d10]",
              )}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                    state === "active" && "bg-amber-500/15 text-amber-400",
                    state === "done" && "bg-emerald-500/15 text-emerald-400",
                    state === "failed" && "bg-rose-500/15 text-rose-400",
                    state === "cancelled" && "bg-zinc-500/20 text-zinc-300",
                    state === "pending" && "bg-white/5 text-zinc-500",
                  )}
                >
                  {state === "done" ? (
                    <Check className="size-3" aria-hidden="true" />
                  ) : state === "active" ? (
                    <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  ) : state === "failed" ? (
                    <AlertCircle className="size-3" aria-hidden="true" />
                  ) : state === "cancelled" ? (
                    <XCircle className="size-3" aria-hidden="true" />
                  ) : (
                    <Circle className="size-3" aria-hidden="true" />
                  )}
                </span>
                <span
                  className={cn(
                    "truncate text-xs font-medium",
                    state === "active" && "text-amber-300",
                    state === "done" && "text-emerald-300",
                    state === "failed" && "text-rose-300",
                    state === "cancelled" && "text-zinc-300",
                    state === "pending" && "text-zinc-400",
                  )}
                >
                  {index + 1}. {stage.label}
                </span>
                <span className="ml-auto font-mono text-[10px] tabular-nums text-zinc-500">
                  {state === "done"
                    ? "100%"
                    : state === "active"
                      ? `${Math.round(percent)}%`
                      : state === "failed"
                        ? "error"
                        : state === "cancelled"
                          ? "cancelado"
                          : "—"}
                </span>
              </div>
              {state === "active" ? (
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-amber-400 transition-[width] duration-500"
                    style={{ width: `${percent}%` }}
                  />
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>

      {isFailed || error ? (
        <div
          role="alert"
          className="mt-4 flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-300"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium">El procesamiento ha fallado</p>
            <p className="mt-0.5 text-xs text-rose-300/80">
              {error ?? "Revisa los registros del worker para más detalles."}
            </p>
          </div>
        </div>
      ) : null}

      {isCancelled ? (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-zinc-500/30 bg-zinc-500/10 px-3 py-2.5 text-sm text-zinc-300">
          <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium">Procesamiento cancelado</p>
            <p className="mt-0.5 text-xs text-zinc-400">
              El trabajo se detuvo por solicitud del usuario. Los clips ya
              renderizados permanecen disponibles abajo.
            </p>
          </div>
        </div>
      ) : null}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Cancelar el procesamiento?</AlertDialogTitle>
            <AlertDialogDescription>
              Se detendrá el trabajo activo. Los clips ya generados se conservan,
              pero el proyecto quedará incompleto.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Volver</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => onCancel?.()}
            >
              Cancelar trabajo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
