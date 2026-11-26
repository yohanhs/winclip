"""Resolución de fuentes OFL y locales para los subtítulos.

Las fuentes se indexan leyendo la tabla `name` del propio archivo: la familia (`nameID 1`)
y el nombre completo (`nameID 4`) son los que `libass` compara al buscar en `fontsdir`.
Los presets usan nombres legibles (`Montserrat ExtraBold`) y aquí se resuelven al archivo
y al nombre que `libass` entiende de forma unívoca.
"""

from __future__ import annotations

import contextlib
import shutil
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from winclip.core.config import ROOT_DIR, Settings

FONTS_DIRNAME = "assets/fonts"
FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc"})
_NAME_IDS = (1, 2, 4, 6, 16, 17)


@dataclass(frozen=True)
class FontFile:
    """Fuente indexada con sus nombres tal como los ve `libass`."""

    path: Path
    family: str
    style: str
    full_name: str
    postscript_name: str

    @property
    def ass_name(self) -> str:
        """Nombre que se escribe en el estilo `.ass` (nombre completo, único por archivo)."""
        return self.full_name or self.family


@dataclass(frozen=True)
class ResolvedFont:
    """Fuente efectiva, con aviso si hubo que usar el respaldo OFL."""

    requested: str
    font: FontFile
    effective_name: str = ""
    fallback_used: bool = False
    warning: str | None = None

    @property
    def name(self) -> str:
        """Nombre legible de la fuente usada (lo que registra `render.json`)."""
        return self.effective_name or self.font.full_name or self.font.family

    @property
    def ass_name(self) -> str:
        return self.font.ass_name


def _normalize(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def read_font_names(path: Path) -> dict[int, str]:
    """Lee los `nameID` relevantes de la tabla `name` de un TTF/OTF (sin dependencias)."""
    try:
        data = Path(path).read_bytes()
        if data[:4] == b"ttcf":
            return {}
        table_count = struct.unpack(">H", data[4:6])[0]
        tables: dict[str, tuple[int, int]] = {}
        for index in range(table_count):
            offset = 12 + index * 16
            tag = data[offset : offset + 4].decode("latin-1")
            table_offset, table_length = struct.unpack(">II", data[offset + 8 : offset + 16])
            tables[tag] = (table_offset, table_length)
        if "name" not in tables:
            return {}
        name_offset, _ = tables["name"]
        count, string_offset = struct.unpack(">HH", data[name_offset + 2 : name_offset + 6])
        names: dict[int, str] = {}
        for index in range(count):
            record = name_offset + 6 + index * 12
            platform_id, _, language_id, name_id, length, offset = struct.unpack(
                ">HHHHHH", data[record : record + 12]
            )
            if name_id not in _NAME_IDS or platform_id != 3 or language_id != 0x409:
                continue
            start = name_offset + string_offset + offset
            names.setdefault(name_id, data[start : start + length].decode("utf-16-be", "replace"))
        return names
    except (OSError, struct.error, UnicodeDecodeError, IndexError):
        return {}


def describe_font(path: Path) -> FontFile | None:
    """Construye un `FontFile`; devuelve `None` si el archivo no es una fuente válida."""
    names = read_font_names(path)
    family = names.get(1) or names.get(16) or ""
    style = names.get(2) or names.get(17) or ""
    full_name = names.get(4) or ""
    postscript_name = names.get(6) or ""
    if not family:
        try:
            from PIL import ImageFont

            family, style = ImageFont.truetype(str(path), 24).getname()
            full_name = full_name or f"{family} {style}".strip()
        except (OSError, ValueError):
            return None
    if not full_name:
        full_name = f"{family} {style}".strip() or family
    return FontFile(
        path=Path(path),
        family=family,
        style=style,
        full_name=full_name,
        postscript_name=postscript_name,
    )


class FontIndex:
    """Índice de fuentes por nombre normalizado (familia, nombre completo y archivo)."""

    def __init__(self) -> None:
        self._fonts: dict[str, FontFile] = {}

    def add(self, path: Path) -> None:
        font = describe_font(path)
        if font is None:
            return
        keys = {
            font.family,
            font.full_name,
            font.postscript_name,
            f"{font.family} {font.style}".strip(),
            Path(font.path).stem,
        }
        for key in keys:
            normalized = _normalize(key)
            if normalized:
                self._fonts.setdefault(normalized, font)

    def add_tree(self, directory: Path) -> None:
        if not directory.is_dir():
            return
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in FONT_SUFFIXES:
                self.add(path)

    def resolve(self, name: str) -> FontFile | None:
        return self._fonts.get(_normalize(name))

    def __len__(self) -> int:
        return len({id(font) for font in self._fonts.values()})


@dataclass
class FontsLookup:
    """Índice de `assets/fonts/` con carga perezosa de `USER_FONTS_DIR`."""

    settings: Settings
    assets_dir: Path = ROOT_DIR / FONTS_DIRNAME
    _index: FontIndex = field(default_factory=FontIndex)
    _assets_loaded: bool = False
    _user_loaded: bool = False

    @property
    def index(self) -> FontIndex:
        if not self._assets_loaded:
            self._index.add_tree(self.assets_dir)
            self._assets_loaded = True
        return self._index

    def _load_user_fonts(self) -> None:
        if self._user_loaded:
            return
        self._user_loaded = True
        user_dir = Path(self.settings.user_fonts_dir).expanduser()
        if user_dir.is_dir() and user_dir.resolve() != self.assets_dir.resolve():
            self._index.add_tree(user_dir)

    def resolve(self, name: str) -> FontFile | None:
        found = self.index.resolve(name)
        if found is not None:
            return found
        self._load_user_fonts()
        return self.index.resolve(name)


def resolve_font(
    requested: str,
    *,
    fallback: str,
    settings: Settings,
    lookup: FontsLookup | None = None,
) -> ResolvedFont:
    """Resuelve la fuente pedida o el respaldo OFL del preset, sin fallar nunca."""
    lookup = lookup or FontsLookup(settings)
    found = lookup.resolve(requested)
    if found is not None:
        return ResolvedFont(requested=requested, font=found, effective_name=requested)
    fallback_font = lookup.resolve(fallback)
    if fallback_font is None:
        raise FileNotFoundError(
            f"no se encontró la fuente {requested!r} ni el respaldo {fallback!r} en "
            f"{lookup.assets_dir}"
        )
    return ResolvedFont(
        requested=requested,
        font=fallback_font,
        effective_name=fallback,
        fallback_used=True,
        warning=(f"fuente {requested!r} no encontrada; se usa el respaldo OFL {fallback!r}"),
    )


def measure_font(font_path: Path, size: int):
    """Devuelve `measure(text) -> ancho en px` con la fuente y tamaño dados."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(font_path), size)
    canvas = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def measure(text: str) -> float:
        return float(canvas.textlength(text, font=font))

    return measure


@contextlib.contextmanager
def fonts_directory(fonts: list[FontFile], *, directory: Path | None = None):
    """Directorio temporal con enlaces a las fuentes para `fontsdir=` de libass."""
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
        for font in fonts:
            target = directory / Path(font.path).name
            if not target.exists():
                with contextlib.suppress(OSError):
                    target.symlink_to(Path(font.path).resolve())
        yield directory
        return

    tmp = Path(tempfile.mkdtemp(prefix="winclip-fonts-"))
    try:
        seen: set[str] = set()
        for font in fonts:
            name = Path(font.path).name
            if name in seen:
                continue
            seen.add(name)
            with contextlib.suppress(OSError):
                (tmp / name).symlink_to(Path(font.path).resolve())
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
