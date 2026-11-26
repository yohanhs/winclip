import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { FileDropzone } from "@/components/projects/file-dropzone";

function makeVideoFile(name = "clip.mp4", size = 2 * 1024 * 1024): File {
  return new File([new Uint8Array(size)], name, { type: "video/mp4" });
}

describe("FileDropzone", () => {
  const onFileChange = vi.fn();

  beforeEach(() => {
    onFileChange.mockReset();
  });

  it("muestra la zona de arrastre y el límite de tamaño", () => {
    render(<FileDropzone file={null} onFileChange={onFileChange} />);
    expect(
      screen.getByText(
        /Arrastra un archivo de video aquí o haz clic para seleccionar/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/hasta 4000 MB/i)).toBeInTheDocument();
  });

  it("acepta un vídeo válido mediante el input", () => {
    render(<FileDropzone file={null} onFileChange={onFileChange} />);
    const input = screen.getByLabelText("Seleccionar archivo de vídeo");
    const file = makeVideoFile();
    fireEvent.change(input, { target: { files: [file] } });
    expect(onFileChange).toHaveBeenCalledWith(file);
  });

  it("rechaza archivos que no son vídeo", () => {
    render(<FileDropzone file={null} onFileChange={onFileChange} />);
    const input = screen.getByLabelText("Seleccionar archivo de vídeo");
    const file = new File(["texto"], "notas.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onFileChange).not.toHaveBeenCalled();
    expect(
      screen.getByText(/El archivo debe ser un vídeo/i),
    ).toBeInTheDocument();
  });

  it("muestra el archivo seleccionado y permite quitarlo", () => {
    const file = makeVideoFile("entrevista.mp4");
    render(<FileDropzone file={file} onFileChange={onFileChange} />);
    expect(screen.getByText("entrevista.mp4")).toBeInTheDocument();
    expect(screen.getByText(/2.0 MB/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Quitar archivo"));
    expect(onFileChange).toHaveBeenCalledWith(null);
  });

  it("muestra el progreso real de subida y permite cancelar", () => {
    const onCancelUpload = vi.fn();
    render(
      <FileDropzone
        file={makeVideoFile()}
        onFileChange={onFileChange}
        onCancelUpload={onCancelUpload}
        uploading
        progress={42}
      />,
    );
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("Subiendo archivo")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Cancelar subida/i }));
    expect(onCancelUpload).toHaveBeenCalledTimes(1);
  });

  it("rechaza archivos que superan el límite de tamaño", () => {
    render(
      <FileDropzone file={null} onFileChange={onFileChange} maxSizeMB={1} />,
    );
    const input = screen.getByLabelText("Seleccionar archivo de vídeo");
    const bigFile = makeVideoFile("enorme.mp4", 2 * 1024 * 1024);
    fireEvent.change(input, { target: { files: [bigFile] } });
    expect(onFileChange).not.toHaveBeenCalled();
    expect(
      screen.getByText(/El archivo supera el límite de 1 MB/i),
    ).toBeInTheDocument();
  });
});
