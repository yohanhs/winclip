import type { Metadata } from "next";

import { ProjectList } from "@/components/projects";

export const metadata: Metadata = { title: "Proyectos" };

export default function ProjectsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Proyectos</h1>
        <p className="text-sm text-muted-foreground">
          Cada vídeo largo (URL o archivo) con sus clips generados.
        </p>
      </header>
      <ProjectList />
    </div>
  );
}