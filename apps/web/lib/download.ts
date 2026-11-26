import type { ClipOut } from "@winclip/api-client";

import { mediaUrl } from "@/lib/api";

/** Descarga el MP4 del clip forzando un blob local. */
export async function downloadClipFile(clip: ClipOut): Promise<void> {
  const url = mediaUrl(clip.video_url, clip.updated_at);
  if (!url) throw new Error("El clip todavía no tiene vídeo renderizado");

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`No se pudo descargar el clip (${response.status})`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const safeTitle = clip.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  anchor.href = objectUrl;
  anchor.download = `${safeTitle || clip.id}.mp4`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
