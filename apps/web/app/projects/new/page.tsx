import type { Metadata } from "next";

import { ProjectCreateForm } from "@/components/projects/project-create-form";

export const metadata: Metadata = { title: "Crear proyecto" };

export default function NewProjectPage() {
  return (
    <main className="mx-auto w-full max-w-[1400px] space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
          Crear proyecto
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Sube un vídeo o pega una URL para generar clips verticales con
          subtítulos.
        </p>
      </header>

      <ProjectCreateForm />
    </main>
  );
}
