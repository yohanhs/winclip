import type { Metadata } from "next";

import { CampaignsWorkspace } from "@/components/campaigns/campaigns-workspace";

export const metadata: Metadata = { title: "Campañas" };

export default function CampaignsPage() {
  return <CampaignsWorkspace />;
}
