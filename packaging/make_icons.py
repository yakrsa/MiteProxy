#!/usr/bin/env python3
"""生成应用图标（v1.15）：1024px 母版 -> icon.ico / icon.icns / icon_256.png。

用法：packaging/make_icons.py（需 PySide6 + Pillow，offscreen 运行）

- 图案放大：盾牌占画布宽度约 60%（旧版约 40%），小尺寸下更易辨认
- ico 帧编码：<=128 用 BMP（Windows 经典 shell/任务栏只认 BMP 小帧，
  旧 ico 全 PNG 编码导致资源管理器显示白板），256 用 PNG
- icns 用 iconutil 从 iconset 生成（macOS 自带）
"""

import subprocess
import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent

# ---- 1. 画 1024 母版（PySide6 offscreen）---------------------------------

from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import (
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QColor,
    QImage,
)
from PySide6.QtWidgets import QApplication

CANVAS = 1024


def draw_icon() -> QImage:
    app = QApplication.instance() or QApplication([])
    img = QImage(CANVAS, CANVAS, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # 背景：蓝->紫 对角渐变圆角方块
    bg = QPainterPath()
    bg.addRoundedRect(0, 0, CANVAS, CANVAS, 232, 232)
    grad = QLinearGradient(0, 0, CANVAS, CANVAS)
    grad.setColorAt(0.0, QColor("#3D6DF5"))
    grad.setColorAt(1.0, QColor("#8A4BF0"))
    p.fillPath(bg, grad)

    # 盾牌（白色，居中，占宽 ~60%）
    L, R, T = 202.0, 822.0, 192.0          # 左右-top
    shield = QPainterPath()
    shield.moveTo(L, 232)
    shield.quadTo(L, T, L + 40, T)          # 左上圆角
    shield.lineTo(R - 40, T)                # 顶边
    shield.quadTo(R, T, R, 232)             # 右上圆角
    shield.lineTo(R, 470)                   # 右侧直边
    shield.cubicTo(R, 645, 726, 775, 549, 848)   # 右下弧线收拢
    shield.quadTo(512, 863, 475, 848)       # 底尖圆头
    shield.cubicTo(298, 775, L, 645, L, 470)     # 左下弧线
    shield.closeSubpath()
    p.fillPath(shield, QColor("#FFFFFF"))

    # 三支箭头：左右向上（紫），中间向下（蓝）
    def arrow(cx: float, top: float, bottom: float, up: bool,
              color: str, shaft_w: float = 58.0,
              head_w: float = 148.0, head_h: float = 118.0) -> None:
        path = QPainterPath()
        if up:
            shaft_top, shaft_bot = top + head_h * 0.6, bottom
            apex = top
            base = top + head_h
        else:
            shaft_top, shaft_bot = top, bottom - head_h * 0.6
            apex = bottom
            base = bottom - head_h
        # 杆（圆角矩形）
        path.addRoundedRect(cx - shaft_w / 2, shaft_top, shaft_w,
                            shaft_bot - shaft_top, 29, 29)
        # 头（三角）
        tri = QPainterPath()
        tri.moveTo(cx, apex)
        tri.lineTo(cx + head_w / 2, base)
        tri.lineTo(cx - head_w / 2, base)
        tri.closeSubpath()
        p.fillPath(path, QColor(color))
        p.fillPath(tri, QColor(color))

    arrow(376, 336, 700, up=True,  color="#8B5CF6")   # 左上（紫）
    arrow(648, 336, 700, up=True,  color="#8B5CF6")   # 右上（紫）
    arrow(512, 336, 730, up=False, color="#3B82F6")   # 中下（蓝）

    p.end()
    return img


def save_png(img: QImage, path: Path, size: int | None = None) -> None:
    out = img
    if size is not None and size != img.width():
        out = img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    out.save(buf, "PNG")
    path.write_bytes(bytes(buf.data()))


# ---- 2. 派生 ico / icns ---------------------------------------------------

def make_ico(master: Path) -> None:
    from PIL import Image

    img = Image.open(master)
    img.save(
        PACKAGING / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
               (64, 64), (128, 128), (256, 256)],
        # 全 BMP 编码（DIB）：Windows 只保证 256 帧 PNG 兼容，小尺寸帧
        # 必须 BMP；旧 ico 全 PNG 编码导致资源管理器/任务栏显示白板
        bitmap_format="bmp",
    )


def make_icns(master: Path) -> None:
    from PIL import Image

    iconset = PACKAGING / "MiteProxy.iconset"
    iconset.mkdir(exist_ok=True)
    img = Image.open(master)
    for name, size in [
        ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
    ]:
        img.resize((size, size), Image.LANCZOS).save(iconset / name)
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset),
         "-o", str(PACKAGING / "icon.icns")],
        check=True,
    )
    subprocess.run(["rm", "-rf", str(iconset)], check=True)


def main() -> None:
    img = draw_icon()
    master = PACKAGING / "icon_master.png"
    save_png(img, master)
    save_png(img, PACKAGING / "icon_256.png", 256)   # 运行时窗口图标（打进包）
    make_ico(master)
    make_icns(master)
    print("生成完成：icon_master.png / icon_256.png / icon.ico / icon.icns")


if __name__ == "__main__":
    sys.exit(main())
