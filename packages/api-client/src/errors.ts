/**
 * Error tipado de la API de WinClip.
 *
 * Conserva el código HTTP y el cuerpo de error devuelto por FastAPI para que la
 * UI pueda mostrar un mensaje legible sin recurrir a `any`.
 */

function extractDetail(data: unknown): string | null {
  if (typeof data !== "object" || data === null) return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "object" && item !== null && "msg" in item) {
          const msg = (item as { msg?: unknown }).msg;
          return typeof msg === "string" ? msg : null;
        }
        return null;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) return messages.join("; ");
  }
  return null;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly data: unknown
  ) {
    const detail = extractDetail(data);
    super(detail ? `API ${status}: ${detail}` : `API ${status}`);
    this.name = "ApiError";
  }
}
