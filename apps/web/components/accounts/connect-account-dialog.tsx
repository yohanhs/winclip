"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  Globe,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import type { AccountPlatform, SocialAccountOut } from "@winclip/api-client";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useAccountsOAuthConfig,
  useBrowserLoginStatus,
  useCancelBrowserLogin,
  useConfirmBrowserLogin,
  useImportAccountTokens,
  useStartAccountOAuth,
  useStartBrowserLogin,
} from "@/hooks/use-accounts";
import { API_URL, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PlatformIcon, platformTitle } from "./platform-icon";

type ConnectTab = "oauth" | "browser" | "import";

interface ConnectAccountDialogProps {
  open: boolean;
  initialPlatform?: AccountPlatform;
  initialTab?: ConnectTab;
  reconnectAccount?: SocialAccountOut | null;
  onOpenChange: (open: boolean) => void;
}

const ALL_PLATFORMS: AccountPlatform[] = ["youtube", "tiktok", "instagram"];
const BROWSER_PLATFORMS: Array<"tiktok" | "instagram"> = ["tiktok", "instagram"];

export function ConnectAccountDialog({
  open,
  initialPlatform = "youtube",
  initialTab = "oauth",
  reconnectAccount = null,
  onOpenChange,
}: ConnectAccountDialogProps) {
  const defaultTab: ConnectTab = reconnectAccount
    ? reconnectAccount.auth_method === "playwright"
      ? "browser"
      : "oauth"
    : initialTab;
  const defaultPlatform: AccountPlatform = reconnectAccount?.platform ?? initialPlatform;
  const defaultBrowserPlatform: "tiktok" | "instagram" =
    defaultPlatform === "instagram" ? "instagram" : "tiktok";

  const [tab, setTab] = useState<ConnectTab>(defaultTab);
  const [oauthPlatform, setOauthPlatform] = useState<AccountPlatform>(defaultPlatform);
  const [oauthAlias, setOauthAlias] = useState(reconnectAccount?.alias ?? "");
  const [tiktokDirectPost, setTiktokDirectPost] = useState(false);

  const [browserPlatform, setBrowserPlatform] = useState<"tiktok" | "instagram">(
    defaultBrowserPlatform,
  );
  const [browserAlias, setBrowserAlias] = useState(reconnectAccount?.alias ?? "");
  const [activeBrowserAccountId, setActiveBrowserAccountId] = useState<string | null>(null);

  const [importPath, setImportPath] = useState("");
  const [importPlatform, setImportPlatform] = useState<"" | "youtube" | "tiktok">("");
  const [importAlias, setImportAlias] = useState("");

  const oauthConfig = useAccountsOAuthConfig();
  const startOAuth = useStartAccountOAuth();
  const startBrowser = useStartBrowserLogin();
  const confirmBrowser = useConfirmBrowserLogin();
  const cancelBrowser = useCancelBrowserLogin();
  const importTokens = useImportAccountTokens();

  const browserStatusQuery = useBrowserLoginStatus(
    activeBrowserAccountId,
    open && Boolean(activeBrowserAccountId),
  );

  const liveBrowserStatus = browserStatusQuery.data?.session_status ?? null;

  useEffect(() => {
    if (!activeBrowserAccountId || liveBrowserStatus !== "connected") return;
    toast.success("Sesión de navegador conectada");
    onOpenChange(false);
  }, [activeBrowserAccountId, liveBrowserStatus, onOpenChange]);

  const platformConfig = oauthConfig.data?.platforms.find(
    (item) => item.platform === oauthPlatform,
  );
  const isOAuthConfigured = platformConfig?.configured ?? false;
  const missingEnvVars = platformConfig?.missing ?? [];

  const handleStartOAuth = () => {
    startOAuth.mutate(
      {
        platform: oauthPlatform,
        body: {
          account_id: reconnectAccount?.id ?? null,
          direct_post: oauthPlatform === "tiktok" ? tiktokDirectPost : false,
          alias: oauthAlias.trim() || null,
        },
      },
      {
        onSuccess: (res) => {
          window.location.assign(res.auth_url);
        },
        onError: (err) => {
          toast.error("No se pudo iniciar OAuth", {
            description: errorMessage(err),
          });
        },
      },
    );
  };

  const handleStartBrowser = () => {
    startBrowser.mutate(
      {
        platform: browserPlatform,
        account_id:
          reconnectAccount?.platform === browserPlatform ? reconnectAccount.id : null,
        alias: browserAlias.trim() || null,
      },
      {
        onSuccess: (res) => {
          setActiveBrowserAccountId(res.account_id);
          toast.message("Chromium abierto", {
            description:
              "Inicia sesión manualmente (incluyendo 2FA si aplica) en la ventana visible.",
          });
        },
        onError: (err) => {
          toast.error("No se pudo abrir Chromium", {
            description: errorMessage(err),
          });
        },
      },
    );
  };

  const handleConfirmBrowser = () => {
    if (!activeBrowserAccountId) return;
    confirmBrowser.mutate(activeBrowserAccountId, {
      onError: (err) => {
        toast.error("No se pudo confirmar la sesión", {
          description: errorMessage(err),
        });
      },
    });
  };

  const handleCancelBrowser = () => {
    if (!activeBrowserAccountId) return;
    cancelBrowser.mutate(activeBrowserAccountId, {
      onSuccess: () => {
        setActiveBrowserAccountId(null);
        toast.message("Inicio de sesión en navegador cancelado");
      },
      onError: (err) => {
        toast.error("No se pudo cancelar", { description: errorMessage(err) });
      },
    });
  };

  const handleImportSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanedPath = importPath.trim();
    if (!cleanedPath) return;
    importTokens.mutate(
      {
        path: cleanedPath,
        platform: importPlatform || null,
        alias: importAlias.trim() || null,
      },
      {
        onSuccess: (accounts) => {
          toast.success(
            accounts.length === 1
              ? `Cuenta ${accounts[0]?.display_name ?? ""} importada`
              : `${accounts.length} cuentas importadas`,
            {
              description: "Credenciales cifradas en almacenamiento local.",
            },
          );
          setImportPath("");
          setImportAlias("");
          onOpenChange(false);
        },
        onError: (err) => {
          toast.error("Error al importar token", {
            description: errorMessage(err),
          });
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          setActiveBrowserAccountId(null);
        }
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent className="border-white/[0.12] bg-[#111114] text-zinc-100 sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {reconnectAccount
              ? `Reconectar ${reconnectAccount.alias || reconnectAccount.display_name}`
              : "Conectar cuenta social"}
          </DialogTitle>
          <DialogDescription className="text-zinc-400">
            Todas las credenciales OAuth se cifran con Fernet en tu disco local y los perfiles de
            navegador se aíslan por cuenta.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as ConnectTab)}
          className="mt-1 space-y-4"
        >
          <TabsList className="grid w-full grid-cols-3 bg-[#09090B]">
            <TabsTrigger value="oauth" className="gap-1.5 text-xs">
              <ShieldCheck className="size-3.5 text-sky-400" />
              <span>API Oficial</span>
            </TabsTrigger>
            <TabsTrigger value="browser" className="gap-1.5 text-xs">
              <Globe className="size-3.5 text-violet-400" />
              <span>Navegador</span>
            </TabsTrigger>
            <TabsTrigger value="import" className="gap-1.5 text-xs">
              <FolderOpen className="size-3.5 text-amber-400" />
              <span>Importar token</span>
            </TabsTrigger>
          </TabsList>

          {/* TAB 1: OAuth API Oficial */}
          <TabsContent value="oauth" className="space-y-4">
            <div className="space-y-2">
              <span className="block text-xs font-medium text-zinc-300">Plataforma</span>
              <div className="grid grid-cols-3 gap-2.5">
                {ALL_PLATFORMS.map((platform) => (
                  <button
                    key={platform}
                    type="button"
                    onClick={() => setOauthPlatform(platform)}
                    className={cn(
                      "flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border p-3 transition-colors",
                      oauthPlatform === platform
                        ? "border-amber-400/60 bg-amber-400/10 text-zinc-100"
                        : "border-white/[0.08] bg-[#09090B] text-zinc-400 hover:text-zinc-200",
                    )}
                  >
                    <PlatformIcon platform={platform} className="size-5" />
                    <span className="text-xs font-medium">{platformTitle(platform)}</span>
                  </button>
                ))}
              </div>
            </div>

            {!isOAuthConfigured && !oauthConfig.isLoading ? (
              <div
                data-testid="oauth-missing-config-guide"
                className="space-y-2 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-100"
              >
                <div className="flex items-center gap-2 font-semibold text-amber-300">
                  <AlertTriangle className="size-4 shrink-0" />
                  <span>
                    Falta configuración en <code className="font-mono">.env</code> para{" "}
                    {platformTitle(oauthPlatform)}
                  </span>
                </div>
                <p className="text-zinc-300">
                  Añade las siguientes variables en tu archivo <code className="font-mono">.env</code>{" "}
                  local (nunca en git) y reinicia la API:
                </p>
                <ul className="list-inside list-disc space-y-0.5 font-mono text-[11px] text-amber-200">
                  {missingEnvVars.map((envVar) => (
                    <li key={envVar}>{envVar}</li>
                  ))}
                </ul>
                <p className="text-[11px] text-zinc-400">
                  Redirect URI:{" "}
                  <code className="font-mono text-zinc-200">
                    {API_URL}/api/accounts/oauth/{oauthPlatform}/callback
                  </code>
                </p>
              </div>
            ) : null}

            <div className="space-y-1.5">
              <label htmlFor="oauth-alias" className="block text-xs text-zinc-300">
                Alias interno (opcional)
              </label>
              <input
                id="oauth-alias"
                type="text"
                value={oauthAlias}
                onChange={(e) => setOauthAlias(e.target.value)}
                placeholder="Ej. Canal Principal"
                className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-sm text-zinc-100 focus:border-amber-400/60 focus:outline-none"
              />
            </div>

            {oauthPlatform === "tiktok" ? (
              <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-white/[0.08] bg-[#09090B] p-3 text-xs text-zinc-300">
                <Checkbox
                  checked={tiktokDirectPost}
                  onCheckedChange={(checked) => setTiktokDirectPost(Boolean(checked))}
                />
                <span>
                  Mi app de TikTok tiene <code className="font-mono">video.publish</code> aprobado
                  (publicación directa; si no, operará en modo <strong>Solo inbox</strong>).
                </span>
              </label>
            ) : null}

            <div className="flex justify-end gap-2 border-t border-white/[0.08] pt-3">
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="h-9 rounded-md px-3.5 text-sm text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleStartOAuth}
                disabled={!isOAuthConfigured || startOAuth.isPending}
                className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-amber-400 px-4 text-sm font-semibold text-zinc-950 hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {startOAuth.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
                <span>Autorizar con {platformTitle(oauthPlatform)}</span>
              </button>
            </div>
          </TabsContent>

          {/* TAB 2: Conectar con navegador (Playwright) */}
          <TabsContent value="browser" className="space-y-4">
            <div className="space-y-2">
              <span className="block text-xs font-medium text-zinc-300">
                Plataforma (perfil persistente Chromium)
              </span>
              <div className="grid grid-cols-2 gap-2.5">
                {BROWSER_PLATFORMS.map((platform) => (
                  <button
                    key={platform}
                    type="button"
                    disabled={Boolean(activeBrowserAccountId)}
                    onClick={() => setBrowserPlatform(platform)}
                    className={cn(
                      "flex cursor-pointer items-center justify-center gap-2 rounded-lg border p-3 transition-colors disabled:opacity-60",
                      browserPlatform === platform
                        ? "border-violet-400/60 bg-violet-500/10 text-zinc-100"
                        : "border-white/[0.08] bg-[#09090B] text-zinc-400 hover:text-zinc-200",
                    )}
                  >
                    <PlatformIcon platform={platform} className="size-5" />
                    <span className="text-xs font-medium">{platformTitle(platform)}</span>
                  </button>
                ))}
              </div>
            </div>

            {!activeBrowserAccountId ? (
              <>
                <div className="space-y-1.5">
                  <label htmlFor="browser-alias" className="block text-xs text-zinc-300">
                    Alias interno (opcional)
                  </label>
                  <input
                    id="browser-alias"
                    type="text"
                    value={browserAlias}
                    onChange={(e) => setBrowserAlias(e.target.value)}
                    placeholder="Ej. TikTok Secundario"
                    className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-sm text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                  />
                </div>

                <p className="rounded-lg border border-white/[0.08] bg-[#09090B] p-3 text-xs text-zinc-400">
                  Se abrirá una ventana visible de Chromium con perfil aislado para esta cuenta.
                  Inicia sesión y completa cualquier verificación 2FA manualmente.
                </p>

                <div className="flex justify-end gap-2 border-t border-white/[0.08] pt-3">
                  <button
                    type="button"
                    onClick={() => onOpenChange(false)}
                    className="h-9 rounded-md px-3.5 text-sm text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
                  >
                    Cancelar
                  </button>
                  <button
                    type="button"
                    onClick={handleStartBrowser}
                    disabled={startBrowser.isPending}
                    className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-amber-400 px-4 text-sm font-semibold text-zinc-950 hover:bg-amber-300 disabled:opacity-50"
                  >
                    {startBrowser.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
                    <span>Conectar con navegador</span>
                  </button>
                </div>
              </>
            ) : (
              <div
                data-testid="browser-login-live-panel"
                className="space-y-3 rounded-lg border border-violet-400/30 bg-violet-500/10 p-4"
              >
                <div className="flex items-center gap-2 text-sm font-medium text-violet-200">
                  {liveBrowserStatus === "waiting" || !liveBrowserStatus ? (
                    <Loader2 className="size-4 animate-spin text-violet-300" />
                  ) : liveBrowserStatus === "connected" ? (
                    <CheckCircle2 className="size-4 text-emerald-400" />
                  ) : (
                    <AlertTriangle className="size-4 text-rose-400" />
                  )}
                  <span>
                    {liveBrowserStatus === "waiting" || !liveBrowserStatus
                      ? "Esperando inicio de sesión en Chromium…"
                      : liveBrowserStatus === "connected"
                        ? "Sesión detectada y guardada"
                        : browserStatusQuery.data?.error ||
                          `Estado: ${liveBrowserStatus}`}
                  </span>
                </div>
                <p className="text-xs text-zinc-300">
                  Si ya completaste el login en la ventana de Chromium y no se detectó
                  automáticamente, pulsa <strong>Confirmar sesión</strong>.
                </p>
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleCancelBrowser}
                    disabled={cancelBrowser.isPending}
                    className="h-8 rounded-md border border-white/[0.1] px-3 text-xs text-zinc-200 hover:bg-white/[0.06]"
                  >
                    Cancelar sesión
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmBrowser}
                    disabled={confirmBrowser.isPending}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md bg-amber-400 px-3 text-xs font-semibold text-zinc-950 hover:bg-amber-300"
                  >
                    {confirmBrowser.isPending ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : null}
                    <span>Confirmar sesión</span>
                  </button>
                </div>
              </div>
            )}
          </TabsContent>

          {/* TAB 3: Importar token existente */}
          <TabsContent value="import">
            <form onSubmit={handleImportSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="import-token-path" className="block text-xs text-zinc-300">
                  Ruta local al archivo JSON o carpeta de tokens
                </label>
                <input
                  id="import-token-path"
                  type="text"
                  required
                  value={importPath}
                  onChange={(e) => setImportPath(e.target.value)}
                  placeholder="/ruta/local/tokens/canal_youtube.json"
                  className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 font-mono text-xs text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                />
                <p className="text-[11px] text-zinc-400">
                  Modo solo lectura: WinClip cifra el token en tu almacenamiento local sin copiar
                  ni modificar el archivo original.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor="import-platform" className="block text-xs text-zinc-300">
                    Plataforma
                  </label>
                  <select
                    id="import-platform"
                    value={importPlatform}
                    onChange={(e) =>
                      setImportPlatform(e.target.value as "" | "youtube" | "tiktok")
                    }
                    className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-sm text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                  >
                    <option value="">Detectar automáticamente</option>
                    <option value="youtube">YouTube (Google Authorized User)</option>
                    <option value="tiktok">TikTok Token JSON</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="import-alias" className="block text-xs text-zinc-300">
                    Alias interno (opcional)
                  </label>
                  <input
                    id="import-alias"
                    type="text"
                    value={importAlias}
                    onChange={(e) => setImportAlias(e.target.value)}
                    placeholder="Ej. HookVault YT"
                    className="h-9 w-full rounded-md border border-white/[0.1] bg-[#09090B] px-3 text-sm text-zinc-100 focus:border-amber-400/60 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 border-t border-white/[0.08] pt-3">
                <button
                  type="button"
                  onClick={() => onOpenChange(false)}
                  className="h-9 rounded-md px-3.5 text-sm text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={!importPath.trim() || importTokens.isPending}
                  className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-amber-400 px-4 text-sm font-semibold text-zinc-950 hover:bg-amber-300 disabled:opacity-50"
                >
                  {importTokens.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
                  <span>Importar token</span>
                </button>
              </div>
            </form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
