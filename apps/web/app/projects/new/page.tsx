"use client";

import { ProjectCreateForm } from "@/components/projects/project-create-form";

export default function NewProjectPage() {
  return (
    <main className="flex-1 container mx-auto px-4 py-8 max-w-[1440px]">
      <div className="space-y-6">
        {/* Header */}
        <header>
          <h1 className="text-2xl font-bold text-zinc-100">Crear proyecto</h1>
          <p className="text-zinc-400 mt-1">
            Sube un video o pega una URL para generar clips optimizados
          </p>
        </header>

        {/* Form */}
        <ProjectCreateForm />
      </div>
    </main>
  );
}