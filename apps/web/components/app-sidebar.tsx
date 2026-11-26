"use client";

import {
  Activity,
  Folder,
  Megaphone,
  Send,
  Settings,
  Users,
  ChevronLeft,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  count?: number;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/projects", label: "Proyectos", icon: Folder, count: 0 },
  { href: "/campaigns", label: "Campañas", icon: Megaphone, count: 0 },
  { href: "/accounts", label: "Cuentas", icon: Users, count: 0 },
  { href: "/publications", label: "Publicaciones", icon: Send, count: 0 },
  { href: "/settings", label: "Ajustes", icon: Settings, count: 0 },
];

export function AppSidebar({ appName }: { appName: string }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  // TODO: Conectar con API real para obtener contadores y estado de salud
  // const { data: health } = useHealth();

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col gap-6 border-r transition-all duration-200 ease-in-out",
        "bg-sidebar",
        collapsed ? "w-16" : "w-64"
      )}
      aria-label="Navegación principal"
    >
      {/* Marca con icono W en caja ámbar */}
      <Link
        href="/"
        className={cn(
          "flex items-center gap-2 px-3 py-2 text-lg font-semibold transition-all duration-200",
          collapsed && "justify-center px-0"
        )}
        aria-label={appName}
      >
        <div className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground font-bold">
          W
        </div>
        {!collapsed && <span className="truncate">{appName}</span>}
      </Link>

      {/* Píldora superior de estado del motor local */}
      {!collapsed && (
        <Link
          href="/settings/status"
          className="flex items-center gap-2 rounded-md border border-border/50 bg-muted/30 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
          title="Ver estado del sistema"
        >
          <Activity className="size-3 text-success" aria-hidden />
          <span className="font-mono tabular-nums">M1 Local · Ready</span>
        </Link>
      )}

      {/* Navegación principal */}
      <nav aria-label="Navegación principal" className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon, count = 0 }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/10 hover:text-accent",
                active && "bg-accent/10 text-accent font-medium",
                collapsed && "justify-center px-0"
              )}
              title={collapsed ? label : undefined}
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {!collapsed && (
                <>
                  <span className="truncate flex-1">{label}</span>
                  {count > 0 && (
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-mono tabular-nums text-muted-foreground">
                      {count > 99 ? "99+" : count}
                    </span>
                  )}
                </>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Pie con resumen de almacenamiento y toggle collapse */}
      <div className="mt-auto flex flex-col gap-2 border-t border-sidebar-border pt-4">
        {!collapsed && (
          <div className="px-3 text-xs text-muted-foreground">
            <p className="font-mono tabular-nums truncate" title={process.env.STORAGE_DIR || "./storage"}>
              📁 {process.env.STORAGE_DIR || "./storage"}
            </p>
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/10 hover:text-accent mx-2",
            collapsed && "justify-center px-0"
          )}
          aria-label={collapsed ? "Expandir barra lateral" : "Colapsar barra lateral"}
          title={collapsed ? "Expandir" : "Colapsar"}
        >
          {collapsed ? (
            <ChevronRight className="size-4" aria-hidden />
          ) : (
            <>
              <ChevronLeft className="size-4" aria-hidden />
              <span>Menú</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}