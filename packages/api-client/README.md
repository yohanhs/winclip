# @winclip/api-client

Cliente TypeScript de la API de WinClip.

## Estado

Paquete reservado. Todavía **no** contiene código generado: se activará en el change
`add-web-ui-cards`, cuando la API exponga los endpoints de proyectos y clips.

## Plan

1. La API FastAPI publica su esquema OpenAPI en `/openapi.json`.
2. Se generan los tipos con [`openapi-typescript`](https://openapi-ts.dev/).
3. El cliente HTTP se construye con [`openapi-fetch`](https://openapi-ts.dev/openapi-fetch/).
4. La web (`apps/web`) consume `@winclip/api-client` en lugar de llamar a `fetch` a mano.

Mientras tanto, la web usa `apps/web/lib/api.ts` para el único endpoint disponible
(`GET /api/health`).
