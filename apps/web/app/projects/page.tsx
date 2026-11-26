import type { Metadata } from "next";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Proyectos" };

export default function ProjectsPage() {
  return (
    <PagePlaceholder
      title="Proyectos"
      description="Cada vídeo largo (URL o archivo) con sus clips generados."
    >
      Aquí verás las cards de proyectos con su estado, duración y clips. Llega con el change
      <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">add-web-ui-cards</code>.
    </PagePlaceholder>
  );
}
