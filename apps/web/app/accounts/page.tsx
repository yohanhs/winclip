import { Suspense } from "react";
import type { Metadata } from "next";

import { AccountsWorkspace } from "@/components/accounts/accounts-workspace";

export const metadata: Metadata = { title: "Cuentas" };

export default function AccountsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-zinc-400">Cargando cuentas…</div>}>
      <AccountsWorkspace />
    </Suspense>
  );
}
