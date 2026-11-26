import { ArrowRight, Activity } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";

const SECTIONS = [
  {
    href: "/projects",
    title: "Proyectos",
    description: "Vídeos largos convertidos en shorts, con su estado y sus clips.",
  },
  {
    href: "/campaigns",
    title: "Campañas",
    description: "Reglas de estilo, duración y temas para cada tanda de clips.",
  },
  {
    href: "/accounts",
    title: "Cuentas",
    description: "Cuentas de YouTube, TikTok e Instagram configuradas.",
  },
  {
    href: "/publications",
    title: "Publicaciones",
    description: "Cola de publicación, resultados y enlaces externos.",
  },
];

export default function HomePage() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8">
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">Panel de WinClip</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Base del monorepo: API, web y diagnóstico. El pipeline de clipping se irá habilitando en los
          siguientes changes.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        {SECTIONS.map((section) => (
          <Link key={section.href} href={section.href} className="group">
            <Card className="h-full transition-colors group-hover:border-foreground/20">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  {section.title}
                  <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
                </CardTitle>
                <CardDescription>{section.description}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="size-4" aria-hidden />
            Estado del sistema
          </CardTitle>
          <CardDescription>
            Comprueba ffmpeg-full, el modelo de transcripción, Ollama, Playwright y el
            almacenamiento antes de ejecutar el pipeline.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/settings/status" className={buttonVariants({ variant: "outline" })}>
            Ver diagnóstico
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
