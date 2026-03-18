#!/usr/bin/env python3
"""Extract GD level data from .gmd file into JSON for the web player."""
import base64, gzip, json, xml.etree.ElementTree as ET, sys

def parse_gmd(path):
    tree = ET.parse(path)
    root = tree.getroot()
    d = root.find('dict')
    data = {}
    children = list(d)
    i = 0
    while i < len(children):
        if children[i].tag == 'k':
            key = children[i].text
            val = children[i + 1]
            data[key] = val.text if val.text else ''
            i += 2
        else:
            i += 1
    return data

def decode_level_string(level_str):
    decoded = level_str.replace('-', '+').replace('_', '/')
    if len(decoded) % 4:
        decoded += '=' * (4 - len(decoded) % 4)
    raw = base64.b64decode(decoded)
    return gzip.decompress(raw).decode('utf-8', errors='replace')

def parse_color_string(kS38):
    """Parse the color channel definitions from header."""
    colors = {}
    if not kS38:
        return colors
    for channel_str in kS38.split('|'):
        if not channel_str.strip():
            continue
        props = channel_str.split('_')
        ch = {}
        for j in range(0, len(props) - 1, 2):
            ch[props[j]] = props[j + 1]
        channel_id = int(ch.get('6', '0'))
        colors[channel_id] = {
            'r': int(ch.get('1', '255')),
            'g': int(ch.get('2', '255')),
            'b': int(ch.get('3', '255')),
            'blending': int(ch.get('5', '0')),
            'opacity': float(ch.get('7', '1')),
        }
    return colors

def parse_header(header_str):
    """Parse level header for settings."""
    # Split by comma to get key-value pairs
    parts = header_str.split(',')
    header = {}
    # First part is kS38 (color string), handle specially
    i = 0
    while i < len(parts) - 1:
        key = parts[i]
        val = parts[i + 1]
        header[key] = val
        i += 2
    return header

def main():
    gmd = parse_gmd('level_135888458.gmd')
    level_data = decode_level_string(gmd['k4'])

    parts = level_data.split(';')
    header_str = parts[0]

    # Parse header - extract kS38 first (before first comma-separated kA key)
    # Header format: kS38,<color_data>,kA13,0,...
    header_parts = header_str.split(',', 2)  # Split into: kS38, <color_data>, rest
    color_string = header_parts[1] if len(header_parts) > 1 else ''
    colors = parse_color_string(color_string)

    # Parse remaining header
    if len(header_parts) > 2:
        rest = header_parts[2]
        rest_parts = rest.split(',')
        header = {}
        for j in range(0, len(rest_parts) - 1, 2):
            header[rest_parts[j]] = rest_parts[j + 1]
    else:
        header = {}

    # Parse objects
    blocks = []       # Solid blocks (IDs 1-7)
    spikes = []       # Hazards (IDs 8, 39, 103, 143, 472)
    color_triggers = []  # Color triggers (ID 899)
    decorations = []  # Decoration (IDs 1715, 1743)

    BLOCK_IDS = {1, 2, 3, 4, 5, 6, 7}
    SPIKE_IDS = {8, 39, 103, 143, 472}
    DECO_IDS = {1715, 1743}
    SKIP_IDS = {3600}  # End trigger

    for obj_str in parts[1:]:
        if not obj_str.strip():
            continue
        props = obj_str.split(',')
        obj = {}
        for j in range(0, len(props) - 1, 2):
            obj[props[j]] = props[j + 1]

        obj_id = int(obj.get('1', '0'))
        x = float(obj.get('2', '0'))
        y = float(obj.get('3', '0'))
        rot = float(obj.get('6', '0'))
        color_ch = int(obj.get('21', '0'))
        flip_x = int(obj.get('4', '0'))
        flip_y = int(obj.get('5', '0'))

        if obj_id in BLOCK_IDS:
            entry = {'id': obj_id, 'x': x, 'y': y}
            if rot: entry['r'] = rot
            if color_ch: entry['c'] = color_ch
            if flip_x: entry['fx'] = 1
            if flip_y: entry['fy'] = 1
            blocks.append(entry)
        elif obj_id in SPIKE_IDS:
            entry = {'id': obj_id, 'x': x, 'y': y}
            if rot: entry['r'] = rot
            if color_ch: entry['c'] = color_ch
            if flip_x: entry['flipX'] = 1
            if flip_y: entry['flipY'] = 1
            spikes.append(entry)
        elif obj_id == 899:
            ct = {
                'x': x,
                'ch': int(obj.get('23', '0')),
                'r': int(obj.get('7', '255')),
                'g': int(obj.get('8', '255')),
                'b': int(obj.get('9', '255')),
                'duration': float(obj.get('10', '0')),
                'opacity': float(obj.get('35', '1')),
                'blending': int(obj.get('36', '0')),
            }
            color_triggers.append(ct)
        elif obj_id in DECO_IDS:
            entry = {'id': obj_id, 'x': x, 'y': y}
            if rot: entry['r'] = rot
            if color_ch: entry['c'] = color_ch
            decorations.append(entry)
        elif obj_id in SKIP_IDS:
            pass  # Skip end trigger

    # Sort color triggers by x position
    color_triggers.sort(key=lambda t: t['x'])

    # Find level bounds
    all_x = [b['x'] for b in blocks] + [s['x'] for s in spikes]
    max_x = max(all_x) if all_x else 0

    result = {
        'name': gmd.get('k2', 'Unknown'),
        'colors': {str(k): v for k, v in colors.items()},
        'blocks': blocks,
        'spikes': spikes,
        'colorTriggers': color_triggers,
        'decorations': decorations,
        'maxX': max_x,
    }

    with open('level.json', 'w') as f:
        json.dump(result, f, separators=(',', ':'))

    print(f"Extracted: {len(blocks)} blocks, {len(spikes)} spikes, {len(color_triggers)} color triggers, {len(decorations)} decorations")
    print(f"Level bounds: 0 to {max_x} units ({max_x/30:.0f} blocks)")
    print(f"Color channels: {list(colors.keys())}")
    print(f"Output: level.json ({os.path.getsize('level.json') / 1024:.1f} KB)")

import os
main()
