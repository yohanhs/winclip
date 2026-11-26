"use client";

import { useState } from "react";
import { ProjectCard } from "./project-card";
import { useProjects } from "@/hooks/use-api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2, RefreshCw } from "lucide-react";

export function ProjectList() {
  const { data: projects, isLoading, isError, refetch } = useProjects();
  const [deletedProjectId, setDeletedProjectId] = useState<string | null>(null);

  // Filter out deleted project from the list
  const activeProjects = projects?.filter(
    (project) => project.id !== deletedProjectId,
  );

  if (isLoading) {
    return (
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardContent className="p-4">
              <div className="aspect-video bg-muted rounded-md mb-3" />
              <div className="space-y-2">
                <div className="h-4 bg-muted-foreground/20 rounded w-3/4" />
                <div className="h-3 bg-muted-foreground/20 rounded w-1/2" />
                <div className="h-3 bg-muted-foreground/20 rounded w-1/4" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center p-6">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground mb-4" />
          <p className="text-muted-foreground mb-2">Error al cargar los proyectos</p>
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Reintentar
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!activeProjects || activeProjects.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center p-8">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-12 w-12 text-muted-foreground mb-4"
          >
            <path d="M21 12V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v5h16z" />
            <path d="M3 12v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5H3z" />
            <line x1="12" y1="17" x2="12" y2="12" />
            <line x1="12" y1="12" x2="15" y2="9" />
          </svg>
          <h3 className="text-lg font-medium mb-2">No hay proyectos</h3>
          <p className="text-muted-foreground text-center mb-4">
            Crea tu primer proyecto para comenzar
          </p>
          <a
            href="/projects/new"
            className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring h-9 px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Crear proyecto
          </a>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {activeProjects.map((project) => (
        <ProjectCard
          key={project.id}
          project={project}
          onDelete={setDeletedProjectId}
        />
      ))}
    </div>
  );
}