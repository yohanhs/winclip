import type { Metadata } from "next";

import { PagePlaceholder } from "@/components/page-placeholder";

export const metadata: Metadata = { title: "Cuentas" };

export default function AccountsPage() {
  return (
    <PagePlaceholder
      title="Cuentas"
      description="Cuentas de YouTube, TikTok e Instagram disponibles para publicar."
    >
      Aquí se conectarán las cuentas (API oficial o Playwright) y se revisará su estado. Llega con
      el change
      <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">add-social-accounts</code>.
    </PagePlaceholder>
  );
}
