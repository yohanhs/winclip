"""Motor de subtítulos basado en `.ass` (libass), determinista y apto para golden tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from winclip.pipeline.subtitles.layout import SubtitleCue, WordState, cue_scale, cue_states
from winclip.pipeline.subtitles.presets import SubtitlePreset

STYLE_NAME = "WinClip"
PLAY_RES_X = 1080
PLAY_RES_Y = 1920
BLOCK_BOTTOM_OFFSET = 0.04
POP_MILLISECONDS = 80


def ass_timestamp(seconds: float) -> str:
    """`H:MM:SS.cc` con centésimas (formato de eventos ASS)."""
    total = max(0.0, seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    centiseconds = round((secs - int(secs)) * 100)
    whole = int(secs)
    if centiseconds == 100:
        centiseconds = 0
        whole += 1
    return f"{int(hours)}:{int(minutes):02d}:{whole:02d}.{centiseconds:02d}"


def ass_color(value: str) -> str:
    """`#RRGGBB[AA]` → `&HAABBGGRR` (orden BGR de ASS)."""
    cleaned = value.lstrip("#").upper()
    red, green, blue = cleaned[0:2], cleaned[2:4], cleaned[4:6]
    alpha = cleaned[6:8] if len(cleaned) == 8 else "00"
    return f"&H{alpha}{blue}{green}{red}"


def margin_v(preset: SubtitlePreset, height: int = PLAY_RES_Y) -> int:
    """Margen inferior para que el bloque quede en la zona segura (0.62-0.70 H)."""
    bottom = min(0.70, preset.y_pct + BLOCK_BOTTOM_OFFSET)
    return max(0, round((1.0 - bottom) * height))


def _escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def _cue_text(
    cue: SubtitleCue,
    state: WordState,
    preset: SubtitlePreset,
    *,
    fit_pct: int = 100,
) -> str:
    """Texto del bloque con la palabra activa resaltada y su leve pop de escala."""
    primary = ass_color(preset.primary_color)
    highlight = ass_color(preset.highlight_color)
    pop_pct = round(fit_pct * preset.highlight_scale_pct / 100)
    pop = (
        f"{{\\c{highlight}&\\fscx{pop_pct}\\fscy{pop_pct}"
        f"\\t(0,{POP_MILLISECONDS},\\fscx{fit_pct}\\fscy{fit_pct})}}"
    )
    reset = f"{{\\c{primary}&\\fscx{fit_pct}\\fscy{fit_pct}}}"

    rendered_lines: list[str] = []
    for line_index, line in enumerate(cue.lines):
        tokens: list[str] = []
        for word_index, word in enumerate(line):
            text = _escape(word.text)
            if line_index == state.line_index and word_index == state.word_index:
                tokens.append(f"{pop}{text}{reset}")
            else:
                tokens.append(text)
        rendered_lines.append(" ".join(tokens))
    return "\\N".join(rendered_lines)


def build_ass(
    cues: list[SubtitleCue],
    preset: SubtitlePreset,
    *,
    font_name: str,
    measure: Callable[[str], float] | None = None,
) -> str:
    """Genera el contenido completo de `subs.ass` de forma determinista."""
    border_style = 3 if preset.box_bg_color else 1
    outline_colour = ass_color(preset.box_bg_color or preset.outline_color)
    back_colour = ass_color(preset.shadow_color)
    outline_width = 8 if preset.box_bg_color else preset.outline_width

    lines = [
        "[Script Info]",
        f"; WinClip · preset {preset.name} · {preset.description}".rstrip(),
        "ScriptType: v4.00+",
        f"PlayResX: {PLAY_RES_X}",
        f"PlayResY: {PLAY_RES_Y}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: {STYLE_NAME},{font_name},{preset.font_size},"
            f"{ass_color(preset.primary_color)},{ass_color(preset.primary_color)},"
            f"{outline_colour},{back_colour},0,0,0,0,100,100,0,0,{border_style},"
            f"{outline_width},{preset.shadow_depth},2,{preset.margin_x},"
            f"{preset.margin_x},{margin_v(preset)},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    max_width = PLAY_RES_X - 2 * preset.margin_x
    for cue in cues:
        scale = cue_scale(cue, measure, max_width) if measure is not None else 1.0
        fit_pct = max(20, round(scale * 100))
        prefix = f"{{\\fscx{fit_pct}\\fscy{fit_pct}}}" if fit_pct < 100 else ""
        for state in cue_states(cue):
            if state.end <= state.start:
                continue
            lines.append(
                f"Dialogue: 0,{ass_timestamp(state.start)},{ass_timestamp(state.end)},"
                f"{STYLE_NAME},,0,0,0,,{prefix}{_cue_text(cue, state, preset, fit_pct=fit_pct)}"
            )
    return "\n".join(lines) + "\n"


def write_ass(
    path: Path,
    cues: list[SubtitleCue],
    preset: SubtitlePreset,
    *,
    font_name: str,
    measure: Callable[[str], float] | None = None,
) -> Path:
    """Escribe `subs.ass` (UTF-8) y devuelve la ruta."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_ass(cues, preset, font_name=font_name, measure=measure),
        encoding="utf-8",
    )
    return path
