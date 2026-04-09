#!/usr/bin/env python3
"""Gamma Control  ·  PyQt5 GUI"""

import sys, os, time, platform, configparser, threading

IS_WIN = platform.system() == 'Windows'

if IS_WIN:
    import ctypes

    class _RECT(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    class _MONITORINFOEX(ctypes.Structure):
        _fields_ = [
            ('cbSize',    ctypes.c_uint32),
            ('rcMonitor', _RECT),
            ('rcWork',    _RECT),
            ('dwFlags',   ctypes.c_uint32),
            ('szDevice',  ctypes.c_wchar * 32),
        ]

    _ENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t,
        ctypes.POINTER(_RECT), ctypes.c_long)

    class _GammaRamp(ctypes.Structure):
        _fields_ = [('red',   ctypes.c_uint16 * 256),
                    ('green', ctypes.c_uint16 * 256),
                    ('blue',  ctypes.c_uint16 * 256)]

    _gdi32  = ctypes.WinDLL('gdi32')
    _user32 = ctypes.windll.user32

try:
    import keyboard as _kb
    _HAS_KB = True
except Exception:
    _HAS_KB = False

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QTabWidget, QFrame, QScrollArea,
    QDoubleSpinBox, QSystemTrayIcon, QMenu, QAction, QMessageBox,
)
from PyQt5.QtCore  import Qt, QThread, pyqtSignal, QTimer, QRectF, QRect
from PyQt5.QtGui   import (QColor, QPalette, QIcon, QPixmap, QPainter,
                            QBrush, QPen, QLinearGradient)

_BASE = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
         else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CFG   = os.path.join(_BASE, 'config.ini')

# ─── Palette: deep dark + violet accent ──────────────────────────────────────
# Hierarchy (darkest → lightest):  surf_low < bg < surf < surf_high < surf_top
C = dict(
    bg        = '#100F18',   # page / scroll viewport background
    surf_low  = '#0A0912',   # header / footer bar (darkest)
    surf      = '#1E1B2C',   # card surface  — clearly lighter than bg
    surf_high = '#272442',   # input fields / hover
    surf_top  = '#312E52',   # active / selected state

    # Accent  — blue-violet
    primary   = '#7B68EE',   # main accent (medium slate blue)
    on_pri    = '#FFFFFF',
    pri_cont  = '#2E2878',   # button / container bg
    on_pri_c  = '#C4BAFF',

    # Tonal secondary
    sec_cont  = '#252258',
    on_sec_c  = '#BDB5F0',

    # Text
    on_surf   = '#ECEAF6',   # primary text
    on_surf_v = '#8480A0',   # secondary text (slightly brighter for readability)

    # Borders / dividers
    outline   = '#3A3860',   # standard border
    out_v     = '#1E1C30',   # subtle border / divider

    # Semantic
    success   = '#3DD68C',
    succ_dim  = '#1B4D38',
)


# =============================================================================
# Monitor / gamma helpers
# =============================================================================
def get_monitors():
    if not IS_WIN:
        return [{'device': r'\\.\DISPLAY1', 'index': 0, 'primary': True,
                 'rect': (0, 0, 1920, 1080), 'name': 'Display 1'}]
    mons = []
    def _cb(hMon, _hdc, _lprc, _data):
        mi = _MONITORINFOEX()
        mi.cbSize = ctypes.sizeof(_MONITORINFOEX)
        if _user32.GetMonitorInfoW(hMon, ctypes.byref(mi)):
            r = mi.rcMonitor
            mons.append({
                'device':  mi.szDevice,
                'index':   len(mons),
                'primary': bool(mi.dwFlags & 1),
                'rect':    (r.left, r.top, r.right, r.bottom),
                'name':    f'Display {len(mons)+1}',
            })
        return True
    _user32.EnumDisplayMonitors(None, None, _ENUMPROC(_cb), 0)
    if not mons:
        mons.append({'device': r'\\.\DISPLAY1', 'index': 0, 'primary': True,
                     'rect': (0, 0, 1920, 1080), 'name': 'Display 1'})
    return mons


def apply_gamma(device: str, gamma: float) -> bool:
    if not IS_WIN:
        print(f'[mock] gamma={gamma:.3f} on {device}')
        return True
    ramp = _GammaRamp()
    for i in range(256):
        v = min(int((i / 255.0) ** gamma * 65535), 65535)
        ramp.red[i] = ramp.green[i] = ramp.blue[i] = v
    hdc = _gdi32.CreateDCW(None, device, None, None)
    if not hdc:
        return False
    ok = bool(_gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp)))
    _gdi32.DeleteDC(hdc)
    return ok


# =============================================================================
# Background threads
# =============================================================================
class HotkeyThread(QThread):
    toggled = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._run   = False
        self._lock  = threading.Lock()
        self._g1    = 1.0
        self._g2    = 0.7
        self._dt    = 0.1
        self._dp    = 0.006
        self._key   = 'num 9'
        self._mons  = []
        self._state = 'g1'

    def configure(self, g1, g2, dt, dp, key, monitors):
        with self._lock:
            self._g1, self._g2, self._dt, self._dp = g1, g2, dt, dp
            self._key  = key
            self._mons = monitors[:]

    def stop(self): self._run = False

    def run(self):
        self._run = True
        while self._run:
            with self._lock:
                key, dp, dt = self._key, self._dp, self._dt
                g1, g2      = self._g1,  self._g2
                mons        = self._mons[:]
                state       = self._state
            if _HAS_KB:
                try:
                    if _kb.is_pressed(key):
                        ns = 'g2' if state == 'g1' else 'g1'
                        gv = g2   if ns    == 'g2' else g1
                        with self._lock:
                            self._state = ns
                        for m in mons:
                            apply_gamma(m['device'], gv)
                        self.toggled.emit(ns)
                        time.sleep(dt)
                except Exception:
                    pass
            time.sleep(dp)


class _CaptureThread(QThread):
    captured = pyqtSignal(str)
    failed   = pyqtSignal()

    def run(self):
        if not _HAS_KB:
            self.failed.emit(); return
        try:
            k = _kb.read_key(suppress=False)
            self.captured.emit(k)
        except Exception:
            self.failed.emit()


# =============================================================================
# Custom widgets
# =============================================================================

class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self._on  = checked
        self._pos = 1.0 if checked else 0.0
        self._tmr = QTimer(self, interval=16)
        self._tmr.timeout.connect(self._tick)
        self.setFixedSize(46, 28)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self): return self._on

    def setChecked(self, v):
        if self._on != v:
            self._on = v; self._tmr.start()

    def _tick(self):
        t = 1.0 if self._on else 0.0
        self._pos += (t - self._pos) * 0.3
        if abs(t - self._pos) < 0.02:
            self._pos = t; self._tmr.stop()
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on = not self._on
            self._tmr.start()
            self.toggled.emit(self._on)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        t = self._pos
        # Track
        if t > 0.5:
            grad = QLinearGradient(0, 0, 46, 0)
            grad.setColorAt(0, QColor('#5A4FD4'))
            grad.setColorAt(1, QColor(C['primary']))
            p.setBrush(QBrush(grad))
        else:
            p.setBrush(QBrush(QColor(C['surf_top'])))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 2, 46, 24), 12, 12)
        # Thumb
        thumb_x = 3 + t * 18
        p.setBrush(QBrush(QColor(C['on_pri'] if t > 0.5 else C['on_surf_v'])))
        p.drawEllipse(QRectF(thumb_x, 4, 20, 20))


class _GammaBar(QWidget):
    """Read-only visual bar showing gamma fill (0.30–1.00 range)."""
    def __init__(self, value=1.0, parent=None):
        super().__init__(parent)
        self._v = value
        self.setFixedHeight(6)

    def set_value(self, v):
        self._v = max(0.3, min(1.0, v)); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        # Track
        p.setBrush(QBrush(QColor(C['out_v']))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, 6, 3, 3)
        # Fill
        frac = (self._v - 0.3) / 0.7
        fw = max(6, int(w * frac))
        grad = QLinearGradient(0, 0, fw, 0)
        grad.setColorAt(0, QColor('#5A4FD4'))
        grad.setColorAt(1, QColor(C['primary']))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(0, 0, fw, 6, 3, 3)


class MonitorCard(QFrame):
    selection_changed = pyqtSignal(int, bool)

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self._info = info
        self._sel  = True
        self.setFixedSize(185, 115)
        self._build(); self._style(True)

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(14, 11, 14, 11); lo.setSpacing(5)

        # ── header row ──────────────────────────────────────────────────────
        row = QHBoxLayout(); row.setSpacing(7)

        # Index badge: circle with number
        badge = QLabel(str(self._info['index'] + 1))
        badge.setFixedSize(20, 20); badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background:{C['pri_cont']};color:{C['on_pri_c']};"
            f"border-radius:10px;font-size:10px;font-weight:800;")

        nm = QLabel(self._info['name'])
        nm.setStyleSheet(f"color:{C['on_surf']};font-size:13px;font-weight:600;")

        self._sw = ToggleSwitch(True)
        self._sw.toggled.connect(self._on_sw)

        row.addWidget(badge); row.addWidget(nm)
        row.addStretch(); row.addWidget(self._sw)

        # ── info rows ────────────────────────────────────────────────────────
        r  = self._info['rect']
        rl = QLabel(f"{r[2]-r[0]} × {r[3]-r[1]}")
        rl.setStyleSheet(f"color:{C['on_surf_v']};font-size:12px;")

        is_primary = self._info['primary']
        tag_t = "★  Primary" if is_primary else f"x {r[0]},  y {r[1]}"
        tag_c = C['on_pri_c'] if is_primary else C['out_v'].replace('#', '#')
        # For position labels use a slightly brighter muted color
        tag_c = C['on_pri_c'] if is_primary else '#4A4660'
        tl = QLabel(tag_t)
        tl.setStyleSheet(f"color:{tag_c};font-size:11px;font-weight:500;")

        lo.addLayout(row); lo.addWidget(rl); lo.addWidget(tl)

    def _style(self, sel):
        lbl_rule = f"MonitorCard QLabel{{background:{C['surf']};}}"
        if sel:
            self.setStyleSheet(
                f"MonitorCard{{background:{C['surf']};border-radius:12px;"
                f"border:1px solid {C['primary']};}}" + lbl_rule)
        else:
            self.setStyleSheet(
                f"MonitorCard{{background:{C['surf']};border-radius:12px;"
                f"border:1px solid {C['out_v']};}}" + lbl_rule)

    def _on_sw(self, checked):
        self._sel = checked; self._style(checked)
        self.selection_changed.emit(self._info['index'], checked)

    def is_selected(self): return self._sel


class _SLabel(QWidget):
    """Section header: accent bar + spaced-out label."""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(8)

        bar = QFrame()
        bar.setFixedSize(3, 14)
        bar.setStyleSheet(
            f"background:{C['primary']};border-radius:2px;")

        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{C['on_surf_v']};font-size:10px;"
            f"font-weight:700;letter-spacing:2px;")

        lo.addWidget(bar, 0, Qt.AlignVCenter)
        lo.addWidget(lbl, 0, Qt.AlignVCenter)
        lo.addStretch()


class _Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('Card')
        self.setStyleSheet(
            f"QFrame#Card{{background:{C['surf']};border-radius:12px;"
            f"border:1px solid {C['outline']};}}"
            f"QFrame#Card QWidget{{background:{C['surf']};}}"
            f"QFrame#Card QLabel{{background:{C['surf']};}}")
        self._lo = QVBoxLayout(self)
        self._lo.setContentsMargins(18, 16, 18, 16); self._lo.setSpacing(12)

    def add(self, widget=None, layout=None):
        if widget is not None: self._lo.addWidget(widget)
        if layout is not None: self._lo.addLayout(layout)


class _Slider(QWidget):
    """Two-row slider: label+value-badge on top, slider below."""
    value_changed = pyqtSignal(float)

    def __init__(self, label, val, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(7)

        # Top row: name + value badge
        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color:{C['on_surf_v']};font-size:12px;font-weight:600;")

        self._vl = QLabel(f"{val:.2f}")
        self._vl.setAlignment(Qt.AlignCenter)
        self._vl.setFixedSize(48, 22)
        self._vl.setStyleSheet(
            f"background:{C['pri_cont']};color:{C['on_pri_c']};"
            f"font-size:12px;font-weight:700;border-radius:6px;")

        top.addWidget(lbl); top.addStretch(); top.addWidget(self._vl)

        # Slider
        self._sl = QSlider(Qt.Horizontal)
        self._sl.setRange(30, 100)
        self._sl.setValue(int(val * 100))
        self._sl.valueChanged.connect(self._ch)

        lo.addLayout(top)
        lo.addWidget(self._sl)

    def _ch(self, v):
        fv = v / 100.0
        self._vl.setText(f"{fv:.2f}")
        self.value_changed.emit(fv)

    def value(self): return self._sl.value() / 100.0
    def set_value(self, v): self._sl.setValue(int(v * 100))


class _FilledBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent); self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
QPushButton{{background:{C['primary']};color:{C['on_pri']};border:none;
  border-radius:8px;padding:9px 22px;font-size:13px;font-weight:600;}}
QPushButton:hover{{background:#9180F5;}}
QPushButton:pressed{{background:#6255D4;}}
QPushButton:disabled{{background:{C['surf_high']};color:{C['on_surf_v']};}}""")


class _OutlineBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent); self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
QPushButton{{background:transparent;color:{C['on_pri_c']};
  border:1px solid {C['outline']};border-radius:8px;
  padding:9px 22px;font-size:13px;font-weight:600;}}
QPushButton:hover{{background:{C['surf_high']};border-color:{C['primary']};}}
QPushButton:pressed{{background:{C['surf_top']};}}""")


class _TonalBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent); self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
QPushButton{{background:{C['sec_cont']};color:{C['on_sec_c']};border:none;
  border-radius:8px;padding:9px 22px;font-size:13px;font-weight:600;}}
QPushButton:hover{{background:#302B60;}}
QPushButton:pressed{{background:#221C4A;}}""")


class HotkeyBtn(QPushButton):
    """Keyboard-key–styled button that captures the next keypress."""
    hotkey_set = pyqtSignal(str)

    def __init__(self, key, parent=None):
        super().__init__(key, parent)
        self._key    = key; self._active = False; self._thread = None
        self.setFixedHeight(44); self.setCursor(Qt.PointingHandCursor)
        self._style_idle(); self.clicked.connect(self._toggle)

    def _style_idle(self):
        self.setStyleSheet(f"""
QPushButton{{background:{C['surf_high']};color:{C['on_surf']};
  border:1px solid {C['outline']};border-bottom:3px solid {C['out_v'].replace('#', '#')};
  border-radius:8px;padding:6px 16px;
  font-size:14px;font-family:"Consolas","Courier New",monospace;font-weight:600;}}
QPushButton:hover{{background:{C['surf_top']};border-color:{C['primary']};
  border-bottom-color:{C['primary']};}}""".replace(
    'border-bottom:3px solid #201E2E', f'border-bottom:3px solid #141220'))

    def _style_cap(self):
        self.setStyleSheet(f"""
QPushButton{{background:{C['pri_cont']};color:{C['on_pri_c']};
  border:1px solid {C['primary']};border-bottom:3px solid #1E1860;
  border-radius:8px;padding:6px 16px;
  font-size:13px;font-style:italic;font-weight:500;}}""")

    def _toggle(self):
        if self._active: self._cancel(); return
        self._active = True; self.setText("  Press any key…"); self._style_cap()
        self._thread = _CaptureThread()
        self._thread.captured.connect(self._got)
        self._thread.failed.connect(self._cancel)
        self._thread.start()

    def _got(self, k):
        if not self._active: return
        self._key = k; self._active = False
        self.setText(k); self._style_idle(); self.hotkey_set.emit(k)

    def _cancel(self):
        self._active = False; self.setText(self._key); self._style_idle()

    def key(self): return self._key
    def set_key(self, k): self._key = k; self.setText(k)


# =============================================================================
# Tabs
# =============================================================================
class MainTab(QWidget):
    settings_changed = pyqtSignal()

    def __init__(self, cfg, monitors, parent=None):
        super().__init__(parent)
        self._cfg  = cfg; self._mons = monitors
        self._sel  = list(range(len(monitors)))
        self._build()

    def _build(self):
        outer  = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea{{background:{C['bg']};border:none;}}")
        scroll.viewport().setStyleSheet(f"background:{C['bg']};")
        body   = QWidget(); body.setStyleSheet(f"background:{C['bg']};")
        lo     = QVBoxLayout(body)
        lo.setContentsMargins(20, 20, 20, 20); lo.setSpacing(16)

        # ── Monitors ──────────────────────────────────────────────────────────
        lo.addWidget(_SLabel("MONITORS"))
        hs = QScrollArea(); hs.setFixedHeight(130)
        hs.setFrameShape(QFrame.NoFrame)
        hs.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hs.setStyleSheet(f"QScrollArea{{background:{C['bg']};border:none;}}")
        hs.viewport().setStyleSheet(f"background:{C['bg']};")
        mw  = QWidget(); mw.setStyleSheet(f"background:{C['bg']};")
        mlo = QHBoxLayout(mw)
        mlo.setContentsMargins(0, 0, 0, 0); mlo.setSpacing(10)
        self._cards = []
        for m in self._mons:
            card = MonitorCard(m)
            card.selection_changed.connect(self._on_sel)
            mlo.addWidget(card); self._cards.append(card)
        mlo.addStretch(); hs.setWidget(mw)
        lo.addWidget(hs)

        # ── Gamma values ─────────────────────────────────────────────────────
        lo.addWidget(_SLabel("GAMMA VALUES"))
        g1v = float(self._cfg['GammaSettings']['gamma1'])
        g2v = float(self._cfg['GammaSettings']['gamma2'])
        self._sl1 = _Slider("Normal",  g1v)
        self._sl2 = _Slider("Reduced", g2v)
        self._sl1.value_changed.connect(lambda v: self._save_g('gamma1', v))
        self._sl2.value_changed.connect(lambda v: self._save_g('gamma2', v))
        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background:{C['out_v']};max-height:1px;")
        gc = _Card()
        gc.add(self._sl1); gc.add(div); gc.add(self._sl2)
        lo.addWidget(gc)

        # ── Status ────────────────────────────────────────────────────────────
        lo.addWidget(_SLabel("STATUS"))
        sc = _Card()
        # Big gamma value display
        top_row = QHBoxLayout(); top_row.setSpacing(0)

        left_vl = QVBoxLayout(); left_vl.setSpacing(1)
        self._mode_lbl = QLabel("NORMAL")
        self._mode_lbl.setStyleSheet(
            f"color:{C['primary']};font-size:10px;"
            f"font-weight:700;letter-spacing:2px;")
        self._gval = QLabel(f"{g1v:.2f}")
        self._gval.setStyleSheet(
            f"color:{C['on_surf']};font-size:40px;font-weight:700;"
            f"letter-spacing:-1px;")
        left_vl.addWidget(self._mode_lbl)
        left_vl.addWidget(self._gval)

        right_vl = QVBoxLayout()
        right_vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._run_badge = QLabel("● RUNNING")
        self._run_badge.setAlignment(Qt.AlignRight)
        self._run_badge.setStyleSheet(
            f"color:{C['success']};font-size:12px;font-weight:600;")
        key_hint = self._cfg['GammaSettings'].get('toggle_key', 'num 9').strip()
        self._kbd_lbl = QLabel(f"hotkey:  {key_hint}")
        self._kbd_lbl.setAlignment(Qt.AlignRight)
        self._kbd_lbl.setStyleSheet(
            f"color:{C['out_v'].replace('#2','#4')};font-size:11px;"
            f"font-family:monospace;")
        right_vl.addStretch()
        right_vl.addWidget(self._run_badge)
        right_vl.addSpacing(4)
        right_vl.addWidget(self._kbd_lbl)

        top_row.addLayout(left_vl)
        top_row.addStretch()
        top_row.addLayout(right_vl)

        # Gamma bar below
        self._gbar = _GammaBar(g1v)

        sc.add(layout=top_row)
        sc.add(self._gbar)
        lo.addWidget(sc)
        lo.addStretch()
        scroll.setWidget(body); outer.addWidget(scroll)

    def _save_g(self, key, val):
        self._cfg['GammaSettings'][key] = str(val)
        self.settings_changed.emit()

    def _on_sel(self, idx, checked):
        if checked and idx not in self._sel: self._sel.append(idx)
        elif not checked and idx in self._sel: self._sel.remove(idx)
        self.settings_changed.emit()

    def selected_monitors(self):
        return [self._mons[i] for i in sorted(self._sel) if i < len(self._mons)]

    def update_status(self, state, running, gamma):
        self._mode_lbl.setText("NORMAL" if state == 'g1' else "REDUCED")
        self._gval.setText(f"{gamma:.2f}")
        self._gbar.set_value(gamma)
        if running:
            self._run_badge.setText("● RUNNING")
            self._run_badge.setStyleSheet(
                f"color:{C['success']};font-size:12px;font-weight:600;")
        else:
            self._run_badge.setText("○  STOPPED")
            self._run_badge.setStyleSheet(
                f"color:{C['on_surf_v']};font-size:12px;font-weight:600;")

    def refresh_hotkey_hint(self, key):
        self._kbd_lbl.setText(f"hotkey:  {key}")


class SettingsTab(QWidget):
    saved = pyqtSignal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg; self._build()

    def _spin_ss(self):
        return f"""
QDoubleSpinBox{{background:{C['surf_high']};color:{C['on_surf']};
  border:1px solid {C['outline']};border-radius:8px;
  padding:7px 12px;font-size:13px;min-width:110px;}}
QDoubleSpinBox:focus{{border:1px solid {C['primary']};}}
QDoubleSpinBox::up-button,QDoubleSpinBox::down-button{{
  background:{C['surf_top']};border:none;width:20px;border-radius:4px;}}"""

    def _build(self):
        outer  = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea{{background:{C['bg']};border:none;}}")
        scroll.viewport().setStyleSheet(f"background:{C['bg']};")
        body   = QWidget(); body.setStyleSheet(f"background:{C['bg']};")
        lo     = QVBoxLayout(body)
        lo.setContentsMargins(20, 20, 20, 20); lo.setSpacing(16)

        # ── Hotkey ────────────────────────────────────────────────────────────
        lo.addWidget(_SLabel("HOTKEY"))
        hkc = _Card()
        dsc = QLabel("Click the button, then press the desired key.")
        dsc.setStyleSheet(f"color:{C['on_surf_v']};font-size:12px;")
        dsc.setWordWrap(True)
        self._hkb = HotkeyBtn(self._cfg['GammaSettings']['toggle_key'].strip())
        hkc.add(dsc); hkc.add(self._hkb)
        lo.addWidget(hkc)

        # ── Timing ────────────────────────────────────────────────────────────
        lo.addWidget(_SLabel("TIMING"))
        tc = _Card()

        def lrow(txt, hint, spin):
            r = QHBoxLayout(); r.setSpacing(12)
            vl = QVBoxLayout(); vl.setSpacing(1)
            lb = QLabel(txt)
            lb.setStyleSheet(f"color:{C['on_surf']};font-size:13px;font-weight:600;")
            ht = QLabel(hint)
            ht.setStyleSheet(f"color:{C['on_surf_v']};font-size:11px;")
            vl.addWidget(lb); vl.addWidget(ht)
            r.addLayout(vl); r.addStretch(); r.addWidget(spin); return r

        self._dt = QDoubleSpinBox(); self._dt.setRange(0.01, 2.0)
        self._dt.setSingleStep(0.05); self._dt.setDecimals(3)
        self._dt.setValue(float(self._cfg['GammaSettings']['delay_trigger']))
        self._dt.setSuffix(" s"); self._dt.setStyleSheet(self._spin_ss())

        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background:{C['out_v']};max-height:1px;")

        self._dp = QDoubleSpinBox(); self._dp.setRange(0.001, 0.1)
        self._dp.setSingleStep(0.001); self._dp.setDecimals(4)
        self._dp.setValue(float(self._cfg['GammaSettings']['delay_polling']))
        self._dp.setSuffix(" s"); self._dp.setStyleSheet(self._spin_ss())

        tc.add(layout=lrow("Trigger delay", "Cooldown after toggle", self._dt))
        tc.add(div)
        tc.add(layout=lrow("Polling delay", "How often to check for keypress", self._dp))
        lo.addWidget(tc)

        # ── Buttons ───────────────────────────────────────────────────────────
        br = QHBoxLayout(); br.addStretch()
        rb = _OutlineBtn("Reset defaults"); rb.clicked.connect(self._reset)
        sb = _FilledBtn("Save settings");   sb.clicked.connect(self._save)
        br.addWidget(rb); br.addSpacing(8); br.addWidget(sb)
        lo.addLayout(br); lo.addStretch()
        scroll.setWidget(body); outer.addWidget(scroll)

    def _reset(self):
        self._hkb.set_key('num 9')
        self._dt.setValue(0.1); self._dp.setValue(0.006)

    def _save(self):
        g = self._cfg['GammaSettings']
        g['toggle_key']    = self._hkb.key()
        g['delay_trigger'] = str(self._dt.value())
        g['delay_polling'] = str(self._dp.value())
        try:
            with open(CFG, 'w') as f: self._cfg.write(f)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e)); return
        self.saved.emit()

    def get_key(self): return self._hkb.key()
    def get_dt(self):  return self._dt.value()
    def get_dp(self):  return self._dp.value()


# =============================================================================
# Main window
# =============================================================================
class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self._cfg    = self._load_cfg()
        self._mons   = get_monitors()
        self._state  = 'g1'
        self._thread = HotkeyThread()
        self._thread.toggled.connect(self._on_toggled)
        self.setWindowTitle("Gamma Control")
        self.setMinimumSize(480, 540); self.resize(520, 660)
        self._build_ui(); self._build_tray()
        self.setStyleSheet(SHEET)
        self._start()

    def _load_cfg(self):
        cfg = configparser.ConfigParser(); cfg.read(CFG)
        if not cfg.has_section('GammaSettings'):
            cfg['GammaSettings'] = {
                'gamma1': '1.0', 'gamma2': '0.7',
                'delay_trigger': '0.1', 'delay_polling': '0.006',
                'toggle_key': 'num 9',
            }
        return cfg

    def _build_ui(self):
        root = QWidget(); root.setObjectName('root')
        self.setCentralWidget(root)
        vl = QVBoxLayout(root); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget(); hdr.setFixedHeight(56)
        hdr.setStyleSheet(
            f"background:{C['surf_low']};"
            f"border-bottom:1px solid {C['out_v']};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(18, 0, 18, 0); hl.setSpacing(10)

        # Small painted icon
        ic_lbl = QLabel()
        ic_lbl.setFixedSize(28, 28)
        px = QPixmap(28, 28); px.fill(Qt.transparent)
        pp = QPainter(px); pp.setRenderHint(QPainter.Antialiasing)
        # Outer circle
        pp.setBrush(QBrush(QColor(C['pri_cont']))); pp.setPen(Qt.NoPen)
        pp.drawEllipse(0, 0, 28, 28)
        # Inner sun-like symbol: rays + center dot
        pp.setBrush(QBrush(QColor(C['primary']))); pp.setPen(Qt.NoPen)
        pp.drawEllipse(10, 10, 8, 8)
        pen = QPen(QColor(C['primary'])); pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap); pp.setPen(pen)
        import math
        for i in range(6):
            angle = math.radians(i * 60)
            x1 = 14 + math.cos(angle) * 6; y1 = 14 + math.sin(angle) * 6
            x2 = 14 + math.cos(angle) * 9; y2 = 14 + math.sin(angle) * 9
            pp.drawLine(int(x1), int(y1), int(x2), int(y2))
        pp.end()
        ic_lbl.setPixmap(px)

        ttl = QLabel("Gamma Control")
        ttl.setStyleSheet(f"color:{C['on_surf']};font-size:15px;font-weight:700;")
        ver = QLabel("v2.0")
        ver.setStyleSheet(
            f"color:{C['on_surf_v']};font-size:10px;font-weight:500;"
            f"background:{C['surf_high']};border-radius:4px;padding:1px 6px;")

        hl.addWidget(ic_lbl); hl.addWidget(ttl); hl.addWidget(ver)
        hl.addStretch()
        vl.addWidget(hdr)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self._tabs = QTabWidget(); self._tabs.setObjectName('tabs')
        self._tabs.setDocumentMode(True)
        self._mt = MainTab(self._cfg, self._mons)
        self._mt.settings_changed.connect(self._reconf)
        self._st = SettingsTab(self._cfg)
        self._st.saved.connect(self._on_settings_saved)
        self._tabs.addTab(self._mt, "  Control  ")
        self._tabs.addTab(self._st, "  Settings  ")
        vl.addWidget(self._tabs)

        # ── Footer ────────────────────────────────────────────────────────────
        ftr = QWidget(); ftr.setFixedHeight(56)
        ftr.setStyleSheet(
            f"background:{C['surf_low']};"
            f"border-top:1px solid {C['out_v']};")
        fl = QHBoxLayout(ftr); fl.setContentsMargins(18, 0, 18, 0); fl.setSpacing(8)
        self._tog_btn = _TonalBtn("Toggle Gamma")
        self._tog_btn.clicked.connect(self._manual_toggle)
        self._run_btn = _FilledBtn("Stop"); self._run_btn.setFixedWidth(100)
        self._run_btn.clicked.connect(self._toggle_run)
        fl.addStretch(); fl.addWidget(self._tog_btn); fl.addWidget(self._run_btn)
        vl.addWidget(ftr)

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        px = QPixmap(32, 32); px.fill(Qt.transparent)
        p = QPainter(px); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(C['primary'])); p.setPen(Qt.NoPen)
        p.drawEllipse(4, 4, 24, 24); p.end()
        self._tray = QSystemTrayIcon(QIcon(px), self)
        self._tray.setToolTip("Gamma Control")
        m = QMenu(); m.setStyleSheet(TRAY_SS)
        m.addAction("Show", self.show)
        m.addSeparator()
        m.addAction("Toggle Gamma", self._manual_toggle)
        m.addSeparator()
        m.addAction("Quit", QApplication.quit)
        self._tray.setContextMenu(m)
        self._tray.activated.connect(
            lambda r: (self.show(), self.activateWindow())
            if r == QSystemTrayIcon.DoubleClick else None)
        self._tray.show()

    def _reconf(self):
        g = self._cfg['GammaSettings']
        self._thread.configure(
            g1=float(g['gamma1']), g2=float(g['gamma2']),
            dt=float(g['delay_trigger']), dp=float(g['delay_polling']),
            key=g['toggle_key'].strip(),
            monitors=self._mt.selected_monitors())

    def _on_settings_saved(self):
        self._reconf()
        # Refresh hotkey hint in status card
        self._mt.refresh_hotkey_hint(
            self._cfg['GammaSettings'].get('toggle_key', 'num 9').strip())

    def _start(self):
        self._reconf()
        g1 = float(self._cfg['GammaSettings']['gamma1'])
        for m in self._mt.selected_monitors():
            apply_gamma(m['device'], g1)
        self._thread.start()
        self._run_btn.setText("Stop")
        self._mt.update_status('g1', True, g1)

    def _stop(self):
        self._thread.stop(); self._thread.wait(2000)
        self._run_btn.setText("Start")
        g = float(self._cfg['GammaSettings']['gamma1' if self._state == 'g1' else 'gamma2'])
        self._mt.update_status(self._state, False, g)

    def _toggle_run(self):
        if self._thread.isRunning(): self._stop()
        else: self._start()

    def _manual_toggle(self):
        ns  = 'g2' if self._state == 'g1' else 'g1'
        key = 'gamma2' if ns == 'g2' else 'gamma1'
        gv  = float(self._cfg['GammaSettings'][key])
        self._state = ns
        for m in self._mt.selected_monitors():
            apply_gamma(m['device'], gv)
        self._mt.update_status(ns, self._thread.isRunning(), gv)
        with self._thread._lock:
            self._thread._state = ns

    def _on_toggled(self, ns):
        self._state = ns
        key = 'gamma2' if ns == 'g2' else 'gamma1'
        gv  = float(self._cfg['GammaSettings'][key])
        self._mt.update_status(ns, True, gv)

    def closeEvent(self, e):
        if hasattr(self, '_tray') and self._tray.isVisible():
            self.hide(); e.ignore()
        else:
            self._stop(); e.accept()


# =============================================================================
# Stylesheets
# =============================================================================
SHEET = f"""
QMainWindow, QWidget#root {{
    background: {C['bg']};
}}
QWidget {{
    font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
}}

/* ── Tabs ──────────────────────────────────────────────────────────── */
QTabWidget#tabs::pane {{
    border: none;
    background: {C['bg']};
}}
QTabWidget#tabs QTabBar {{
    background: {C['surf_low']};
    border-bottom: 1px solid {C['out_v']};
}}
QTabWidget#tabs QTabBar::tab {{
    background: transparent;
    color: {C['on_surf_v']};
    padding: 12px 8px;
    font-size: 13px;
    font-weight: 500;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 90px;
}}
QTabWidget#tabs QTabBar::tab:selected {{
    color: {C['primary']};
    border-bottom: 2px solid {C['primary']};
    font-weight: 600;
}}
QTabWidget#tabs QTabBar::tab:hover:!selected {{
    color: {C['on_surf']};
    background: {C['surf_high']};
}}

/* ── Scroll areas — explicit bg so viewport doesn't bleed OS colour ── */
QScrollArea {{
    border: none;
    background: {C['bg']};
}}
QScrollArea > QWidget > QWidget {{
    background: {C['bg']};
}}
QScrollBar:vertical {{
    background: {C['bg']}; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['outline']}; border-radius: 3px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {C['on_surf_v']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {C['bg']}; }}
QScrollBar:horizontal {{
    background: {C['bg']}; height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {C['outline']}; border-radius: 3px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C['on_surf_v']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: {C['bg']}; }}

/* ── Sliders ────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 5px;
    background: {C['surf_top']};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 18px; height: 18px;
    border-radius: 9px;
    background: {C['primary']};
    margin: -7px 0;
    border: 2px solid {C['bg']};
}}
QSlider::handle:horizontal:hover {{
    background: #9180F5;
    width: 20px; height: 20px;
    border-radius: 10px;
    margin: -8px 0;
}}
QSlider::sub-page:horizontal {{
    background: {C['primary']};
    border-radius: 3px;
    opacity: 0.7;
}}

/* ── Tooltips ───────────────────────────────────────────────────────── */
QToolTip {{
    background: {C['surf_top']};
    color: {C['on_surf']};
    border: 1px solid {C['outline']};
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 12px;
}}

/* ── Message boxes ──────────────────────────────────────────────────── */
QMessageBox {{
    background: {C['surf']};
    color: {C['on_surf']};
}}
QMessageBox QPushButton {{
    background: {C['primary']};
    color: {C['on_pri']};
    border: none; border-radius: 7px;
    padding: 7px 18px; font-size: 13px; min-width: 70px;
}}
"""

TRAY_SS = f"""
QMenu {{
    background: {C['surf_high']};
    color: {C['on_surf']};
    border: 1px solid {C['outline']};
    border-radius: 10px;
    padding: 5px 0;
    font-size: 13px;
    font-family: "Segoe UI", sans-serif;
}}
QMenu::item {{ padding: 7px 18px; margin: 1px 4px; border-radius: 6px; }}
QMenu::item:selected {{
    background: {C['surf_top']}; color: {C['on_pri_c']};
}}
QMenu::separator {{
    height: 1px; background: {C['out_v']}; margin: 3px 10px;
}}
"""

# =============================================================================
# Entry point
# =============================================================================
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gamma Control")
    app.setQuitOnLastWindowClosed(False)

    pal = QPalette()
    for role, col in (
        (QPalette.Window,          C['bg']),
        (QPalette.WindowText,      C['on_surf']),
        (QPalette.Base,            C['surf']),
        (QPalette.AlternateBase,   C['surf_high']),
        (QPalette.Text,            C['on_surf']),
        (QPalette.Button,          C['pri_cont']),
        (QPalette.ButtonText,      C['on_pri_c']),
        (QPalette.Highlight,       C['primary']),
        (QPalette.HighlightedText, C['on_pri']),
    ):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)

    win = Window()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
