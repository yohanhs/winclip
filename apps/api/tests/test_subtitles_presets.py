"""Tests de presets de subtítulos y resolución de fuentes."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from winclip.core.config import ROOT_DIR, Settings
from winclip.pipeline.subtitles.fonts import (
    FontsLookup,
    fonts_directory,
    resolve_font,
)
from winclip.pipeline.subtitles.presets import (
    SubtitlePreset,
    SubtitlePresetError,
    list_presets,
    load_preset,
    presets_dir,
)

EXPECTED_PRESETS = ["bold-yellow", "clean-white", "hormozi", "mrbeast"]


def _settings(tmp_path: Path, *, user_fonts: Path | None = None) -> Settings:
    payload = {"_env_file": None, "storage_dir": tmp_path / "storage"}
    if user_fonts is not None:
        payload["user_fonts_dir"] = user_fonts
    return Settings(**payload)


def test_all_presets_are_present_and_valid() -> None:
    assert list_presets() == EXPECTED_PRESETS
    for name in EXPECTED_PRESETS:
        preset = load_preset(name)
        assert preset.name == name
        assert preset.fallback_font
        assert 0.62 <= preset.y_pct <= 0.70
        assert preset.max_lines <= 2


def test_preset_typography_matches_design() -> None:
    bold = load_preset("bold-yellow")
    assert bold.font == "Montserrat ExtraBold"
    assert bold.highlight_color == "#FFD600"
    assert bold.max_words_per_cue == 7

    hormozi = load_preset("hormozi")
    assert hormozi.uppercase is True
    assert hormozi.max_words_per_cue == 3
    assert hormozi.highlight_scale_pct == 118

    clean = load_preset("clean-white")
    assert clean.box_bg_color == "#00000088"

    mrbeast = load_preset("mrbeast")
    assert mrbeast.font == "Anton"
    assert mrbeast.max_chars_per_line == 18


def test_missing_preset_lists_available() -> None:
    with pytest.raises(SubtitlePresetError, match="bold-yellow"):
        load_preset("no-existe")


def test_invalid_preset_json_is_reported(tmp_path: Path) -> None:
    directory = tmp_path / "presets"
    directory.mkdir()
    (directory / "roto.json").write_text("{ no es json", encoding="utf-8")
    with pytest.raises(SubtitlePresetError, match="roto"):
        load_preset("roto", directory=directory)

    (directory / "fuera.json").write_text('{"name": "x"}', encoding="utf-8")
    with pytest.raises(SubtitlePresetError, match="inválido"):
        load_preset("fuera", directory=directory)


def test_preset_rejects_palette_and_safe_zone_errors() -> None:
    payload = load_preset("bold-yellow").model_dump()
    with pytest.raises(ValueError, match="color inválido"):
        SubtitlePreset.model_validate({**payload, "primary_color": "blanco"})
    with pytest.raises(ValueError):
        SubtitlePreset.model_validate({**payload, "y_pct": 0.9})
    with pytest.raises(ValueError):
        SubtitlePreset.model_validate({**payload, "max_lines": 3})


def test_presets_dir_points_to_repository_assets() -> None:
    assert presets_dir() == ROOT_DIR / "assets" / "subtitle-presets"
    assert presets_dir().is_dir()


def test_resolve_ofl_fonts_from_assets(tmp_path: Path) -> None:
    settings = _settings(tmp_path, user_fonts=tmp_path / "sin-fuentes")

    bold = resolve_font("Montserrat ExtraBold", fallback="Anton", settings=settings)
    assert bold.fallback_used is False
    assert bold.font.path.name == "Montserrat-ExtraBold.ttf"
    assert "Montserrat" in bold.ass_name

    anton = resolve_font("Anton", fallback="Inter", settings=settings)
    assert anton.font.path.name == "Anton-Regular.ttf"


def test_missing_font_falls_back_to_ofl_with_warning(tmp_path: Path) -> None:
    settings = _settings(tmp_path, user_fonts=tmp_path / "sin-fuentes")

    resolved = resolve_font("GothamBlack", fallback="Montserrat ExtraBold", settings=settings)

    assert resolved.fallback_used is True
    assert "GothamBlack" in (resolved.warning or "")
    assert resolved.font.path.name == "Montserrat-ExtraBold.ttf"


def test_local_commercial_font_wins_when_present(tmp_path: Path) -> None:
    user_fonts = tmp_path / "LibraryFonts"
    user_fonts.mkdir()
    shutil.copyfile(
        ROOT_DIR / "assets" / "fonts" / "inter" / "Inter-Bold.ttf",
        user_fonts / "GothamBlack.ttf",
    )
    settings = _settings(tmp_path, user_fonts=user_fonts)

    resolved = resolve_font("GothamBlack", fallback="Anton", settings=settings)

    assert resolved.fallback_used is False
    assert resolved.font.path == user_fonts / "GothamBlack.ttf"


def test_font_lookup_indexes_lazily(tmp_path: Path) -> None:
    settings = _settings(tmp_path, user_fonts=tmp_path / "sin-fuentes")
    lookup = FontsLookup(settings)

    assert lookup.resolve("Montserrat Black") is not None
    assert lookup.resolve("no-existe") is None


def test_fonts_directory_links_and_cleans_up(tmp_path: Path) -> None:
    settings = _settings(tmp_path, user_fonts=tmp_path / "sin-fuentes")
    font = resolve_font("Anton", fallback="Anton", settings=settings).font

    with fonts_directory([font]) as directory:
        link = Path(directory) / "Anton-Regular.ttf"
        assert link.exists()
        assert link.resolve() == font.path.resolve()
    assert not Path(directory).exists()
