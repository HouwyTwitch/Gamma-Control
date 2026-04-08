#!/usr/bin/env python3
"""Gamma Control  ·  PyQt5 / Material You 3"""

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
from PyQt5.QtCore  import Qt, QThread, pyqtSignal, QTimer, QRectF
from PyQt5.QtGui   import QColor, QPalette, QIcon, QPixmap, QPainter, QBrush

_BASE = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
         else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CFG   = os.path.join(_BASE, 'config.ini')

# ─── Material You 3 dark palette ─────────────────────────────────────────────
C = dict(
    bg        = '#1C1B1F',
    surf_low  = '#1D1B20',
    surf      = '#211F26',
    surf_high = '#2B2930',
    surf_top  = '#36343B',
    primary   = '#D0BCFF',
    on_pri    = '#381E72',
    pri_cont  = '#4F378B',
    on_pri_c  = '#EADDFF',
    sec_cont  = '#4A4458',
    on_sec_c  = '#E8DEF8',
    on_surf   = '#E6E1E5',
    on_surf_v = '#CAC4D0',
    outline   = '#938F99',
    out_v     = '#49454F',
    success   = '#A8D5A2',
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
# Threads
# =============================================================================
class HotkeyThread(QThread):
    toggled = pyqtSignal(str)   # 'g1' | 'g2'

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

    def stop(self):
        self._run = False

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
            self.failed.emit()
            return
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
        self.setFixedSize(52, 32)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self): return self._on

    def setChecked(self, v):
        if self._on != v:
            self._on = v; self._tmr.start()

    def _tick(self):
        t = 1.0 if self._on else 0.0
        self._pos += (t - self._pos) * 0.25
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
        p.setBrush(QBrush(QColor(C['primary'] if t > 0.5 else C['out_v'])))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 4, 52, 24), 12, 12)
        p.setBrush(QBrush(QColor(C['on_pri'] if t > 0.5 else C['outline'])))
        p.drawEllipse(QRectF(4 + t * 20, 4, 24, 24))


class MonitorCard(QFrame):
    selection_changed = pyqtSignal(int, bool)

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self._info = info
        self._sel  = True
        self.setFixedSize(180, 120)
        self._build(); self._style(True)

    def _build(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(14, 12, 14, 12); lo.setSpacing(5)
        row = QHBoxLayout()
        nm  = QLabel(self._info['name'])
        nm.setStyleSheet(f"color:{C['on_surf']};font-size:14px;font-weight:600;")
        self._sw = ToggleSwitch(True)
        self._sw.toggled.connect(self._on_sw)
        row.addWidget(nm); row.addStretch(); row.addWidget(self._sw)
        r   = self._info['rect']
        rl  = QLabel(f"{r[2]-r[0]}×{r[3]-r[1]}")
        rl.setStyleSheet(f"color:{C['on_surf_v']};font-size:12px;")
        is_primary = self._info['primary']
        tag_t = "● Primary" if is_primary else f"({r[0]}, {r[1]})"
        tag_c = C['primary'] if is_primary else C['on_surf_v']
        tl = QLabel(tag_t); tl.setStyleSheet(f"color:{tag_c};font-size:11px;")
        lo.addLayout(row); lo.addWidget(rl); lo.addWidget(tl)

    def _style(self, sel):
        bdr = C['primary'] if sel else C['out_v']
        self.setStyleSheet(
            f"MonitorCard{{background:{C['surf_high']};border-radius:16px;"
            f"border:1.5px solid {bdr};}}")

    def _on_sw(self, checked):
        self._sel = checked; self._style(checked)
        self.selection_changed.emit(self._info['index'], checked)

    def is_selected(self): return self._sel


class _Slider(QWidget):
    value_changed = pyqtSignal(float)

    def __init__(self, label, val, parent=None):
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0); lo.setSpacing(14)
        lbl = QLabel(label); lbl.setFixedWidth(76)
        lbl.setStyleSheet(f"color:{C['on_surf_v']};font-size:13px;")
        self._sl = QSlider(Qt.Horizontal)
        self._sl.setRange(30, 100); self._sl.setValue(int(val * 100))
        self._sl.valueChanged.connect(self._ch)
        self._vl = QLabel(f"{val:.2f}"); self._vl.setFixedWidth(38)
        self._vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._vl.setStyleSheet(f"color:{C['primary']};font-size:14px;font-weight:700;")
        lo.addWidget(lbl); lo.addWidget(self._sl); lo.addWidget(self._vl)

    def _ch(self, v):
        fv = v / 100.0; self._vl.setText(f"{fv:.2f}"); self.value_changed.emit(fv)

    def value(self): return self._sl.value() / 100.0
    def set_value(self, v): self._sl.setValue(int(v * 100))


class _SLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color:{C['on_surf_v']};font-size:11px;font-weight:700;letter-spacing:1.5px;")


class _Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('Card')
        self.setStyleSheet(
            f"QFrame#Card{{background:{C['surf']};border-radius:16px;border:none;}}")
        self._lo = QVBoxLayout(self)
        self._lo.setContentsMargins(20, 20, 20, 20); self._lo.setSpacing(14)

    def add(self, widget=None, layout=None):
        if widget is not None: self._lo.addWidget(widget)
        if layout is not None: self._lo.addLayout(layout)


def _btn(cls, text):
    b = cls(text); b.setCursor(Qt.PointingHandCursor); return b

class _FilledBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent); self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
QPushButton{{background:{C['primary']};color:{C['on_pri']};border:none;
  border-radius:20px;padding:10px 24px;font-size:14px;font-weight:600;}}
QPushButton:hover{{background:#D8C6FF;}}
QPushButton:pressed{{background:#C4AEFF;}}
QPushButton:disabled{{background:{C['surf_high']};color:{C['outline']};}}""")

class _OutlineBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent); self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
QPushButton{{background:transparent;color:{C['primary']};border:1px solid {C['outline']};
  border-radius:20px;padding:10px 24px;font-size:14px;font-weight:600;}}
QPushButton:hover{{background:rgba(208,188,255,0.08);}}
QPushButton:pressed{{background:rgba(208,188,255,0.12);}}""")

class _TonalBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent); self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
QPushButton{{background:{C['sec_cont']};color:{C['on_sec_c']};border:none;
  border-radius:20px;padding:10px 24px;font-size:14px;font-weight:600;}}
QPushButton:hover{{background:#524965;}}
QPushButton:pressed{{background:#3E3751;}}""")


class HotkeyBtn(QPushButton):
    hotkey_set = pyqtSignal(str)

    def __init__(self, key, parent=None):
        super().__init__(key, parent)
        self._key    = key; self._active = False; self._thread = None
        self.setFixedHeight(48); self.setCursor(Qt.PointingHandCursor)
        self._style_idle(); self.clicked.connect(self._toggle)

    def _style_idle(self):
        self.setStyleSheet(f"""
QPushButton{{background:{C['surf_high']};color:{C['on_surf']};
  border:1px solid {C['out_v']};border-radius:12px;
  padding:8px 16px;font-size:14px;font-family:monospace;}}
QPushButton:hover{{background:{C['surf_top']};border:1px solid {C['outline']};}}""")

    def _style_cap(self):
        self.setStyleSheet(f"""
QPushButton{{background:{C['pri_cont']};color:{C['on_pri_c']};
  border:2px solid {C['primary']};border-radius:12px;
  padding:8px 16px;font-size:14px;font-style:italic;}}""")

    def _toggle(self):
        if self._active: self._cancel(); return
        self._active = True; self.setText("Press any key…"); self._style_cap()
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
        body   = QWidget(); body.setStyleSheet(f"background:{C['bg']};")
        lo     = QVBoxLayout(body)
        lo.setContentsMargins(24, 24, 24, 24); lo.setSpacing(18)

        # Monitors
        lo.addWidget(_SLabel("MONITORS"))
        hs = QScrollArea(); hs.setFixedHeight(138)
        hs.setFrameShape(QFrame.NoFrame)
        hs.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hs.setStyleSheet("background:transparent;")
        mw  = QWidget(); mw.setStyleSheet(f"background:{C['bg']};")
        mlo = QHBoxLayout(mw)
        mlo.setContentsMargins(0, 0, 0, 0); mlo.setSpacing(12)
        self._cards = []
        for m in self._mons:
            card = MonitorCard(m)
            card.selection_changed.connect(self._on_sel)
            mlo.addWidget(card); self._cards.append(card)
        mlo.addStretch(); hs.setWidget(mw)
        lo.addWidget(hs)

        # Gamma values
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

        # Status
        lo.addWidget(_SLabel("STATUS"))
        self._dot  = QLabel("●"); self._dot.setStyleSheet(f"color:{C['success']};font-size:20px;")
        self._stxt = QLabel("Running — Normal (1.00)")
        self._stxt.setStyleSheet(f"color:{C['on_surf']};font-size:14px;")
        sr = QHBoxLayout(); sr.setSpacing(10)
        sr.addWidget(self._dot); sr.addWidget(self._stxt); sr.addStretch()
        sc = _Card(); sc.add(layout=sr)
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
        if running:
            self._dot.setStyleSheet(f"color:{C['success']};font-size:20px;")
            lab = "Normal" if state == 'g1' else "Reduced"
            self._stxt.setText(f"Running — {lab} ({gamma:.2f})")
        else:
            self._dot.setStyleSheet(f"color:{C['outline']};font-size:20px;")
            self._stxt.setText("Stopped")


class SettingsTab(QWidget):
    saved = pyqtSignal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg; self._build()

    def _spin_ss(self):
        return f"""
QDoubleSpinBox{{background:{C['surf_high']};color:{C['on_surf']};
  border:1px solid {C['out_v']};border-radius:8px;
  padding:8px 12px;font-size:14px;min-width:110px;}}
QDoubleSpinBox:focus{{border:2px solid {C['primary']};}}
QDoubleSpinBox::up-button,QDoubleSpinBox::down-button{{
  background:{C['surf_top']};border:none;width:22px;border-radius:4px;}}"""

    def _build(self):
        outer  = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body   = QWidget(); body.setStyleSheet(f"background:{C['bg']};")
        lo     = QVBoxLayout(body)
        lo.setContentsMargins(24, 24, 24, 24); lo.setSpacing(18)

        # Hotkey
        lo.addWidget(_SLabel("HOTKEY"))
        hkc = _Card()
        dsc = QLabel("Click the button below, then press the desired key.")
        dsc.setStyleSheet(f"color:{C['on_surf_v']};font-size:13px;"); dsc.setWordWrap(True)
        self._hkb = HotkeyBtn(self._cfg['GammaSettings']['toggle_key'].strip())
        hkc.add(dsc); hkc.add(self._hkb)
        lo.addWidget(hkc)

        # Timing
        lo.addWidget(_SLabel("TIMING"))
        tc = _Card()

        def lrow(txt, spin):
            r = QHBoxLayout()
            lbl = QLabel(txt); lbl.setStyleSheet(f"color:{C['on_surf']};font-size:14px;")
            r.addWidget(lbl); r.addStretch(); r.addWidget(spin); return r

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

        tc.add(layout=lrow("Trigger delay", self._dt))
        tc.add(div)
        tc.add(layout=lrow("Polling delay", self._dp))
        lo.addWidget(tc)

        # Buttons
        br = QHBoxLayout(); br.addStretch()
        rb = _OutlineBtn("Reset defaults"); rb.clicked.connect(self._reset)
        sb = _FilledBtn("Save settings");   sb.clicked.connect(self._save)
        br.addWidget(rb); br.addSpacing(10); br.addWidget(sb)
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
        self.setMinimumSize(500, 560); self.resize(540, 680)
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

        # Header
        hdr = QWidget(); hdr.setFixedHeight(60)
        hdr.setStyleSheet(
            f"background:{C['surf_low']};border-bottom:1px solid {C['out_v']};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20, 0, 20, 0)
        ico = QLabel("◑"); ico.setStyleSheet(f"color:{C['primary']};font-size:22px;")
        ttl = QLabel("Gamma Control")
        ttl.setStyleSheet(f"color:{C['on_surf']};font-size:17px;font-weight:700;")
        hl.addWidget(ico); hl.addSpacing(10); hl.addWidget(ttl); hl.addStretch()
        vl.addWidget(hdr)

        # Tabs
        self._tabs = QTabWidget(); self._tabs.setObjectName('tabs')
        self._tabs.setDocumentMode(True)
        self._mt = MainTab(self._cfg, self._mons)
        self._mt.settings_changed.connect(self._reconf)
        self._st = SettingsTab(self._cfg)
        self._st.saved.connect(self._reconf)
        self._tabs.addTab(self._mt, "Control")
        self._tabs.addTab(self._st, "Settings")
        vl.addWidget(self._tabs)

        # Footer
        ftr = QWidget(); ftr.setFixedHeight(60)
        ftr.setStyleSheet(
            f"background:{C['surf_low']};border-top:1px solid {C['out_v']};")
        fl = QHBoxLayout(ftr); fl.setContentsMargins(20, 0, 20, 0); fl.setSpacing(10)
        self._tog_btn = _TonalBtn("Toggle Gamma")
        self._tog_btn.clicked.connect(self._manual_toggle)
        self._run_btn = _FilledBtn("Stop"); self._run_btn.setFixedWidth(110)
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
        self._mt.update_status(self._state, False, 0.0)

    def _toggle_run(self):
        if self._thread.isRunning(): self._stop()
        else: self._start()

    def _manual_toggle(self):
        ns = 'g2' if self._state == 'g1' else 'g1'
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
QTabWidget#tabs::pane {{
    border: none;
    background: {C['bg']};
}}
QTabWidget#tabs QTabBar {{
    background: {C['surf_low']};
}}
QTabWidget#tabs QTabBar::tab {{
    background: transparent;
    color: {C['on_surf_v']};
    padding: 14px 32px;
    font-size: 14px;
    font-weight: 500;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 100px;
}}
QTabWidget#tabs QTabBar::tab:selected {{
    color: {C['primary']};
    border-bottom: 2px solid {C['primary']};
}}
QTabWidget#tabs QTabBar::tab:hover:!selected {{
    background: rgba(208,188,255,0.06);
    color: {C['on_surf']};
}}
QScrollArea {{
    border: none; background: transparent;
}}
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['out_v']}; border-radius: 3px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C['outline']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent; height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {C['out_v']}; border-radius: 3px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C['outline']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QSlider::groove:horizontal {{
    height: 4px; background: {C['out_v']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 20px; height: 20px; border-radius: 10px;
    background: {C['primary']}; margin: -8px 0; border: none;
}}
QSlider::handle:horizontal:hover {{
    background: #D8C6FF;
}}
QSlider::sub-page:horizontal {{
    background: {C['primary']}; border-radius: 2px;
}}
QToolTip {{
    background: {C['surf_top']}; color: {C['on_surf']};
    border: 1px solid {C['out_v']}; border-radius: 8px;
    padding: 6px 10px; font-size: 12px;
}}
QMessageBox {{
    background: {C['surf']}; color: {C['on_surf']};
}}
QMessageBox QPushButton {{
    background: {C['primary']}; color: {C['on_pri']};
    border: none; border-radius: 16px;
    padding: 8px 20px; font-size: 13px; min-width: 80px;
}}
"""

TRAY_SS = f"""
QMenu {{
    background: {C['surf_high']}; color: {C['on_surf']};
    border: 1px solid {C['out_v']}; border-radius: 12px;
    padding: 6px 0; font-size: 13px;
    font-family: "Segoe UI", sans-serif;
}}
QMenu::item {{ padding: 8px 20px; margin: 2px 4px; border-radius: 8px; }}
QMenu::item:selected {{
    background: rgba(208,188,255,0.12); color: {C['primary']};
}}
QMenu::separator {{
    height: 1px; background: {C['out_v']}; margin: 4px 12px;
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
