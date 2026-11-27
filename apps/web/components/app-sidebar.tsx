"use client";

import {
  Activity,
  ChevronLeft,
  ChevronRight,
  Folder,
  HardDrive,
  Megaphone,
  Menu,
  Send,
  Settings,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useAccounts } from "@/hooks/use-accounts";
import { useHealth } from "@/hooks/use-api-client";
import { useCampaigns } from "@/hooks/use-campaigns";
import { useProjects } from "@/hooks/use-projects";
import { usePublications } from "@/hooks/use-publications";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/projects", label: "Proyectos", icon: Folder },
  { href: "/campaigns", label: "Campañas", icon: Megaphone },
  { href: "/accounts", label: "Cuentas", icon: Users },
  { href: "/publications", label: "Publicaciones", icon: Send },
  { href: "/settings", label: "Ajustes", icon: Settings },
];

export function AppSidebar({ appName }: { appName: string }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const health = useHealth();
  const projects = useProjects();
  const campaigns = useCampaigns();
  const accounts = useAccounts();
  const publications = usePublications();

  const checks = health.data?.checks ?? [];
  const hasError = health.isError || checks.some((check) => check.status === "error");
  const hasWarn = checks.some((check) => check.status === "warn");
  const storageCheck = checks.find((check) =>
    check.name.toLowerCase().includes("storage"),
  );
  const projectCount = projects.data?.length ?? 0;
  const campaignCount = campaigns.data?.length ?? 0;
  const accountCount = accounts.data?.length ?? 0;
  const pendingPublicationsCount = (publications.data ?? []).filter(
    (item) => item.status === "scheduled" || item.status === "publishing",
  ).length;
  const expiredAccountsCount = (accounts.data ?? []).filter(
    (item) => item.status === "expired" || item.status === "error",
  ).length;

  const engineStatus = hasError
    ? { label: "Motor local · Error", color: "text-rose-400" }
    : hasWarn
      ? { label: "Motor local · Avisos", color: "text-amber-400" }
      : health.data
        ? { label: "Motor local · Listo", color: "text-emerald-400" }
        : { label: "Comprobando motor…", color: "text-zinc-500" };

  const renderNavLinks = (isCompact: boolean, onSelect?: () => void) => (
    <nav aria-label="Navegación principal" className="flex flex-col gap-1 px-2">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        const count =
          href === "/projects"
            ? projectCount
            : href === "/campaigns"
              ? campaignCount
              : href === "/accounts"
                ? accountCount
                : href === "/publications"
                  ? pendingPublicationsCount
                  : 0;
        const showExpiredAlert = href === "/accounts" && expiredAccountsCount > 0;
        return (
          <Link
            key={href}
            href={href}
            onClick={onSelect}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-zinc-400 transition-colors hover:bg-white/[0.06] hover:text-zinc-100",
              active && "bg-amber-400/12 font-medium text-amber-300",
              isCompact && "justify-center px-0",
            )}
            title={isCompact ? label : undefined}
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            {!isCompact ? (
              <>
                <span className="flex-1 truncate">{label}</span>
                {showExpiredAlert ? (
                  <span
                    data-testid="sidebar-expired-accounts"
                    title={`${expiredAccountsCount} cuenta(s) expirada(s) o con error`}
                    className="flex min-w-5 items-center justify-center rounded-full border border-rose-500/40 bg-rose-500/15 px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-rose-300"
                  >
                    {expiredAccountsCount > 99 ? "99+" : expiredAccountsCount}
                  </span>
                ) : count > 0 ? (
                  <span className="flex min-w-5 items-center justify-center rounded-full bg-white/[0.06] px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-zinc-400">
                    {count > 99 ? "99+" : count}
                  </span>
                ) : null}
              </>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <>
      {/* Barra móvil (< md) para evitar desbordamiento horizontal */}
      <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#0D0D10] px-4 py-3 md:hidden">
        <Link href="/projects" className="flex items-center gap-2 text-base font-semibold">
          <span className="flex size-7 items-center justify-center rounded-md bg-amber-400 font-bold text-zinc-950">
            W
          </span>
          <span className="truncate text-zinc-100">{appName}</span>
        </Link>
        <div className="flex items-center gap-2">
          <Link
            href="/settings/status"
            className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-white/[0.03] px-2 py-1 font-mono text-[11px] text-zinc-300"
          >
            <Activity className={cn("size-3", engineStatus.color)} aria-hidden="true" />
            <span>Estado</span>
          </Link>
          <button
            type="button"
            onClick={() => setMobileOpen((open) => !open)}
            aria-label={mobileOpen ? "Cerrar menú" : "Abrir menú"}
            className="flex size-8 items-center justify-center rounded-md border border-white/[0.08] text-zinc-300 hover:bg-white/[0.06]"
          >
            {mobileOpen ? (
              <X className="size-4" aria-hidden="true" />
            ) : (
              <Menu className="size-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {mobileOpen ? (
        <div className="border-b border-white/[0.08] bg-[#0D0D10] py-3 md:hidden">
          {renderNavLinks(false, () => setMobileOpen(false))}
        </div>
      ) : null}

      {/* Sidebar escritorio (>= md) */}
      <aside
        className={cn(
          "hidden shrink-0 flex-col gap-5 border-r border-white/[0.08] bg-[#0D0D10] py-4 transition-all duration-200 ease-in-out md:flex",
          collapsed ? "w-[68px]" : "w-[240px]",
        )}
        aria-label="Navegación principal"
      >
        <Link
          href="/projects"
          className={cn(
            "flex items-center gap-2.5 px-4 text-lg font-semibold transition-all duration-200",
            collapsed && "justify-center px-0",
          )}
          aria-label={appName}
        >
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-amber-400 font-bold text-zinc-950">
            W
          </div>
          {!collapsed ? <span className="truncate text-zinc-100">{appName}</span> : null}
        </Link>

        {!collapsed ? (
          <div className="px-3">
            <Link
              href="/settings/status"
              className="flex items-center gap-2 rounded-md border border-white/[0.08] bg-[#111114] px-3 py-2 text-xs text-zinc-300 transition-colors hover:border-white/[0.16] hover:text-zinc-100"
              title="Ver estado real del motor local"
            >
              <Activity className={cn("size-3.5 shrink-0", engineStatus.color)} aria-hidden="true" />
              <span className="truncate font-mono tabular-nums">{engineStatus.label}</span>
            </Link>
          </div>
        ) : null}

        {renderNavLinks(collapsed)}

        <div className="mt-auto flex flex-col gap-2 border-t border-white/[0.08] pt-3">
          {!collapsed ? (
            <Link
              href="/settings/status"
              className="mx-3 flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-zinc-500 transition-colors hover:bg-white/[0.04] hover:text-zinc-300"
              title={storageCheck?.detail ?? "Revisar almacenamiento local"}
            >
              <HardDrive className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate font-mono tabular-nums">
                {storageCheck?.detail ?? "Almacenamiento local"}
              </span>
            </Link>
          ) : null}
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            className={cn(
              "mx-2 flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs text-zinc-400 transition-colors hover:bg-white/[0.06] hover:text-zinc-100",
              collapsed && "px-0",
            )}
            aria-label={collapsed ? "Expandir barra lateral" : "Colapsar barra lateral"}
            title={collapsed ? "Expandir" : "Colapsar"}
          >
            {collapsed ? (
              <ChevronRight className="size-4" aria-hidden="true" />
            ) : (
              <>
                <ChevronLeft className="size-4" aria-hidden="true" />
                <span>Colapsar</span>
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
