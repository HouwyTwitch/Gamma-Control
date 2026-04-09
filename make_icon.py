"""
Run once before building with PyInstaller to generate assets/icon.ico.

    python make_icon.py

Produces a multi-resolution ICO (16, 32, 48, 256 px) using the same
sun symbol drawn in the app GUI. No Pillow required — PNG bytes are
packed directly into the ICO container format.
"""
import sys, os, math, struct
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter, QColor, QBrush, QPen
from PyQt5.QtCore import Qt, QRectF, QBuffer, QIODevice

PRI_CONT = '#2E2878'
PRIMARY  = '#7B68EE'


def _draw(size: int) -> QPixmap:
    px = QPixmap(size, size); px.fill(Qt.transparent)
    p = QPainter(px); p.setRenderHint(QPainter.Antialiasing)
    s = size; c = s / 2
    p.setBrush(QBrush(QColor(PRI_CONT))); p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, s, s)
    dot = s * 0.14
    p.setBrush(QBrush(QColor(PRIMARY)))
    p.drawEllipse(QRectF(c - dot, c - dot, dot * 2, dot * 2))
    pen = QPen(QColor(PRIMARY)); pen.setWidth(max(1, round(s / 13)))
    pen.setCapStyle(Qt.RoundCap); p.setPen(pen); p.setBrush(Qt.NoBrush)
    for i in range(6):
        a = math.radians(i * 60)
        x1 = c + math.cos(a) * s * 0.22; y1 = c + math.sin(a) * s * 0.22
        x2 = c + math.cos(a) * s * 0.33; y2 = c + math.sin(a) * s * 0.33
        p.drawLine(int(x1), int(y1), int(x2), int(y2))
    p.end()
    return px


def _to_png(px: QPixmap) -> bytes:
    buf = QBuffer(); buf.open(QIODevice.WriteOnly)
    px.save(buf, 'PNG'); buf.close()
    return bytes(buf.data())


def _write_ico(sizes: list, path: str):
    """Pack PNG-encoded images into a multi-resolution .ico file."""
    images = []
    for sz in sizes:
        images.append((sz, _to_png(_draw(sz))))

    n = len(images)
    # ICO header: reserved(2) + type=1(2) + count(2)
    header = struct.pack('<HHH', 0, 1, n)
    offset = 6 + 16 * n          # data starts after header + all dir entries
    dir_entries = b''
    for sz, data in images:
        # width/height: 0 encodes 256 in the ICO spec
        w = h = 0 if sz == 256 else sz
        dir_entries += struct.pack('<BBBBHHII',
                                   w, h,        # width, height
                                   0, 0,         # color count, reserved
                                   1, 32,        # planes, bit depth
                                   len(data),    # size of image data
                                   offset)       # offset to image data
        offset += len(data)

    with open(path, 'wb') as f:
        f.write(header + dir_entries)
        for _, data in images:
            f.write(data)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    os.makedirs('assets', exist_ok=True)
    out = 'assets/icon.ico'
    _write_ico([16, 32, 48, 256], out)
    print(f'Saved {out}  ({os.path.getsize(out):,} bytes)')
