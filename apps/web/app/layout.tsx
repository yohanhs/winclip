import type { Metadata } from "next";

import { AppSidebar } from "@/components/app-sidebar";

import "./globals.css";
import { Providers } from "./providers";

const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "WinClip";

export const metadata: Metadata = {
  title: {
    default: appName,
    template: `%s · ${appName}`,
  },
  description: "Clipping local: vídeos largos a shorts verticales con subtítulos y publicación.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <Providers>
          <div className="flex min-h-screen">
            <AppSidebar appName={appName} />
            <main className="min-w-0 flex-1 p-8">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
