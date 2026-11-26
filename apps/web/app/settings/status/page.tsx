import type { Metadata } from "next";

import { StatusClient } from "@/components/status-client";

export const metadata: Metadata = { title: "Estado del sistema" };

export default function StatusPage() {
  return <StatusClient />;
}
