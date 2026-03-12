#!/usr/bin/env python3
"""
给 data.json 里每个条目的图片补充真实宽高（size 字段）。

格式：在 arr 中新增 "size": ["3024x4032", "4032x3024", ...] 与 link 一一对应。
已有 size 字段的条目会跳过（幂等）。

使用：python3 backfill_sizes.py
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from PIL import Image, ImageOps

BLOG_ROOT  = Path('/Users/huanghuizhou/IdeaProjects/bolgSource')
PHOTOS_DIR = BLOG_ROOT / 'source/assets/photos'
DATA_JSON  = BLOG_ROOT / 'source/photos/data.json'

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.gif'}


def get_size_via_pillow(path: Path) -> Optional[tuple[int, int]]:
    """使用 Pillow 读取尺寸，自动修正 EXIF 旋转方向。"""
    try:
        img = ImageOps.exif_transpose(Image.open(path))
        return img.size  # (w, h)
    except Exception:
        return None


def get_size_via_sips(path: Path) -> Optional[tuple[int, int]]:
    """sips 方式获取尺寸（HEIC 或 Pillow 打不开时使用）。"""
    try:
        result = subprocess.run(
            ['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(path)],
            capture_output=True, text=True, timeout=10
        )
        w = h = None
        for line in result.stdout.splitlines():
            if 'pixelWidth' in line:
                w = int(line.split(':')[1].strip())
            elif 'pixelHeight' in line:
                h = int(line.split(':')[1].strip())
        if w and h:
            return (w, h)
    except Exception:
        pass
    return None


def resolve_photo_path(filename: str) -> Optional[Path]:
    """在 photos 目录中查找图片文件（兼容 .jpg/.jpeg 大小写混用）。"""
    stem = Path(filename).stem
    for ext in ('.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'):
        candidate = PHOTOS_DIR / (stem + ext)
        if candidate.exists():
            return candidate
    # 直接用原始文件名
    direct = PHOTOS_DIR / filename
    if direct.exists():
        return direct
    return None


def get_image_size(filename: str) -> str:
    """返回 'WxH' 字符串，找不到文件时返回 '0x0'。"""
    path = resolve_photo_path(filename)
    if path is None:
        print(f'    [未找到] {filename}')
        return '0x0'

    size = get_size_via_pillow(path) or get_size_via_sips(path)
    if size:
        return f'{size[0]}x{size[1]}'

    print(f'    [读取失败] {filename}')
    return '0x0'


def main() -> None:
    with open(DATA_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_entries = len(data['list'])
    updated = 0
    skipped = 0

    for entry in data['list']:
        arr = entry['arr']
        links = arr.get('link', [])

        # 已有完整 size 且数量匹配 → 跳过
        existing_sizes = arr.get('size', [])
        if existing_sizes and len(existing_sizes) == len(links):
            skipped += 1
            continue

        year, month = arr['year'], arr['month']
        print(f'处理 {year}-{month:02d}（{len(links)} 张）')

        sizes = []
        for filename in links:
            size_str = get_image_size(filename)
            print(f'    {filename} → {size_str}')
            sizes.append(size_str)

        arr['size'] = sizes
        updated += 1

    with open(DATA_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    print(f'\n完成：更新 {updated} 个分组，跳过 {skipped} 个（已有尺寸）')


if __name__ == '__main__':
    main()
