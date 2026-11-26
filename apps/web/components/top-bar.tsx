"use client";

import { Search, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function TopBar({ title, children }: { title: string; children?: React.ReactNode }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b border-border bg-background/80 backdrop-blur-sm px-4">
      {/* Título de sección */}
      <div className="flex flex-1 items-center gap-4 min-w-0">
        <h1 className="truncate text-lg font-semibold">{title}</h1>
        {children}
      </div>

      {/* Buscador global */}
      <div className={cn("flex items-center gap-2 transition-all duration-200", showSearch ? "w-64" : "w-0 overflow-hidden")}>
        <label htmlFor="global-search" className="sr-only">
          Buscar proyectos, clips, cuentas…
        </label>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            id="global-search"
            type="search"
            placeholder="Buscar proyectos, clips, cuentas…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setShowSearch(true)}
            onBlur={() => setTimeout(() => setShowSearch(false), 200)}
            className="pl-9 pr-4 h-8 text-sm bg-muted/50 border-border/50 focus:border-ring focus:bg-muted"
            aria-label="Buscar proyectos, clips, cuentas…"
          />
        </div>
      </div>

      {/* Botón primario + Nuevo proyecto */}
      <Link href="/projects/new">
        <Button className="gap-2 bg-primary hover:bg-primary/90 text-primary-foreground">
          <Plus className="size-4" aria-hidden />
          <span className="hidden sm:inline">Nuevo proyecto</span>
        </Button>
      </Link>
    </header>
  );
}