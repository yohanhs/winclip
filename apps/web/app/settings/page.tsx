import { Activity, ArrowRight, Database, FolderCog, ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = { title: "Ajustes" };

const ITEMS = [
  {
    href: "/settings/status",
    title: "Estado del sistema",
    description:
      "Comprueba ffmpeg, whisper, ollama, claves de LLM, almacenamiento y volumen externo.",
    icon: Activity,
    cta: "Ver comprobaciones",
  },
  {
    href: "/settings/status",
    title: "Almacenamiento",
    description:
      "Los proyectos y clips se guardan en STORAGE_DIR. La ruta y el espacio libre se validan en el health check.",
    icon: Database,
    cta: "Revisar almacenamiento",
  },
];

export default function SettingsPage() {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
          Ajustes
        </h1>
        <p className="text-sm text-zinc-500">
          Configuración local de WinClip. Los secretos viven en el{" "}
          <code className="text-zinc-400">.env</code> de la raíz y nunca se
          muestran en la interfaz.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        {ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.title} href={item.href} className="group">
              <Card className="h-full transition-colors group-hover:border-white/20">
                <CardHeader>
                  <CardTitle className="flex items-center justify-between text-base">
                    <span className="flex items-center gap-2">
                      <Icon className="size-4 text-amber-400" aria-hidden="true" />
                      {item.title}
                    </span>
                    <ArrowRight
                      className="size-4 text-zinc-600 transition-transform group-hover:translate-x-0.5 group-hover:text-zinc-400"
                      aria-hidden="true"
                    />
                  </CardTitle>
                  <CardDescription>{item.description}</CardDescription>
                </CardHeader>
                <CardContent className="text-xs font-medium text-amber-400/90">
                  {item.cta}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FolderCog className="size-4 text-zinc-400" aria-hidden="true" />
            Variables de entorno
          </CardTitle>
          <CardDescription>
            Cambia los valores en el <code>.env</code> local y reinicia{" "}
            <code>pnpm dev</code>. La interfaz solo lee la configuración pública.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 text-sm text-zinc-400 sm:grid-cols-2">
            <li className="flex items-center gap-2">
              <ShieldCheck className="size-3.5 text-emerald-400" aria-hidden="true" />
              <code>STORAGE_DIR</code> · carpeta de proyectos y clips
            </li>
            <li className="flex items-center gap-2">
              <ShieldCheck className="size-3.5 text-emerald-400" aria-hidden="true" />
              <code>NEXT_PUBLIC_API_URL</code> · URL de la API para la web
            </li>
            <li className="flex items-center gap-2">
              <ShieldCheck className="size-3.5 text-emerald-400" aria-hidden="true" />
              <code>WHISPER_MODEL</code> · modelo de transcripción
            </li>
            <li className="flex items-center gap-2">
              <ShieldCheck className="size-3.5 text-emerald-400" aria-hidden="true" />
              <code>OLLAMA_HOST</code> · LLM local de respaldo
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
