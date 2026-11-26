import { Activity, ArrowRight, Settings } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = { title: "Ajustes" };

export default function SettingsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Ajustes</h1>
        <p className="text-sm text-muted-foreground">
          Configuración local de WinClip. Los secretos viven en el <code>.env</code> de la raíz y
          nunca se muestran en la interfaz.
        </p>
      </header>

      <Link href="/settings/status" className="group">
        <Card className="transition-colors group-hover:border-foreground/20">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Activity className="size-4" aria-hidden />
                Estado del sistema
              </span>
              <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
            </CardTitle>
            <CardDescription>
              Resultado del doctor: ffmpeg-full con libass, ffprobe, yt-dlp, whisper, Ollama,
              Playwright, volumen externo, almacenamiento y claves.
            </CardDescription>
          </CardHeader>
        </Card>
      </Link>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="size-4" aria-hidden />
            Preferencias
          </CardTitle>
          <CardDescription>
            Marca, presets de subtítulos y cuentas se configurarán en changes posteriores.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Por ahora todo se ajusta con variables de entorno (ver <code>.env.example</code>).
        </CardContent>
      </Card>
    </div>
  );
}
