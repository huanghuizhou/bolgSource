#!/usr/bin/env python3
"""
相册照片批量导入脚本

功能：
  1. 扫描源目录照片，读取 EXIF/sips 拍摄日期（无则回退 mtime）
  2. HEIC 自动用 sips 转成 JPEG
  3. 按 YYYY-MM-DD_原文件名.jpg 规范命名，复制到 source/assets/photos/
  4. 生成 360x360 正方形缩略图到 source/assets/min_photos/
  5. 按日期分组更新 source/photos/data.json（新条目插到已有条目前面）

使用：
  python3 add_photos.py [--dry-run]
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import subprocess
import tempfile
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS

# ── 路径配置 ─────────────────────────────────────────────────────────────────
SRC_DIR    = Path('/Users/huanghuizhou/摄影/精选')
BLOG_ROOT  = Path('/Users/huanghuizhou/IdeaProjects/bolgSource')
PHOTOS_DIR = BLOG_ROOT / 'source/assets/photos'
THUMBS_DIR = BLOG_ROOT / 'source/assets/min_photos'
DATA_JSON  = BLOG_ROOT / 'source/photos/data.json'

THUMB_SIZE     = (360, 360)
SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.heic'}

# ── 日期读取 ──────────────────────────────────────────────────────────────────

def read_exif_date(path: Path) -> Optional[datetime]:
    """从 JPG/PNG 的 EXIF 中读取拍摄时间。"""
    try:
        img = Image.open(path)
        exif_raw = img._getexif()
        if not exif_raw:
            return None
        for tag_id, val in exif_raw.items():
            tag = TAGS.get(tag_id)
            if tag in ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime'):
                return datetime.strptime(val, '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    return None


def read_sips_date(path: Path) -> Optional[datetime]:
    """通过 macOS sips 读取文件的 creation 时间（HEIC/通用备用）。"""
    try:
        result = subprocess.run(
            ['sips', '-g', 'creation', str(path)],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if 'creation' in line:
                date_str = line.split(':', 1)[1].strip()
                return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    return None


def get_photo_date(path: Path) -> tuple[datetime, str]:
    """
    依次尝试 EXIF → sips → mtime，返回 (datetime, 来源标注)。
    """
    dt = read_exif_date(path)
    if dt:
        return dt, 'exif'

    dt = read_sips_date(path)
    if dt:
        return dt, 'sips'

    return datetime.fromtimestamp(path.stat().st_mtime), 'mtime'

# ── HEIC 转换 ─────────────────────────────────────────────────────────────────

def heic_to_jpeg(src: Path, dst: Path) -> bool:
    """使用 sips 将 HEIC 转换为 JPEG，成功返回 True。"""
    try:
        result = subprocess.run(
            ['sips', '-s', 'format', 'jpeg', str(src), '--out', str(dst)],
            capture_output=True, timeout=30
        )
        return result.returncode == 0 and dst.exists()
    except Exception:
        return False

# ── 缩略图生成 ────────────────────────────────────────────────────────────────

def make_thumbnail(src: Path, dst: Path, size: tuple[int, int] = THUMB_SIZE) -> bool:
    """
    生成正方形缩略图：先按 EXIF 方向自动旋转，中心裁剪为正方形，
    再缩放到目标尺寸，以 JPEG 格式保存。
    """
    try:
        img = Image.open(src)
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')

        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top  = (h - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))
        img = img.resize(size, Image.LANCZOS)
        img.save(dst, 'JPEG', quality=85)
        return True
    except Exception as e:
        print(f'    [缩略图失败] {e}')
        return False

# ── data.json 操作 ────────────────────────────────────────────────────────────

def load_data_json() -> dict:
    with open(DATA_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_data_json(data: dict) -> None:
    with open(DATA_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def date_sort_key(entry: dict) -> tuple[int, int]:
    """按 (year desc, month desc) 排序的 key。"""
    arr = entry['arr']
    return (-arr['year'], -arr['month'])


def get_image_size(path: Path) -> str:
    """读取图片真实尺寸（自动修正 EXIF 旋转），返回 'WxH' 字符串，失败返回 '0x0'。"""
    try:
        img = ImageOps.exif_transpose(Image.open(path))
        return f'{img.width}x{img.height}'
    except Exception:
        return '0x0'


def build_new_entries(
    photo_groups: dict[tuple[int, int], list[str]]
) -> list[dict]:
    """
    将 {(year, month): [filename, ...]} 转换为 data.json 格式的条目列表。
    每个 (year, month) 分组生成一条 entry，同时记录真实图片尺寸。
    """
    entries = []
    for (year, month), filenames in sorted(photo_groups.items(), reverse=True):
        texts = [Path(fn).stem.split('_', 1)[-1] if '_' in fn else Path(fn).stem
                 for fn in filenames]
        sizes = [get_image_size(PHOTOS_DIR / fn) for fn in filenames]
        entries.append({
            'date': f'{year}-{month}',
            'arr': {
                'year':  year,
                'month': month,
                'link':  filenames,
                'text':  texts,
                'type':  ['image'] * len(filenames),
                'size':  sizes,
            }
        })
    return entries


def merge_entries(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """
    将新条目追加到已有列表中。

    原则：
    - 所有已有条目保持原样，不做任何合并或修改（保留同月多条目结构）。
    - 已存在于任意已有条目中的文件名 → 跳过（幂等）。
    - 新条目中的文件名不与任何已有条目重叠 → 作为新条目追加。
    - 最终按日期降序排列。
    """
    # 收集所有已存在的文件名（跨所有条目）
    all_existing_links: set[str] = set()
    for entry in existing:
        all_existing_links.update(entry['arr'].get('link', []))

    result = list(existing)

    for new_entry in new_entries:
        fresh_links = [fn for fn in new_entry['arr']['link']
                       if fn not in all_existing_links]
        if not fresh_links:
            continue

        # 只保留未重叠的文件
        link_set = set(new_entry['arr']['link'])
        kept_indices = [i for i, fn in enumerate(new_entry['arr']['link'])
                        if fn in set(fresh_links)]

        filtered = {
            'date': new_entry['date'],
            'arr': {
                'year':  new_entry['arr']['year'],
                'month': new_entry['arr']['month'],
                'link':  [new_entry['arr']['link'][i] for i in kept_indices],
                'text':  [new_entry['arr']['text'][i] for i in kept_indices],
                'type':  [new_entry['arr']['type'][i] for i in kept_indices],
                'size':  [new_entry['arr']['size'][i] for i in kept_indices],
            }
        }
        result.append(filtered)
        all_existing_links.update(filtered['arr']['link'])

    result.sort(key=date_sort_key)
    return result

# ── 主流程 ────────────────────────────────────────────────────────────────────

def process(dry_run: bool = False) -> None:
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    all_files = [
        f for f in SRC_DIR.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTS and f.is_file()
    ]
    all_files.sort()

    print(f'发现 {len(all_files)} 张照片，开始处理…\n')

    photo_groups: dict[tuple[int, int], list[str]] = defaultdict(list)
    ok_count  = 0
    skip_count = 0
    fail_count = 0

    for src_path in all_files:
        stem = src_path.stem
        ext  = src_path.suffix.lower()
        is_heic = ext == '.heic'

        dt, date_src = get_photo_date(src_path)
        out_name  = f"{dt.strftime('%Y-%m-%d')}_{stem}.jpg"
        photo_dst = PHOTOS_DIR / out_name
        thumb_dst = THUMBS_DIR / out_name

        if photo_dst.exists() and thumb_dst.exists():
            print(f'  [跳过] {src_path.name}  →  {out_name}  (已存在)')
            photo_groups[(dt.year, dt.month)].append(out_name)
            skip_count += 1
            continue

        print(f'  {src_path.name}')
        print(f'    日期: {dt.strftime("%Y-%m-%d")} [{date_src}]')
        print(f'    输出: {out_name}')

        if dry_run:
            photo_groups[(dt.year, dt.month)].append(out_name)
            ok_count += 1
            continue

        # HEIC → 先转成临时 JPEG，再用 Pillow 生成缩略图
        if is_heic:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = Path(tmp.name)
            if not heic_to_jpeg(src_path, tmp_path):
                print(f'    [错误] HEIC 转换失败，跳过')
                fail_count += 1
                continue
            jpeg_src = tmp_path
        else:
            jpeg_src = src_path

        # 复制原图（HEIC 使用转换后的 JPEG）
        try:
            shutil.copy2(jpeg_src, photo_dst)
        except Exception as e:
            print(f'    [错误] 复制原图失败: {e}')
            if is_heic:
                tmp_path.unlink(missing_ok=True)
            fail_count += 1
            continue

        # 生成缩略图
        thumb_ok = make_thumbnail(jpeg_src, thumb_dst)
        if not thumb_ok:
            fail_count += 1

        if is_heic:
            tmp_path.unlink(missing_ok=True)

        photo_groups[(dt.year, dt.month)].append(out_name)
        ok_count += 1

    # 更新 data.json
    print(f'\n正在更新 data.json …')
    data = load_data_json()
    new_entries = build_new_entries(photo_groups)
    data['list'] = merge_entries(data['list'], new_entries)

    if not dry_run:
        save_data_json(data)
        print(f'data.json 已写入（共 {len(data["list"])} 条分组）')
    else:
        print(f'[dry-run] data.json 不写入（将新增 {len(new_entries)} 个分组）')

    print(f'\n完成：处理 {ok_count} 张，跳过 {skip_count} 张，失败 {fail_count} 张')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='批量导入照片到 Hexo 相册')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不写入任何文件')
    args = parser.parse_args()

    process(dry_run=args.dry_run)
