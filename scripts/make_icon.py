"""Рисует иконку приложения (assets/icon.png и icon.ico). Запуск: python scripts/make_icon.py"""
import math
import os
import struct
import zlib

S, SS = 256, 2
OUT = os.path.join(os.path.dirname(__file__), "..", "pyfactor", "assets")


def seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def inside(x, y, r=58):
    return math.hypot(x - min(max(x, r), S - r), y - min(max(y, r), S - r)) <= r


raw = bytearray()
for y in range(S):
    raw.append(0)
    for x in range(S):
        a = [0, 0, 0, 0]
        for sy in range(SS):
            for sx in range(SS):
                px, py = x + (sx + .5) / SS, y + (sy + .5) / SS
                if not inside(px, py):
                    continue
                t = (px + py) / (2 * S)
                c = (124 + (47 - 124) * t, 92 + (183 - 92) * t, 255)
                if seg(px, py, 78, 88, 134, 128) <= 11 or seg(px, py, 134, 128, 78, 168) <= 11 or (146 <= px <= 196 and 158 <= py <= 174):
                    c = (255, 255, 255)
                a[0] += c[0]; a[1] += c[1]; a[2] += c[2]; a[3] += 1
        n = SS * SS
        raw += bytes([int(a[0] / a[3]), int(a[1] / a[3]), int(a[2] / a[3]), 255 * a[3] // n]) if a[3] else bytes(4)


def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)


png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0)) + \
    chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "icon.png"), "wb").write(png)
open(os.path.join(OUT, "icon.ico"), "wb").write(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png)
print("иконка готова")
