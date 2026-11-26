import type { Metadata } from "next";

import { ProjectList } from "@/components/projects";

export const metadata: Metadata = { title: "Proyectos" };

export default function ProjectsPage() {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
          Proyectos
        </h1>
        <p className="text-sm text-zinc-500">
          Cada vídeo largo (URL o archivo) con sus clips generados en 9:16.
        </p>
      </header>
      <ProjectList />
    </div>
  );
}
