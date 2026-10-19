"""Small, per-user appearance settings and cached translucent crystal palettes."""
from runtime_paths import app_dir
import re
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QSettings, QStandardPaths
from PySide6.QtGui import QColor

PRESETS = {
    'Sapphire': '#2873eb', 'Amethyst': '#9654dc', 'Rose Quartz': '#e79ab7',
    'Emerald': '#209a66', 'Ruby': '#c73558', 'Amber': '#e69b26',
    'Arctic': '#8acdda', 'Midnight': '#39466d',
}


def valid_hex(value):
    return isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) is not None


class CrystalPalette:
    def __init__(self, color=None):
        self.base = QColor(color or PRESETS['Sapphire'])
        self.original = color is None or self.base.name() == PRESETS['Sapphire']
        self.cache = {}

    def color(self, r, g, b, a=255):
        key = (r, g, b, a)
        if key not in self.cache:
            source = QColor(r, g, b, a)
            if self.original:
                result = source
            else:
                reference = QColor(PRESETS['Sapphire'])
                hue = (max(0, self.base.hueF()) + (source.hueF() - reference.hueF()) * .45) % 1
                saturation = min(.95, self.base.saturationF() * source.saturationF() / reference.saturationF())
                value = min(1, source.valueF() * (.3 + .7 * self.base.valueF()) / reference.valueF())
                # Keep white faces legible even for a white custom crystal.
                # The specular highlight and luminous rim keep their brightness.
                if (r, g, b) == (40, 115, 235):
                    value = min(value, .84)
                result = QColor.fromHsvF(hue, saturation, value, a / 255)
            self.cache[key] = result
        return self.cache[key]


class Appearance(QObject):
    changed = Signal()

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        if settings is None:
            path = app_dir('config') / 'appearance.ini'
            settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.settings = settings
        self.settings.setFallbacksEnabled(False)
        preset = settings.value('crystal/preset', 'Sapphire')
        custom = settings.value('crystal/custom', PRESETS['Sapphire'])
        self.preset = preset if isinstance(preset, str) and (preset in PRESETS or preset == 'Custom') else 'Sapphire'
        self.custom = custom.lower() if valid_hex(custom) else PRESETS['Sapphire']
        if self.preset == 'Custom' and not valid_hex(custom):
            self.preset = 'Sapphire'
        enabled = settings.value('idle/enabled', True)
        self.idle_enabled = str(enabled).lower() not in ('false', '0')
        self._update_palette()

    def _update_palette(self):
        self.color = self.custom if self.preset == 'Custom' else PRESETS[self.preset]
        self.palette = CrystalPalette(None if self.preset == 'Sapphire' else self.color)

    def select(self, preset, custom=None, persist=True):
        if preset not in PRESETS and preset != 'Custom':
            raise ValueError('Unknown orb preset')
        if custom is not None:
            if not valid_hex(custom):
                raise ValueError('Expected an RGB hex color')
            self.custom = custom.lower()
        self.preset = preset
        self._update_palette()
        if persist:
            self.save()
        self.changed.emit()

    def set_idle_enabled(self, enabled):
        self.idle_enabled = bool(enabled)
        self.save()
        self.changed.emit()

    def save(self):
        self.settings.setValue('crystal/preset', self.preset)
        self.settings.setValue('crystal/custom', self.custom)
        self.settings.setValue('idle/enabled', self.idle_enabled)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            # Color still applies for this session; never silently claim it saved.
            import sys
            print('Hya: could not save appearance to ' + self.settings.fileName(), file=sys.stderr)
