import type { Metadata } from "next";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Campañas" };

export default function CampaignsPage() {
  return (
    <PagePlaceholder
      title="Campañas"
      description="Reglas de estilo y selección que se aplican a los clips."
    >
      Aquí se editarán las reglas de campaña (duración, temas, tono, hashtags…). Llega con el
      change
      <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">add-campaign-rules</code>.
    </PagePlaceholder>
  );
}
