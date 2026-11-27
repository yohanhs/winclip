import { expect, test } from "@playwright/test";

import {
  createSampleClip,
  createSampleProject,
  emitSseEvent,
  setupMockApi,
} from "./helpers/mock-api";

test.describe("Detalle de proyecto y revisión de clips (/projects/[id])", () => {
  test("avanza etapas por SSE hasta mostrar cards, permite editar, recortar/re-renderizar y multiseleccionar", async ({
    page,
  }) => {
    const processingProject = createSampleProject({
      id: "proj-live",
      title: "Episodio en vivo",
      status: "processing",
      clips_count: 0,
      active_job: {
        id: "job-live",
        type: "pipeline",
        status: "running",
        progress: 15,
        stage: "ingest",
        error: null,
        created_at: "2026-11-26T10:00:00Z",
        updated_at: "2026-11-26T10:01:00Z",
      },
      latest_job: {
        id: "job-live",
        type: "pipeline",
        status: "running",
        progress: 15,
        stage: "ingest",
        error: null,
        created_at: "2026-11-26T10:00:00Z",
        updated_at: "2026-11-26T10:01:00Z",
      },
    });

    const state = await setupMockApi(page, {
      projects: [processingProject],
      clipsByProject: { "proj-live": [] },
    });

    await page.goto("/projects/proj-live");

    await expect(page.getByText("Episodio en vivo")).toBeVisible();
    await expect(page.getByText("15%")).toBeVisible();
    await expect(
      page.getByText("Aún no hay clips en este proyecto"),
    ).toBeVisible();

    // Avance por SSE: transcripción -> selección -> clip listo -> terminado
    await emitSseEvent(page, "job.progress", {
      job_id: "job-live",
      project_id: "proj-live",
      type: "pipeline",
      status: "running",
      progress: 50,
      stage: "transcribe",
    });
    await expect(page.getByText("50%")).toBeVisible();

    const clip1 = createSampleClip({
      id: "clip-live-1",
      project_id: "proj-live",
      title: "Clip viral #1",
      score: 95,
      start_sec: 100,
      end_sec: 145,
      duration: 45,
    });
    const clip2 = createSampleClip({
      id: "clip-live-2",
      project_id: "proj-live",
      title: "Clip viral #2",
      score: 88,
      start_sec: 300,
      end_sec: 340,
      duration: 40,
    });
    state.clipsByProject["proj-live"] = [clip1, clip2];
    processingProject.status = "ready";
    processingProject.clips_count = 2;
    processingProject.active_job = null;
    processingProject.latest_job = {
      ...processingProject.latest_job!,
      status: "done",
      progress: 100,
      stage: "done",
    };

    await emitSseEvent(page, "clip.ready", {
      project_id: "proj-live",
      job_id: "job-live",
      clip_id: "clip-live-1",
      status: "rendered",
      thumb_url: "/api/clips/clip-live-1/thumb",
      video_url: "/api/clips/clip-live-1/file",
    });
    await emitSseEvent(page, "job.done", {
      job_id: "job-live",
      project_id: "proj-live",
      type: "pipeline",
      status: "done",
      progress: 100,
      stage: "done",
    });

    await expect(page.getByText("Clip viral #1")).toBeVisible();
    await expect(page.getByText("Clip viral #2")).toBeVisible();
    await expect(page.getByText("95/100")).toBeVisible();

    // Editar metadatos del primer clip
    await page.getByRole("button", { name: "Editar Clip viral #1" }).click();
    await page.getByLabel("Título").fill("Clip viral editado");
    await page.getByLabel("Hashtags").fill("#shorts #dinero");
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByText("Clip viral editado")).toBeVisible();
    expect(state.patchPayloads[0]).toMatchObject({
      clipId: "clip-live-1",
      body: { title: "Clip viral editado", hashtags: ["shorts", "dinero"] },
    });

    // Ajustar mini timeline, validar rango inválido y lanzar re-render
    await page
      .getByRole("button", { name: "Recortar Clip viral editado" })
      .click();
    await page.getByLabel("Entrada (IN · s)").fill("160");
    await expect(page.getByText(/El rango no es válido/i)).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Guardar y re-renderizar" }),
    ).toBeDisabled();

    await page.getByLabel("Entrada (IN · s)").fill("105");
    await page.getByLabel("Salida (OUT · s)").fill("150");
    await page.getByRole("button", { name: "Guardar y re-renderizar" }).click();

    await expect(page.getByText("Re-renderizando…")).toBeVisible();
    expect(state.rerenderCalls).toEqual(["clip-live-1"]);

    // Al llegar clip.ready se actualiza la card
    clip1.status = "rendered";
    clip1.updated_at = "2026-11-26T12:05:00Z";
    await emitSseEvent(page, "clip.ready", {
      project_id: "proj-live",
      job_id: "job-rerender-clip-live-1",
      clip_id: "clip-live-1",
      status: "rendered",
      thumb_url: "/api/clips/clip-live-1/thumb",
      video_url: "/api/clips/clip-live-1/file",
    });
    await expect(page.getByText("Re-renderizando…")).toBeHidden();

    // Multiselección y botón Publicar deshabilitado hasta change 8
    await page.getByLabel("Seleccionar Clip viral editado").click();
    await page.getByLabel("Seleccionar Clip viral #2").click();
    const actionBar = page.getByRole("region", {
      name: "Acciones de selección",
    });
    await expect(actionBar).toBeVisible();
    await expect(actionBar.getByText("de 2 seleccionados")).toBeVisible();
    await expect(
      actionBar.getByRole("button", { name: /Publicar en redes/i }),
    ).toBeDisabled();

    await actionBar.getByRole("button", { name: /Limpiar/i }).click();
    await expect(actionBar).toBeHidden();
  });

  test("se adapta a móvil sin desbordamiento horizontal", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMockApi(page);

    await page.goto("/projects/proj-e2e-1");
    await expect(
      page.getByText("El error que te cuesta 500 al mes"),
    ).toBeVisible();

    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
