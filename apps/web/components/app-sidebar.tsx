"use client";

import {
  Activity,
  Folder,
  Megaphone,
  Send,
  Settings,
  Scissors,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

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

  return (
    <aside className="flex w-60 shrink-0 flex-col gap-6 border-r bg-muted/40 p-4">
      <Link href="/" className="flex items-center gap-2 text-lg font-semibold">
        <Scissors className="size-5" aria-hidden />
        {appName}
      </Link>

      <nav aria-label="Navegación principal" className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                active && "bg-accent font-medium text-accent-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto">
        <Link
          href="/settings/status"
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
            pathname === "/settings/status" && "bg-accent font-medium text-accent-foreground",
          )}
        >
          <Activity className="size-4" aria-hidden />
          Estado del sistema
        </Link>
        <p className="px-3 pt-2 text-xs text-muted-foreground">Local · un solo usuario</p>
      </div>
    </aside>
  );
}
