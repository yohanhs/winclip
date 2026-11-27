import type { Metadata } from "next";

import { PublicationsWorkspace } from "@/components/publications/publications-workspace";

export const metadata: Metadata = { title: "Publicaciones" };

export default function PublicationsPage() {
  return <PublicationsWorkspace />;
}
