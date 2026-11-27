"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Calendar,
  Check,
  Info,
  Loader2,
  Send,
  ShieldAlert,
  X,
} from "lucide-react";
import { toast } from "sonner";
import type {
  AccountPlatform,
  ClipOut,
  DeliveryMode,
  PublishMeta,
  SocialAccountOut,
} from "@winclip/api-client";

import { PlatformIcon, platformTitle } from "@/components/accounts/platform-icon";
import { Button } from "@/components/ui/button";
import { useAccounts } from "@/hooks/use-accounts";
import {
  useCreatePublications,
  usePreviewPublicationMeta,
  usePublicationsQuota,
} from "@/hooks/use-publications";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

const PLATFORMS: AccountPlatform[] = ["youtube", "tiktok", "instagram"];
const YOUTUBE_TITLE_MAX = 100;
const YOUTUBE_DESC_MAX = 5000;
const CAPTION_MAX = 2200;

interface PlatformEditableMeta {
  title: string;
  description: string;
  caption: string;
  tagsText: string;
  privacyStatus: "public" | "unlisted" | "private";
  pinnedComment: string;
  deliveryMode: DeliveryMode;
  privacyLevel: string;
  disableComment: boolean;
  disableDuet: boolean;
  disableStitch: boolean;
  shareToFeed: boolean;
}

export interface PublishDialogProps {
  clips: ClipOut[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPublished?: () => void;
}

function defaultScheduleValue(): string {
  const date = new Date(Date.now() + 2 * 60 * 60 * 1000);
  date.setMinutes(0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function buildInitialMeta(clip?: ClipOut): Record<AccountPlatform, PlatformEditableMeta> {
  const tags = (clip?.hashtags ?? []).map((t) => (t.startsWith("#") ? t : `#${t}`));
  const tagsLine = tags.join(" ");
  const ytTags = Array.from(new Set([...tags.map((t) => t.replace(/^#/, "")), "Shorts"])).join(
    ", ",
  );
  const rawTitle = (clip?.title ?? "").slice(0, YOUTUBE_TITLE_MAX);
  const desc = [clip?.description ?? "", tagsLine].filter(Boolean).join("\n\n");

  return {
    youtube: {
      title: rawTitle,
      description: desc ? `${desc}${desc.includes("#Shorts") ? "" : " #Shorts"}` : "#Shorts",
      caption: desc,
      tagsText: ytTags,
      privacyStatus: "public",
      pinnedComment: "",
      deliveryMode: "direct",
      privacyLevel: "PUBLIC_TO_EVERYONE",
      disableComment: false,
      disableDuet: false,
      disableStitch: false,
      shareToFeed: true,
    },
    tiktok: {
      title: rawTitle,
      description: clip?.description ?? "",
      caption: [clip?.title ?? "", tagsLine].filter(Boolean).join(" ").slice(0, CAPTION_MAX),
      tagsText: "",
      privacyStatus: "public",
      pinnedComment: "",
      deliveryMode: "direct",
      privacyLevel: "PUBLIC_TO_EVERYONE",
      disableComment: false,
      disableDuet: false,
      disableStitch: false,
      shareToFeed: true,
    },
    instagram: {
      title: rawTitle,
      description: clip?.description ?? "",
      caption: [clip?.description || clip?.title || "", tagsLine]
        .filter(Boolean)
        .join("\n\n")
        .slice(0, CAPTION_MAX),
      tagsText: "",
      privacyStatus: "public",
      pinnedComment: "",
      deliveryMode: "direct",
      privacyLevel: "PUBLIC_TO_EVERYONE",
      disableComment: false,
      disableDuet: false,
      disableStitch: false,
      shareToFeed: true,
    },
  };
}

export function PublishDialog({
  clips,
  open,
  onOpenChange,
  onPublished,
}: PublishDialogProps) {
  const accountsQuery = useAccounts();
  const quotaQuery = usePublicationsQuota();
  const previewMutation = usePreviewPublicationMeta();
  const createMutation = useCreatePublications();

  const accounts = useMemo(() => accountsQuery.data ?? [], [accountsQuery.data]);
  const defaultAccountIds = useMemo(() => {
    const defaults = accounts
      .filter((a) => a.is_default && a.status === "connected")
      .map((a) => a.id);
    if (defaults.length > 0) return defaults;
    return accounts
      .filter((a) => a.status === "connected")
      .slice(0, 1)
      .map((a) => a.id);
  }, [accounts]);

  const [userSelectedAccountIds, setUserSelectedAccountIds] = useState<string[] | null>(
    null,
  );
  const selectedAccountIds = userSelectedAccountIds ?? defaultAccountIds;
  const [activeTab, setActiveTab] = useState<AccountPlatform>("youtube");
  const [scheduleMode, setScheduleMode] = useState<"now" | "scheduled">("now");
  const [scheduledDateTime, setScheduledDateTime] = useState<string>(defaultScheduleValue);
  const [platformMeta, setPlatformMeta] = useState<Record<AccountPlatform, PlatformEditableMeta>>(
    () => buildInitialMeta(clips[0]),
  );
  const [previewWarnings, setPreviewWarnings] = useState<string[]>([]);
  const [forceSubmit, setForceSubmit] = useState(false);

  // Solicitar preview-meta al backend cuando cambian clips/cuentas seleccionadas
  const clipIdsKey = clips.map((c) => c.id).join(",");
  const accountIdsKey = selectedAccountIds.join(",");
  const previewMutate = previewMutation.mutate;

  useEffect(() => {
    if (!open || clips.length === 0 || selectedAccountIds.length === 0) return;
    previewMutate(
      { clip_ids: clips.map((c) => c.id), account_ids: selectedAccountIds },
      {
        onSuccess: (data) => {
          setPreviewWarnings(data.warnings ?? []);
          setPlatformMeta((prev) => {
            const next = { ...prev };
            for (const platform of PLATFORMS) {
              const first = data.items.find((item) => item.platform === platform);
              if (!first) continue;
              const m = first.meta;
              next[platform] = {
                ...next[platform],
                title: m.title ?? next[platform].title,
                description: m.description ?? next[platform].description,
                caption: m.caption ?? next[platform].caption,
                tagsText: (m.tags ?? []).join(", "),
                privacyStatus: m.privacy_status ?? next[platform].privacyStatus,
                pinnedComment: m.pinned_comment ?? "",
                deliveryMode: first.delivery_mode,
                privacyLevel: m.privacy_level ?? next[platform].privacyLevel,
                disableComment: m.disable_comment ?? false,
                disableDuet: m.disable_duet ?? false,
                disableStitch: m.disable_stitch ?? false,
                shareToFeed: m.share_to_feed ?? true,
              };
            }
            return next;
          });
        },
      },
    );
  }, [open, clipIdsKey, accountIdsKey, previewMutate, clips, selectedAccountIds]);

  const selectedAccounts = useMemo(
    () => accounts.filter((a) => selectedAccountIds.includes(a.id)),
    [accounts, selectedAccountIds],
  );

  const hasYouTube = selectedAccounts.some((a) => a.platform === "youtube");
  const hasTikTokInboxOnly = selectedAccounts.some(
    (a) =>
      a.platform === "tiktok" &&
      a.auth_method === "api" &&
      !Boolean(a.capabilities?.direct_post),
  );
  const hasPlaywright = selectedAccounts.some((a) => a.auth_method === "playwright");
  const hasDeferredPlatform = selectedAccounts.some(
    (a) => a.platform === "tiktok" || a.platform === "instagram",
  );

  const ytTitleLen = platformMeta.youtube.title.trim().length;
  const ytTitleInvalid = hasYouTube && (ytTitleLen === 0 || ytTitleLen > YOUTUBE_TITLE_MAX);
  const tiktokCaptionInvalid =
    selectedAccounts.some((a) => a.platform === "tiktok") &&
    platformMeta.tiktok.caption.length > CAPTION_MAX;
  const igCaptionInvalid =
    selectedAccounts.some((a) => a.platform === "instagram") &&
    platformMeta.instagram.caption.length > CAPTION_MAX;

  const totalJobs = clips.length * selectedAccounts.length;
  const ytUploadsInBatch =
    clips.length *
    selectedAccounts.filter((a) => a.platform === "youtube" && a.auth_method === "api").length;
  const quota = quotaQuery.data;
  const projectedYtUnits =
    (quota?.youtube_units_used ?? 0) + ytUploadsInBatch * (quota?.youtube_upload_cost ?? 1600);
  const exceedsYtQuota =
    ytUploadsInBatch > 0 && projectedYtUnits > (quota?.youtube_units_limit ?? 10000);

  if (!open) return null;

  const toggleAccount = (account: SocialAccountOut) => {
    if (account.status === "expired") return;
    setUserSelectedAccountIds((prev) => {
      const base = prev ?? defaultAccountIds;
      return base.includes(account.id)
        ? base.filter((id) => id !== account.id)
        : [...base, account.id];
    });
  };

  const updateMeta = (
    platform: AccountPlatform,
    patch: Partial<PlatformEditableMeta>,
  ) => {
    setPlatformMeta((prev) => ({
      ...prev,
      [platform]: { ...prev[platform], ...patch },
    }));
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (selectedAccounts.length === 0 || ytTitleInvalid || tiktokCaptionInvalid || igCaptionInvalid) {
      return;
    }

    const scheduledIso =
      scheduleMode === "scheduled" && scheduledDateTime
        ? new Date(scheduledDateTime).toISOString()
        : null;

    const items = clips.flatMap((clip) =>
      selectedAccounts.map((acc) => {
        const editable = platformMeta[acc.platform];
        const parsedTags = editable.tagsText
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
        const meta: PublishMeta = {
          title:
            clips.length > 1 && acc.platform === "youtube"
              ? (clip.title || editable.title).slice(0, YOUTUBE_TITLE_MAX)
              : editable.title,
          description: editable.description,
          caption: editable.caption,
          hashtags: clip.hashtags ?? [],
          scheduled_at: scheduledIso,
          delivery_mode:
            acc.platform === "tiktok" &&
            acc.auth_method === "api" &&
            !Boolean(acc.capabilities?.direct_post)
              ? "inbox"
              : editable.deliveryMode,
          language: "es",
          tags: parsedTags,
          category_id: "22",
          privacy_status: editable.privacyStatus,
          pinned_comment: editable.pinnedComment.trim() || null,
          upload_thumbnail: Boolean(clip.thumb_url),
          privacy_level: editable.privacyLevel,
          disable_comment: editable.disableComment,
          disable_duet: editable.disableDuet,
          disable_stitch: editable.disableStitch,
          share_to_feed: editable.shareToFeed,
        };
        return {
          clip_id: clip.id,
          account_id: acc.id,
          meta,
          scheduled_at: scheduledIso,
        };
      }),
    );

    createMutation.mutate(
      { items, force: forceSubmit },
      {
        onSuccess: (created) => {
          toast.success(
            scheduleMode === "scheduled"
              ? `${created.length} publicaciones programadas`
              : `${created.length} publicaciones encoladas`,
            {
              description: "Puedes seguir el estado en tiempo real en /publications.",
            },
          );
          onPublished?.();
          onOpenChange(false);
        },
        onError: (err) => {
          toast.error("No se pudieron crear las publicaciones", {
            description: errorMessage(err),
          });
        },
      },
    );
  };

  const currentMeta = platformMeta[activeTab];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
      onClick={() => onOpenChange(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Publicar clips en redes sociales"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-white/[0.12] bg-[#111114] shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-4 border-b border-white/[0.08] px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-zinc-100">
              Publicar {clips.length} {clips.length === 1 ? "clip" : "clips"} en redes
            </h2>
            <p className="mt-0.5 text-xs text-zinc-400">
              Selecciona cuentas destino, edita metadatos por plataforma y programa o envía ahora.
            </p>
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Cerrar diálogo"
            className="rounded-md p-1.5 text-zinc-400 hover:bg-white/[0.06] hover:text-zinc-100"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* 1. Cuentas agrupadas por plataforma */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-medium text-zinc-200">
                1. Cuentas destino ({selectedAccountIds.length} seleccionadas)
              </span>
              <span className="text-[11px] text-zinc-500">
                Total envíos:{" "}
                <strong className="font-mono tabular-nums text-zinc-200">{totalJobs}</strong>
              </span>
            </div>

            {accountsQuery.isLoading ? (
              <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-[#09090B] p-4 text-xs text-zinc-400">
                <Loader2 className="size-4 animate-spin text-amber-400" aria-hidden="true" />
                Cargando cuentas conectadas…
              </div>
            ) : accounts.length === 0 ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-400/25 bg-amber-400/[0.06] p-4 text-xs text-amber-200">
                <span>No hay cuentas sociales conectadas todavía.</span>
                <Button asChild size="sm" variant="outline">
                  <Link href="/accounts">Conectar cuentas →</Link>
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {PLATFORMS.map((platform) => {
                  const group = accounts.filter((a) => a.platform === platform);
                  return (
                    <div
                      key={platform}
                      className="space-y-2 rounded-lg border border-white/[0.08] bg-[#09090B] p-3"
                    >
                      <div className="flex items-center gap-2 text-xs font-semibold text-zinc-200">
                        <PlatformIcon platform={platform} className="size-4" />
                        <span>{platformTitle(platform)}</span>
                      </div>

                      {group.length === 0 ? (
                        <p className="text-[11px] text-zinc-500">Sin cuentas conectadas</p>
                      ) : (
                        <div className="space-y-1.5">
                          {group.map((acc) => {
                            const checked = selectedAccountIds.includes(acc.id);
                            const expired = acc.status === "expired";
                            return (
                              <label
                                key={acc.id}
                                className={cn(
                                  "flex items-start gap-2.5 rounded-md border p-2 transition-colors",
                                  expired
                                    ? "cursor-not-allowed border-rose-500/25 bg-rose-500/[0.05] opacity-70"
                                    : checked
                                      ? "cursor-pointer border-amber-400/55 bg-amber-400/[0.08]"
                                      : "cursor-pointer border-white/[0.06] hover:border-white/[0.16]",
                                )}
                              >
                                <input
                                  type="checkbox"
                                  disabled={expired}
                                  checked={checked}
                                  onChange={() => toggleAccount(acc)}
                                  className="sr-only"
                                />
                                <span
                                  className={cn(
                                    "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border",
                                    checked
                                      ? "border-amber-400 bg-amber-400 text-zinc-950"
                                      : "border-white/25 bg-transparent",
                                  )}
                                >
                                  {checked ? <Check className="size-3 stroke-[3]" /> : null}
                                </span>
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-1.5">
                                    <p className="truncate text-xs font-medium text-zinc-100">
                                      {acc.alias || acc.display_name}
                                    </p>
                                    {acc.auth_method === "playwright" ? (
                                      <span className="rounded bg-violet-500/15 px-1 py-0.5 font-mono text-[9px] text-violet-300">
                                        PW
                                      </span>
                                    ) : null}
                                  </div>
                                  <p className="truncate font-mono text-[11px] text-zinc-500">
                                    {acc.handle || acc.display_name}
                                  </p>
                                  {expired ? (
                                    <span className="mt-0.5 inline-flex items-center gap-1 text-[10px] text-rose-400">
                                      <AlertTriangle className="size-3" aria-hidden="true" />
                                      Sesión expirada
                                    </span>
                                  ) : null}
                                </div>
                              </label>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Avisos de cuota YouTube, Inbox TikTok y ToS Playwright */}
          {(hasYouTube || hasTikTokInboxOnly || hasPlaywright || previewWarnings.length > 0) && (
            <div className="space-y-2">
              {hasYouTube && quota ? (
                <div
                  className={cn(
                    "flex items-start gap-2 rounded-lg border px-3 py-2 text-xs",
                    exceedsYtQuota
                      ? "border-rose-500/35 bg-rose-500/10 text-rose-200"
                      : "border-white/[0.08] bg-[#09090B] text-zinc-300",
                  )}
                >
                  <Info className="mt-0.5 size-3.5 shrink-0 text-amber-400" aria-hidden="true" />
                  <span>
                    Cuota diaria YouTube API:{" "}
                    <strong className="font-mono tabular-nums">
                      {projectedYtUnits.toLocaleString()} /{" "}
                      {quota.youtube_units_limit.toLocaleString()}
                    </strong>{" "}
                    unidades estimadas (~6 subidas/día estándar).
                  </span>
                </div>
              ) : null}

              {hasTikTokInboxOnly ? (
                <div className="flex items-start gap-2 rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
                  <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                  <span>
                    Tu cuenta API de TikTok usa modo <strong>Borrador Inbox</strong> (sin permiso
                    Direct Post): completa la publicación desde la app móvil de TikTok.
                  </span>
                </div>
              ) : null}

              {hasPlaywright ? (
                <div className="flex items-start gap-2 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-200">
                  <ShieldAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                  <span>
                    <strong>Aviso ToS (Playwright):</strong> la automatización web conlleva riesgo
                    de retos anti-bot. WinClip usa navegador visible y se detiene de inmediato ante
                    cualquier CAPTCHA o 2FA.
                  </span>
                </div>
              ) : null}
            </div>
          )}

          {/* 2. Metadatos editables por plataforma */}
          <div className="space-y-3 border-t border-white/[0.06] pt-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[13px] font-medium text-zinc-200">
                2. Metadatos y modo de entrega por plataforma
              </span>
              <div
                role="tablist"
                aria-label="Plataformas de metadatos"
                className="inline-flex rounded-md border border-white/[0.08] bg-[#09090B] p-0.5"
              >
                {PLATFORMS.map((platform) => (
                  <button
                    key={platform}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === platform}
                    onClick={() => setActiveTab(platform)}
                    className={cn(
                      "inline-flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors",
                      activeTab === platform
                        ? "bg-white/[0.1] text-zinc-100"
                        : "text-zinc-400 hover:text-zinc-200",
                    )}
                  >
                    <PlatformIcon platform={platform} className="size-3.5" />
                    <span>{platformTitle(platform)}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-3 rounded-lg border border-white/[0.08] bg-[#09090B] p-4">
              {activeTab === "youtube" ? (
                <>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="space-y-1.5 sm:col-span-2">
                      <div className="flex items-center justify-between text-xs">
                        <label htmlFor="yt-title" className="text-zinc-400">
                          Título (YouTube Shorts)
                        </label>
                        <span
                          className={cn(
                            "font-mono text-[11px] tabular-nums",
                            currentMeta.title.length > YOUTUBE_TITLE_MAX
                              ? "text-rose-400"
                              : "text-zinc-500",
                          )}
                        >
                          {currentMeta.title.length}/{YOUTUBE_TITLE_MAX}
                        </span>
                      </div>
                      <input
                        id="yt-title"
                        type="text"
                        value={currentMeta.title}
                        onChange={(e) => updateMeta("youtube", { title: e.target.value })}
                        className="h-9 w-full rounded-md border border-white/[0.1] bg-[#111114] px-3 text-[13px] text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label htmlFor="yt-privacy" className="block text-xs text-zinc-400">
                        Privacidad
                      </label>
                      <select
                        id="yt-privacy"
                        value={currentMeta.privacyStatus}
                        onChange={(e) =>
                          updateMeta("youtube", {
                            privacyStatus: e.target.value as "public" | "unlisted" | "private",
                          })
                        }
                        className="h-9 w-full rounded-md border border-white/[0.1] bg-[#111114] px-3 text-xs text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                      >
                        <option value="public">Público</option>
                        <option value="unlisted">Oculto</option>
                        <option value="private">Privado</option>
                      </select>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <label htmlFor="yt-desc" className="text-zinc-400">
                        Descripción y hashtags
                      </label>
                      <span className="font-mono text-[11px] tabular-nums text-zinc-500">
                        {currentMeta.description.length}/{YOUTUBE_DESC_MAX}
                      </span>
                    </div>
                    <textarea
                      id="yt-desc"
                      rows={2}
                      value={currentMeta.description}
                      onChange={(e) => updateMeta("youtube", { description: e.target.value })}
                      className="w-full resize-none rounded-md border border-white/[0.1] bg-[#111114] p-2.5 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <label htmlFor="yt-tags" className="block text-xs text-zinc-400">
                        Tags (separados por coma)
                      </label>
                      <input
                        id="yt-tags"
                        type="text"
                        value={currentMeta.tagsText}
                        onChange={(e) => updateMeta("youtube", { tagsText: e.target.value })}
                        placeholder="Shorts, finanzas, ahorro"
                        className="h-9 w-full rounded-md border border-white/[0.1] bg-[#111114] px-3 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label htmlFor="yt-comment" className="block text-xs text-zinc-400">
                        Comentario fijado (opcional)
                      </label>
                      <input
                        id="yt-comment"
                        type="text"
                        value={currentMeta.pinnedComment}
                        onChange={(e) => updateMeta("youtube", { pinnedComment: e.target.value })}
                        placeholder="CTA o enlace para comentar al publicar"
                        className="h-9 w-full rounded-md border border-white/[0.1] bg-[#111114] px-3 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
                      />
                    </div>
                  </div>
                </>
              ) : activeTab === "tiktok" ? (
                <>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <label htmlFor="tt-delivery" className="block text-xs text-zinc-400">
                        Modo de entrega
                      </label>
                      <select
                        id="tt-delivery"
                        value={currentMeta.deliveryMode}
                        onChange={(e) =>
                          updateMeta("tiktok", { deliveryMode: e.target.value as DeliveryMode })
                        }
                        className="h-9 w-full rounded-md border border-white/[0.1] bg-[#111114] px-3 text-xs text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                      >
                        <option value="direct">Directo (Publicar)</option>
                        <option value="inbox">Borrador Inbox</option>
                      </select>
                    </div>
                    <div className="space-y-1.5">
                      <label htmlFor="tt-privacy" className="block text-xs text-zinc-400">
                        Privacidad
                      </label>
                      <select
                        id="tt-privacy"
                        value={currentMeta.privacyLevel}
                        onChange={(e) => updateMeta("tiktok", { privacyLevel: e.target.value })}
                        className="h-9 w-full rounded-md border border-white/[0.1] bg-[#111114] px-3 text-xs text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                      >
                        <option value="PUBLIC_TO_EVERYONE">Público</option>
                        <option value="FOLLOWER_OF_CREATOR">Seguidores</option>
                        <option value="MUTUAL_FOLLOW_FRIENDS">Amigos</option>
                        <option value="SELF_ONLY">Solo yo</option>
                      </select>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <label htmlFor="tt-caption" className="text-zinc-400">
                        Caption y hashtags (TikTok)
                      </label>
                      <span
                        className={cn(
                          "font-mono text-[11px] tabular-nums",
                          currentMeta.caption.length > CAPTION_MAX
                            ? "text-rose-400"
                            : "text-zinc-500",
                        )}
                      >
                        {currentMeta.caption.length}/{CAPTION_MAX}
                      </span>
                    </div>
                    <textarea
                      id="tt-caption"
                      rows={3}
                      value={currentMeta.caption}
                      onChange={(e) => updateMeta("tiktok", { caption: e.target.value })}
                      className="w-full resize-none rounded-md border border-white/[0.1] bg-[#111114] p-2.5 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <label htmlFor="ig-caption" className="text-zinc-400">
                        Caption y hashtags (Instagram Reels)
                      </label>
                      <span
                        className={cn(
                          "font-mono text-[11px] tabular-nums",
                          currentMeta.caption.length > CAPTION_MAX
                            ? "text-rose-400"
                            : "text-zinc-500",
                        )}
                      >
                        {currentMeta.caption.length}/{CAPTION_MAX}
                      </span>
                    </div>
                    <textarea
                      id="ig-caption"
                      rows={3}
                      value={currentMeta.caption}
                      onChange={(e) => updateMeta("instagram", { caption: e.target.value })}
                      className="w-full resize-none rounded-md border border-white/[0.1] bg-[#111114] p-2.5 text-xs text-zinc-200 focus:border-amber-400/60 focus:outline-none"
                    />
                  </div>
                  <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
                    <input
                      type="checkbox"
                      checked={currentMeta.shareToFeed}
                      onChange={(e) => updateMeta("instagram", { shareToFeed: e.target.checked })}
                      className="accent-amber-400"
                    />
                    <span>Compartir también en el feed principal</span>
                  </label>
                </>
              )}
            </div>
          </div>

          {/* 3. Cuándo publicar */}
          <div className="space-y-3 border-t border-white/[0.06] pt-3">
            <span className="block text-[13px] font-medium text-zinc-200">
              3. Cuándo publicar
            </span>
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-md border border-white/[0.08] bg-[#09090B] p-0.5">
                <button
                  type="button"
                  onClick={() => setScheduleMode("now")}
                  className={cn(
                    "inline-flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[5px] px-3 py-1.5 text-xs font-medium transition-colors",
                    scheduleMode === "now"
                      ? "bg-white/[0.1] text-zinc-100"
                      : "text-zinc-400 hover:text-zinc-200",
                  )}
                >
                  <Send className="size-3.5" aria-hidden="true" />
                  <span>Publicar ahora</span>
                </button>
                <button
                  type="button"
                  onClick={() => setScheduleMode("scheduled")}
                  className={cn(
                    "inline-flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-[5px] px-3 py-1.5 text-xs font-medium transition-colors",
                    scheduleMode === "scheduled"
                      ? "bg-white/[0.1] text-zinc-100"
                      : "text-zinc-400 hover:text-zinc-200",
                  )}
                >
                  <Calendar className="size-3.5" aria-hidden="true" />
                  <span>Programar fecha y hora</span>
                </button>
              </div>

              {scheduleMode === "scheduled" ? (
                <input
                  type="datetime-local"
                  aria-label="Fecha y hora programada"
                  value={scheduledDateTime}
                  onChange={(e) => setScheduledDateTime(e.target.value)}
                  className="h-9 rounded-md border border-white/[0.1] bg-[#09090B] px-3 font-mono text-xs text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                />
              ) : null}
            </div>

            {scheduleMode === "scheduled" && hasDeferredPlatform ? (
              <p className="text-[11px] text-zinc-400">
                YouTube programa directamente en servidor. TikTok e Instagram requieren que WinClip
                y el worker local estén activos a la hora programada.
              </p>
            ) : null}

            <label className="inline-flex cursor-pointer items-center gap-2 text-[11px] text-zinc-400">
              <input
                type="checkbox"
                checked={forceSubmit}
                onChange={(e) => setForceSubmit(e.target.checked)}
                className="accent-amber-400"
              />
              <span>Permitir republicar duplicados o superar el límite diario (force)</span>
            </label>
          </div>

          {/* Footer actions */}
          <div className="flex items-center justify-between gap-3 border-t border-white/[0.08] pt-4">
            <span className="text-xs text-zinc-500">
              {selectedAccounts.length === 0
                ? "Selecciona al menos una cuenta activa."
                : ytTitleInvalid
                  ? `El título de YouTube debe tener entre 1 y ${YOUTUBE_TITLE_MAX} caracteres.`
                  : `Se crearán ${totalJobs} ${totalJobs === 1 ? "tarea" : "tareas"} en Publicaciones.`}
            </span>
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="h-9 cursor-pointer rounded-md px-3.5 text-[13px] text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={
                  selectedAccounts.length === 0 ||
                  ytTitleInvalid ||
                  tiktokCaptionInvalid ||
                  igCaptionInvalid ||
                  createMutation.isPending
                }
                className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md bg-amber-400 px-4 text-[13px] font-semibold text-zinc-950 transition-colors hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {createMutation.isPending ? (
                  <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Send className="size-3.5" aria-hidden="true" />
                )}
                <span>{scheduleMode === "now" ? "Enviar ahora" : "Programar envíos"}</span>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
