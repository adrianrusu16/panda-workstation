"""Pinned local font shaping and glyph outlines using a private Pango font map."""
import ctypes
from ctypes.util import find_library
from functools import lru_cache
import hashlib

from visual_assets import ASSETS, verified_assets


def pointer(obj):
    get = ctypes.pythonapi.PyCapsule_GetPointer
    get.argtypes = (ctypes.py_object, ctypes.c_char_p)
    get.restype = ctypes.c_void_p
    return get(obj.__gpointer__, None)


class Metrics:
    def __init__(self):
        try:
            import gi
            gi.require_version("Pango", "1.0")
            gi.require_version("PangoCairo", "1.0")
            from gi.repository import Pango, PangoCairo
            import cairo
        except (ImportError, ValueError) as error:
            raise ValueError("accurate visual export requires existing PyGObject/PangoCairo and pycairo; no fallback") from error
        self.Pango, self.PangoCairo, self.cairo = Pango, PangoCairo, cairo
        receipt, data, _ = verified_assets()
        self.font = ASSETS / "NotoSans-Regular.ttf"
        # Pango's set_config is a documented C API unavailable to GI bindings.
        self.fc = ctypes.CDLL(find_library("fontconfig") or "libfontconfig.so.1")
        self.pfc = ctypes.CDLL(find_library("pangoft2-1.0") or "libpangoft2-1.0.so.0")
        self.fc.FcConfigCreate.restype = ctypes.c_void_p
        self.fc.FcConfigAppFontAddFile.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
        self.fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        self.fc.FcConfigBuildFonts.argtypes = (ctypes.c_void_p,)
        self.fc.FcConfigBuildFonts.restype = ctypes.c_int
        self.fc.FcConfigDestroy.argtypes = (ctypes.c_void_p,)
        self.fc.FcGetVersion.restype = ctypes.c_int
        self.pfc.pango_fc_font_map_set_config.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        self.pfc.pango_fc_font_get_pattern.argtypes = (ctypes.c_void_p,)
        self.pfc.pango_fc_font_get_pattern.restype = ctypes.c_void_p
        self.fc.FcPatternGetString.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                                              ctypes.POINTER(ctypes.c_char_p))
        self.fc.FcPatternGetString.restype = ctypes.c_int
        config = self.fc.FcConfigCreate()
        if not config:
            raise ValueError("private font configuration unavailable")
        try:
            if not self.fc.FcConfigAppFontAddFile(config, bytes(self.font)) or not self.fc.FcConfigBuildFonts(config):
                raise ValueError("pinned font could not be loaded")
            self.fontmap = PangoCairo.FontMap.new()
            self.pfc.pango_fc_font_map_set_config(pointer(self.fontmap), config)
        finally:
            self.fc.FcConfigDestroy(config)  # Pango retains its own reference.
        self.context = self.fontmap.create_context()
        self.context.set_language(Pango.Language.from_string("en"))
        options = cairo.FontOptions()
        options.set_hint_style(cairo.HINT_STYLE_NONE)
        options.set_hint_metrics(cairo.HINT_METRICS_OFF)
        PangoCairo.context_set_font_options(self.context, options)
        PangoCairo.context_set_resolution(self.context, 96)
        description = Pango.FontDescription.from_string("Noto Sans")
        description.set_absolute_size(14 * Pango.SCALE)
        font = self.fontmap.load_font(self.context, description)
        if font is None:
            raise ValueError("pinned font unavailable")
        path = ctypes.c_char_p()
        pattern = self.pfc.pango_fc_font_get_pattern(pointer(font))
        if self.fc.FcPatternGetString(pattern, b"file", 0, ctypes.byref(path)) != 0 or path.value != bytes(self.font):
            raise ValueError("resolved font identity mismatch; no system fallback permitted")
        self.provenance = dict(family="Noto Sans", version=receipt["font"]["version"],
                               sha256=hashlib.sha256(data["NotoSans-Regular.ttf"]).hexdigest(),
                               pango=Pango.version_string(), cairo=cairo.cairo_version_string(),
                               fontconfig=self.fc.FcGetVersion(), resolution=96,
                               hint_metrics="off", language="en", fallback=False,
                               font_file="NotoSans-Regular.ttf")

    def layout(self, text, size, width=None):
        Pango = self.Pango
        description = Pango.FontDescription.from_string("Noto Sans")
        description.set_absolute_size(size * Pango.SCALE)
        layout = Pango.Layout.new(self.context)
        layout.set_font_description(description)
        attributes = Pango.AttrList()
        attributes.insert(Pango.attr_fallback_new(False))
        attributes.insert(Pango.attr_font_features_new("tnum=1"))
        layout.set_attributes(attributes)
        layout.set_text(text, -1)
        layout.set_single_paragraph_mode(True)
        if width is not None:
            layout.set_width(int(width * Pango.SCALE))
            layout.set_height(-1)
            layout.set_ellipsize(Pango.EllipsizeMode.END)
        if layout.get_unknown_glyphs_count():
            raise ValueError("unsupported glyph in pinned font; fallback refused")
        return layout

    @lru_cache(maxsize=2048)
    def shape(self, text, size, width=None):
        layout = self.layout(text, size, width)
        ink, logical = layout.get_extents()
        cr = self.cairo.Context(self.cairo.RecordingSurface(self.cairo.CONTENT_COLOR_ALPHA, None))
        self.PangoCairo.layout_path(cr, layout)
        x1, y1, x2, y2 = cr.path_extents()
        commands = []
        for kind, values in cr.copy_path():
            command = {self.cairo.PATH_MOVE_TO: "M", self.cairo.PATH_LINE_TO: "L",
                       self.cairo.PATH_CURVE_TO: "C", self.cairo.PATH_CLOSE_PATH: "Z"}[kind]
            commands.append(command + " ".join(f"{n:.5f}".rstrip("0").rstrip(".") if n else "0" for n in values))
        scale = self.Pango.SCALE
        return dict(path=" ".join(commands), ink=[x1, y1, x2 - x1, y2 - y1],
                    width=logical.width / scale, height=logical.height / scale,
                    ellipsized=layout.is_ellipsized())

    def measure(self, text, size):
        return {key: value for key, value in self.shape(text, size).items() if key != "path"}


@lru_cache(maxsize=1)
def get_metrics():
    return Metrics()
