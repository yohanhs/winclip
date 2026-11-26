"""Reencuadre vertical 9:16: muestreo, detección facial, cortes y filtros de `ffmpeg`.

Flujo del modo `face`: muestrear 2-4 fps con `FFMPEG_BIN` → detectar rostros con YuNet →
segmentar planos por histograma HSV → elegir el rostro principal → suavizar la trayectoria
(deadband + EMA bidireccional + límite de paneo) → simplificar con RDP → expresar el
recorte como filtro `crop` dinámico en función de `t`.
"""

from __future__ import annotations

import hashlib
import subprocess
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.pipeline.ingest import probe_media
from winclip.pipeline.render_models import (
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    ReframeRequestMode,
    ReframeResult,
)

SAMPLE_WIDTH = 640
DEFAULT_SAMPLE_FPS = 3.0
FACE_CONFIDENCE = 0.6
SHOT_THRESHOLD = 0.45
DEADBAND = 0.02
EMA_ALPHA = 0.25
MAX_SPEED = 0.22
RDP_EPSILON = 0.005
MIN_FACE_COVERAGE = 0.15
GAP_FILL_SECONDS = 1.0
MODELS_DIR = "models"
YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
VERTICAL_TOLERANCE = 0.08
ASPECT_RATIO = 9 / 16


class ReframeError(RuntimeError):
    """Fallo de reencuadre con un mensaje apto para la CLI."""


@dataclass(frozen=True)
class FaceDetection:
    """Rostro detectado con caja normalizada y confianza."""

    cx: float
    cy: float
    width: float
    height: float
    confidence: float

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


@dataclass(frozen=True)
class SampleFrame:
    """Muestra temporal del clip con sus rostros detectados."""

    time: float
    faces: tuple[FaceDetection, ...]
    histogram: np.ndarray | None = None


class FaceDetector(Protocol):
    """Detector de rostros inyectable (YuNet en producción, fakes en tests)."""

    def detect(self, frame: np.ndarray) -> list[FaceDetection]: ...


class YuNetFaceDetector:
    """Detector `cv2.FaceDetectorYN` sobre el modelo ONNX cacheado en `STORAGE_DIR/models/`."""

    def __init__(self, model_path: Path, *, score_threshold: float = FACE_CONFIDENCE) -> None:
        import cv2

        self._cv2 = cv2
        self._detector = cv2.FaceDetectorYN.create(
            str(model_path),
            "",
            (SAMPLE_WIDTH, SAMPLE_WIDTH),
            score_threshold,
            0.3,
            5000,
        )
        self._shape: tuple[int, int] | None = None

    def detect(self, frame: np.ndarray) -> list[FaceDetection]:
        height, width = frame.shape[:2]
        if self._shape != (width, height):
            self._detector.setInputSize((width, height))
            self._shape = (width, height)
        _, detections = self._detector.detect(frame)
        faces: list[FaceDetection] = []
        if detections is None:
            return faces
        for row in detections:
            x, y, box_width, box_height = (float(value) for value in row[:4])
            confidence = float(row[14])
            if box_width <= 1 or box_height <= 1:
                continue
            faces.append(
                FaceDetection(
                    cx=(x + box_width / 2) / width,
                    cy=(y + box_height / 2) / height,
                    width=box_width / width,
                    height=box_height / height,
                    confidence=confidence,
                )
            )
        return faces


def sha256_file(path: Path) -> str:
    """SHA-256 de un archivo en streaming (modelos y marcas de agua)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_yunet_model(
    settings: Settings,
    *,
    download: bool = True,
    url: str = YUNET_URL,
    expected_sha256: str = YUNET_SHA256,
) -> Path:
    """Devuelve la ruta del modelo YuNet, descargándolo y verificándolo si falta."""
    models_dir = LocalStorage(settings.storage_dir).path(MODELS_DIR)
    model_path = models_dir / YUNET_FILENAME
    if model_path.is_file():
        if sha256_file(model_path) == expected_sha256:
            return model_path
        if not download:
            raise ReframeError(f"el modelo {model_path} está corrupto; bórralo para descargarlo")
        model_path.unlink()

    if not download:
        raise ReframeError(
            f"falta el modelo de rostros {model_path}; ejecuta sin `download=False` "
            "o descárgalo manualmente desde " + url
        )

    models_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = model_path.with_suffix(".onnx.part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            tmp_path.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        tmp_path.unlink(missing_ok=True)
        raise ReframeError(
            "no se pudo descargar el modelo de detección facial "
            f"({exc}); usa `--reframe center` o `--reframe blur` sin conexión"
        ) from exc

    if sha256_file(tmp_path) != expected_sha256:
        tmp_path.unlink(missing_ok=True)
        raise ReframeError(f"el modelo descargado no coincide con el SHA-256 esperado ({url})")
    tmp_path.replace(model_path)
    return model_path


def load_face_detector(settings: Settings, *, detector: FaceDetector | None = None) -> FaceDetector:
    """Detector inyectado o YuNet real con descarga lazy del modelo."""
    if detector is not None:
        return detector
    return YuNetFaceDetector(ensure_yunet_model(settings))


def is_vertical(width: int, height: int) -> bool:
    """`True` si la fuente ya es 9:16 (con tolerancia ±0.08)."""
    if width <= 0 or height <= 0 or height <= width:
        return False
    return abs(width / height - ASPECT_RATIO) <= VERTICAL_TOLERANCE


def even(value: float) -> int:
    """Entero par más cercano (H.264 exige dimensiones pares)."""
    rounded = round(value)
    return max(2, rounded - rounded % 2)


def sample_video_frames(
    video_path: Path,
    start: float,
    end: float,
    *,
    fps: float,
    settings: Settings,
    width: int = SAMPLE_WIDTH,
) -> Iterator[tuple[float, np.ndarray]]:
    """Genera `(t_relativo, frame BGR)` muestreando `[start, end)` con `FFMPEG_BIN`."""
    duration = max(0.0, end - start)
    if duration <= 0:
        return
    info = probe_media(Path(video_path), settings)
    if not info.width or not info.height:
        raise ReframeError(f"no se pudo determinar la resolución de {video_path}")
    height = even(info.height * width / info.width)
    frame_size = width * height * 3
    command = [
        str(settings.ffmpeg_bin),
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps:g},scale={width}:{height}:flags=bilinear",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    index = 0
    try:
        while chunk := process.stdout.read(frame_size):
            if len(chunk) < frame_size:
                break
            frame = np.frombuffer(chunk, dtype=np.uint8).reshape(height, width, 3)
            yield index / fps, frame.copy()
            index += 1
    finally:
        process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
        code = process.wait()
        if code != 0 and index == 0:
            raise ReframeError(
                "ffmpeg no pudo muestrear el clip para el reencuadre: "
                + (" ".join(stderr.split())[-400:] or "sin detalle")
            )


def frame_histogram(frame: np.ndarray) -> np.ndarray:
    """Histograma HSV normalizado para comparar fotogramas consecutivos."""
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return histogram


def histogram_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Distancia de Bhattacharyya entre dos histogramas normalizados."""
    import cv2

    return float(cv2.compareHist(first, second, cv2.HISTCMP_BHATTACHARYYA))


def detect_shot_ranges(
    histograms: list[np.ndarray],
    *,
    threshold: float = SHOT_THRESHOLD,
) -> list[tuple[int, int]]:
    """Divide las muestras en planos contiguos `(primero, último)` inclusive."""
    if not histograms:
        return []
    ranges: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(histograms)):
        if histogram_distance(histograms[index - 1], histograms[index]) > threshold:
            ranges.append((start, index - 1))
            start = index
    ranges.append((start, len(histograms) - 1))
    return ranges


def select_primary_face(
    faces: Iterable[FaceDetection],
    *,
    previous_cx: float | None = None,
) -> FaceDetection | None:
    """Rostro principal por área, centralidad y continuidad con la muestra anterior."""
    candidates = [face for face in faces if face.confidence >= FACE_CONFIDENCE]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def score(face: FaceDetection) -> float:
        centrality = 1 - abs(face.cx - 0.5)
        if previous_cx is None:
            return (0.55 * face.area + 0.20 * centrality) / 0.75
        continuity = 1 - abs(face.cx - previous_cx)
        return 0.55 * face.area + 0.25 * continuity + 0.20 * centrality

    return max(candidates, key=score)


def fill_short_gaps(values: list[float | None], *, fps: float) -> list[float | None]:
    """Interpola linealmente los huecos sin detección menores a `GAP_FILL_SECONDS`."""
    filled = list(values)
    max_gap = max(1, round(GAP_FILL_SECONDS * fps))
    index = 0
    while index < len(filled):
        if filled[index] is not None:
            index += 1
            continue
        gap_start = index
        while index < len(filled) and filled[index] is None:
            index += 1
        gap = index - gap_start
        left = filled[gap_start - 1] if gap_start > 0 else None
        right = filled[index] if index < len(filled) else None
        if gap <= max_gap and left is not None and right is not None:
            for offset in range(gap):
                ratio = (offset + 1) / (gap + 1)
                filled[gap_start + offset] = left + (right - left) * ratio
    return filled


def apply_deadband(values: list[float], *, deadband: float = DEADBAND) -> list[float]:
    """Congela los micro-movimientos alrededor del último valor fijado."""
    if not values:
        return []
    smoothed = [values[0]]
    anchor = values[0]
    for value in values[1:]:
        if abs(value - anchor) > deadband:
            anchor = value
        smoothed.append(anchor)
    return smoothed


def bidirectional_ema(values: list[float], *, alpha: float = EMA_ALPHA) -> list[float]:
    """EMA de ida y vuelta (cero desfase) sobre la serie de posiciones."""
    if not values:
        return []
    forward = [values[0]]
    for value in values[1:]:
        forward.append(alpha * value + (1 - alpha) * forward[-1])
    backward = [forward[-1]]
    for value in reversed(forward[:-1]):
        backward.append(alpha * value + (1 - alpha) * backward[-1])
    backward.reverse()
    return backward


def clamp_speed(
    values: list[float],
    *,
    fps: float,
    max_speed: float = MAX_SPEED,
) -> list[float]:
    """Limita el paneo a `max_speed` del ancho fuente por segundo."""
    if not values:
        return []
    limit = max_speed / max(fps, 0.001)
    clamped = [values[0]]
    for value in values[1:]:
        previous = clamped[-1]
        clamped.append(min(max(value, previous - limit), previous + limit))
    return clamped


def simplify_rdp(
    points: list[tuple[float, float]],
    *,
    epsilon: float = RDP_EPSILON,
) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker sobre `(t, x)`, conservando los extremos."""
    if len(points) <= 2:
        return list(points)
    first, last = points[0], points[-1]
    span = last[0] - first[0]
    best_index = 0
    best_distance = -1.0
    for index in range(1, len(points) - 1):
        moment, value = points[index]
        if span <= 0:
            distance = abs(value - first[1])
        else:
            expected = first[1] + (last[1] - first[1]) * (moment - first[0]) / span
            distance = abs(value - expected)
        if distance > best_distance:
            best_distance = distance
            best_index = index
    if best_distance <= epsilon:
        return [first, last]
    left = simplify_rdp(points[: best_index + 1], epsilon=epsilon)
    right = simplify_rdp(points[best_index:], epsilon=epsilon)
    return left[:-1] + right


def smooth_track(
    times: list[float],
    values: list[float | None],
    *,
    fps: float,
) -> list[float]:
    """Rellena huecos, aplica deadband + EMA + límite de velocidad y acota a `[0, 1]`."""
    filled = fill_short_gaps(values, fps=fps)
    if not any(value is not None for value in filled):
        return [0.5] * len(filled)
    known = [value for value in filled if value is not None]
    fallback = known[0] if known else 0.5
    series = [value if value is not None else fallback for value in filled]
    series = clamp_speed(bidirectional_ema(apply_deadband(series)), fps=fps)
    return [min(1.0, max(0.0, value)) for value in series]


def build_face_track(
    samples: list[SampleFrame],
    *,
    fps: float,
) -> tuple[list[tuple[float, float]], int]:
    """Trayectoria suavizada por plano y número de muestras con rostro."""
    if not samples:
        return [], 0
    histograms = [sample.histogram for sample in samples if sample.histogram is not None]
    ranges = detect_shot_ranges(histograms) if len(histograms) == len(samples) else None
    if ranges is None:
        ranges = [(0, len(samples) - 1)]

    track: list[tuple[float, float]] = []
    detected = 0
    for first, last in ranges:
        window = samples[first : last + 1]
        positions: list[float | None] = []
        previous_cx: float | None = None
        for sample in window:
            face = select_primary_face(sample.faces, previous_cx=previous_cx)
            if face is None:
                positions.append(None)
                continue
            detected += 1
            previous_cx = face.cx
            positions.append(face.cx)

        coverage = sum(position is not None for position in positions) / len(positions)
        if coverage < MIN_FACE_COVERAGE:
            positions = [0.5] * len(positions)
        smoothed = smooth_track([sample.time for sample in window], positions, fps=fps)
        shot_points = [(sample.time, value) for sample, value in zip(window, smoothed, strict=True)]
        simplified = simplify_rdp(shot_points)
        track.extend(simplified)
    return track, detected


def analyze_faces(
    video_path: Path,
    start: float,
    end: float,
    *,
    options_fps: float,
    settings: Settings,
    detector: FaceDetector | None = None,
) -> tuple[list[tuple[float, float]], int, int]:
    """Muestrea el clip, detecta rostros y devuelve (trayectoria, rostros, planos)."""
    face_detector = load_face_detector(settings, detector=detector)
    samples: list[SampleFrame] = []
    for moment, frame in sample_video_frames(
        video_path, start, end, fps=options_fps, settings=settings
    ):
        samples.append(
            SampleFrame(
                time=moment,
                faces=tuple(face_detector.detect(frame)),
                histogram=frame_histogram(frame),
            )
        )
    track, detected = build_face_track(samples, fps=options_fps)
    histograms = [sample.histogram for sample in samples if sample.histogram is not None]
    shots = len(detect_shot_ranges(histograms)) if histograms else 1
    return track, detected, max(1, shots)


def crop_dimensions(source_width: int, source_height: int) -> tuple[int, int]:
    """Ventana 9:16 más grande posible dentro del fotograma fuente."""
    crop_width = min(source_width, even(source_height * ASPECT_RATIO))
    crop_height = (
        source_height
        if crop_width < source_width
        else min(source_height, even(crop_width / ASPECT_RATIO))
    )
    return crop_width, max(2, crop_height)


def clamp_crop(value: float, maximum: float) -> float:
    return max(0.0, min(maximum, value))


def compute_reframe(
    video_path: Path,
    start: float,
    end: float,
    *,
    mode: ReframeRequestMode = "face",
    options_fps: float = DEFAULT_SAMPLE_FPS,
    settings: Settings,
    detector: FaceDetector | None = None,
    crop_x_pct: float = 50.0,
    crop_y_pct: float = 50.0,
    zoom_pct: float = 100.0,
) -> ReframeResult:
    """Analiza la fuente y decide modo, trayectoria y dimensiones de recorte."""
    try:
        info = probe_media(Path(video_path), settings)
    except Exception as exc:
        raise ReframeError(f"no se pudo inspeccionar {video_path}: {exc}") from exc
    if not info.width or not info.height:
        raise ReframeError(f"no se pudo determinar la resolución de {video_path}")

    if is_vertical(info.width, info.height):
        return ReframeResult(
            mode="passthrough",
            track=[],
            source_width=info.width,
            source_height=info.height,
            crop_width=info.width,
            crop_height=info.height,
        )

    if mode == "blur":
        return ReframeResult(
            mode="blur",
            track=[],
            source_width=info.width,
            source_height=info.height,
            crop_width=info.width,
            crop_height=info.height,
        )

    if mode == "center":
        base_width, _ = crop_dimensions(info.width, info.height)
        crop_width = max(2, min(info.width, even(base_width * 100 / zoom_pct)))
        crop_height = max(2, min(info.height, even(crop_width / ASPECT_RATIO)))
        crop_width = max(2, min(info.width, even(crop_height * ASPECT_RATIO)))
        return ReframeResult(
            mode="center",
            track=[(0.0, min(1.0, max(0.0, crop_x_pct / 100.0)))],
            source_width=info.width,
            source_height=info.height,
            crop_width=crop_width,
            crop_height=crop_height,
        )

    track, detected, shots = analyze_faces(
        Path(video_path),
        start,
        end,
        options_fps=options_fps,
        settings=settings,
        detector=detector,
    )
    crop_width, crop_height = crop_dimensions(info.width, info.height)
    if not track:
        track = [(0.0, 0.5)]
    return ReframeResult(
        mode="face",
        track=track,
        source_width=info.width,
        source_height=info.height,
        crop_width=crop_width,
        crop_height=crop_height,
        faces_detected=detected,
        shots=shots,
    )


def crop_x_pixels(result: ReframeResult, x_norm: float) -> float:
    """Píxel del borde izquierdo del recorte para un centro normalizado."""
    limit = max(0, result.source_width - result.crop_width)
    return clamp_crop(x_norm * result.source_width - result.crop_width / 2, limit)


def static_crop_origin(
    result: ReframeResult,
    *,
    crop_x_pct: float,
    crop_y_pct: float,
) -> tuple[float, float]:
    """Origen del recorte estático para el modo `center`."""
    x = clamp_crop(
        result.source_width * crop_x_pct / 100 - result.crop_width / 2,
        max(0, result.source_width - result.crop_width),
    )
    y = clamp_crop(
        result.source_height * crop_y_pct / 100 - result.crop_height / 2,
        max(0, result.source_height - result.crop_height),
    )
    return x, y


def build_crop_expression(result: ReframeResult) -> str:
    """Expresión `x(t)` piecewise-lineal del `crop` dinámico (saltos en los cortes)."""
    points = [(moment, crop_x_pixels(result, value)) for moment, value in result.track]
    if not points:
        return f"{crop_x_pixels(result, 0.5):.2f}"
    expression = f"{points[-1][1]:.2f}"
    for index in range(len(points) - 2, -1, -1):
        moment_a, value_a = points[index]
        moment_b, value_b = points[index + 1]
        if moment_b - moment_a < 1e-6:
            segment = f"{value_b:.2f}"
        else:
            segment = (
                f"({value_a:.2f}+({value_b - value_a:.2f})*(t-{moment_a:.3f})/"
                f"{moment_b - moment_a:.3f})"
            )
        expression = f"if(lt(t,{moment_b:.3f}),{segment},{expression})"
    return expression


def build_reframe_filter(
    result: ReframeResult,
    *,
    out_width: int = OUTPUT_WIDTH,
    out_height: int = OUTPUT_HEIGHT,
    crop_x_pct: float = 50.0,
    crop_y_pct: float = 50.0,
) -> str:
    """Cadena `filter_complex` de `[0:v]` a `[vref]` para el modo elegido."""
    if result.mode == "blur":
        return (
            f"[0:v]split=2[rf_bg][rf_fg];"
            f"[rf_bg]scale={out_width}:{out_height}:force_original_aspect_ratio=increase,"
            f"crop={out_width}:{out_height},gblur=sigma=18,eq=brightness=-0.06[rf_bgv];"
            f"[rf_fg]scale={out_width}:{out_height}:force_original_aspect_ratio=decrease[rf_fgv];"
            f"[rf_bgv][rf_fgv]overlay=(W-w)/2:(H-h)/2,setsar=1[vref]"
        )

    if result.mode == "passthrough":
        return (
            f"[0:v]scale={out_width}:{out_height}:force_original_aspect_ratio=decrease,"
            f"pad={out_width}:{out_height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1[vref]"
        )

    if result.mode == "center":
        x, y = static_crop_origin(result, crop_x_pct=crop_x_pct, crop_y_pct=crop_y_pct)
        position = f"x={x:.2f}:y={y:.2f}"
    else:
        position = f"x='{build_crop_expression(result)}':y=0"
    return (
        f"[0:v]crop=w={result.crop_width}:h={result.crop_height}:{position},"
        f"scale={out_width}:{out_height}:flags=lanczos,setsar=1[vref]"
    )
