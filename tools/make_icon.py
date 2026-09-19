# -*- coding: utf-8 -*-
"""从 AI 生成的方形图里裁出干净的应用图标。

用法：
    python tools/make_icon.py <源图> [输出目录]

做三件事：
1. 找绿色圆角方块的 bbox（用饱和度判据，能自动排掉灰色的 AI 水印与投影）；
2. 以方块中心裁一个正方形 —— 右下角的生成水印在方块之外，因此被整块裁掉；
3. 把方块以外的背景（含投影）抠成透明，输出多尺寸 .ico + 512/256 png。

不需要 GPU、不依赖 Qt，只要 Pillow。
"""
import os
import sys

from PIL import Image

# 饱和度（max-min 通道差）分界：低于此值视为"灰/白背景"，方块本身远高于它
BG_SAT = 22


def find_tile_bbox(im):
    """返回绿色方块的 (left, top, right, bottom)（闭区间）。"""
    px = im.load()
    W, H = im.size
    x0, y0, x1, y1 = W, H, -1, -1
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if (max(r, g, b) - min(r, g, b)) > BG_SAT:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if x1 < 0:
        raise SystemExit("没找到彩色方块，源图可能不对")
    return x0, y0, x1, y1


def outer_background_mask(im, sat_thr=BG_SAT):
    """从四边泛洪，标记与画面边缘连通的低饱和区域（背景 + 投影）。

    方块内部的浅色高光即使低饱和也抠不到，因为四周被饱和的方块本体挡住。
    """
    px = im.load()
    W, H = im.size
    bg = bytearray(W * H)          # 1 = 背景
    stack = []

    def low_sat(x, y):
        r, g, b = px[x, y]
        return (max(r, g, b) - min(r, g, b)) <= sat_thr

    for x in range(W):
        for y in (0, H - 1):
            if not bg[y * W + x] and low_sat(x, y):
                bg[y * W + x] = 1
                stack.append((x, y))
    for y in range(H):
        for x in (0, W - 1):
            if not bg[y * W + x] and low_sat(x, y):
                bg[y * W + x] = 1
                stack.append((x, y))

    while stack:
        x, y = stack.pop()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < W and 0 <= ny < H and not bg[ny * W + nx] and low_sat(nx, ny):
                bg[ny * W + nx] = 1
                stack.append((nx, ny))
    return bg


def build(src, outdir, bg_mode="transparent"):
    im = Image.open(src).convert("RGB")
    W, H = im.size
    print("源图 %dx%d" % (W, H))

    x0, y0, x1, y1 = find_tile_bbox(im)
    tw, th = x1 - x0 + 1, y1 - y0 + 1
    print("方块 bbox (%d,%d)-(%d,%d)  %dx%d" % (x0, y0, x1, y1, tw, th))

    # 以方块中心裁一个正方形（不拉伸，方正不留形变）
    side = max(tw, th)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    half = side // 2
    box = (cx - half, cy - half, cx - half + side, cy - half + side)
    # 贴边裁：越界时整体平移回画面内
    bx0, by0, bx1, by1 = box
    dx = min(0, bx0) + max(0, bx1 - W)
    dy = min(0, by0) + max(0, by1 - H)
    box = (bx0 - dx, by0 - dy, bx1 - dx, by1 - dy)
    print("裁剪框 %s  -> %dx%d" % (str(box), box[2] - box[0], box[3] - box[1]))

    tile = im.crop(box)
    bgmask = outer_background_mask(tile)

    if bg_mode == "transparent":
        rgba = tile.convert("RGBA")
        ap = rgba.load()
        s = len(bgmask)
        for i in range(s):
            if bgmask[i]:
                x, y = i % rgba.width, i // rgba.width
                ap[x, y] = (255, 255, 255, 0)
        out = rgba
    else:                                    # white：水印区与投影一律填白
        out = tile.copy()
        wp = out.load()
        tp = tile.load()
        for i in range(len(bgmask)):
            if bgmask[i]:
                x, y = i % out.width, i // out.width
                wp[x, y] = (255, 255, 255)
        _ = tp

    os.makedirs(outdir, exist_ok=True)
    master = out.resize((1024, 1024), Image.LANCZOS)
    master.save(os.path.join(outdir, "icon.png"))

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    ico_path = os.path.join(outdir, "icon.ico")
    master.save(ico_path, format="ICO", sizes=sizes)
    print("写出 %s" % ico_path)
    print("写出 %s" % os.path.join(outdir, "icon.png"))
    return master


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "."
    build(src, outdir)
