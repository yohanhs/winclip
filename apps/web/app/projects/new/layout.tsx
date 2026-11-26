import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Crear Proyecto - WinClip",
  description: "Crear un nuevo proyecto de generación de clips",
};

export default function NewProjectLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}