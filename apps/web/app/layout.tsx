import type { Metadata } from "next";

import { AppSidebar } from "@/components/app-sidebar";
import { Providers } from "./providers";

import "./globals.css";

const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "WinClip";

export const metadata: Metadata = {
  title: {
    default: appName,
    template: `%s · ${appName}`,
  },
  description:
    "Clipping local: vídeos largos a shorts verticales con subtítulos y publicación.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="dark">
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>
          <div className="flex min-h-screen flex-col md:flex-row">
            <AppSidebar appName={appName} />
            <div className="flex min-w-0 flex-1 flex-col">
              <main className="min-w-0 flex-1 p-4 md:p-6 lg:p-8">{children}</main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
