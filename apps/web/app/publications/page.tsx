import type { Metadata } from "next";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Publicaciones" };

export default function PublicationsPage() {
  return (
    <PagePlaceholder
      title="Publicaciones"
      description="Historial y cola de publicación de clips en cada red."
    >
      Aquí verás el estado de cada publicación, sus enlaces externos y los errores. Llega con el
      change
      <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">add-publishers</code>.
    </PagePlaceholder>
  );
}
