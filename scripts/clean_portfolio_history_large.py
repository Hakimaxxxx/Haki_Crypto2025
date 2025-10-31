import argparse
import json
import os
import sys
from typing import Generator, Optional


def sniff_format(path: str) -> str:
    """Return 'array' if file starts with a JSON array, else 'ndjson'."""
    with open(path, 'r', encoding='utf-8') as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                # default to ndjson if empty/unreadable; caller will handle
                return 'ndjson'
            for ch in chunk:
                if ch.isspace():
                    continue
                return 'array' if ch == '[' else 'ndjson'


def iter_array_objects(path: str) -> Generator[str, None, None]:
    """Yield JSON object strings from a top-level JSON array without loading the whole file.

    This scans characters, tracking string/escape state and brace depth to extract
    each top-level object as a string. It assumes the file is a single JSON array.
    """
    with open(path, 'r', encoding='utf-8') as f:
        # Skip until first '['
        in_string = False
        escape = False
        depth = 0  # counts { } depth only
        buf: list[str] = []
        started = False
        # We don't need to record array bracket depth; we only extract objects
        while True:
            chunk = f.read(1024 * 64)
            if not chunk:
                break
            for ch in chunk:
                if not started:
                    # Skip whitespace and commas until an object starts
                    if ch == '{':
                        started = True
                        depth = 1
                        buf.append(ch)
                    else:
                        # ignore everything until first '{'
                        continue
                else:
                    # Inside an object; handle strings and escapes properly
                    if in_string:
                        buf.append(ch)
                        if escape:
                            escape = False
                        elif ch == '\\':
                            escape = True
                        elif ch == '"':
                            in_string = False
                    else:
                        if ch == '"':
                            in_string = True
                            buf.append(ch)
                        elif ch == '{':
                            depth += 1
                            buf.append(ch)
                        elif ch == '}':
                            depth -= 1
                            buf.append(ch)
                            if depth == 0:
                                # Completed an object
                                yield ''.join(buf)
                                buf.clear()
                                started = False
                        else:
                            buf.append(ch)


def is_zero_value(obj: dict) -> bool:
    v = obj.get('value')
    # Treat numeric zero or string '0'/'0.0' as zero
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return float(v) == 0.0
    if isinstance(v, str):
        try:
            return float(v.strip()) == 0.0
        except Exception:
            return False
    return False


def filter_ndjson(input_path: str, output_path: str) -> tuple[int, int, int]:
    read_count = kept = dropped = 0
    with open(input_path, 'r', encoding='utf-8') as fin, open(output_path, 'w', encoding='utf-8') as fout:
        for line_no, line in enumerate(fin, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                read_count += 1
            except json.JSONDecodeError:
                # If the file is a single JSON array accidentally read here, bail out
                raise
            if is_zero_value(obj):
                dropped += 1
                continue
            kept += 1
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            if kept % 100000 == 0:
                print(f"Kept {kept:,} objects...", file=sys.stderr)
    return read_count, kept, dropped


def filter_array(input_path: str, output_path: str) -> tuple[int, int, int]:
    read_count = kept = dropped = 0
    with open(output_path, 'w', encoding='utf-8') as fout:
        fout.write('[')
        first = True
        for obj_str in iter_array_objects(input_path):
            try:
                obj = json.loads(obj_str)
            except json.JSONDecodeError as e:
                # Re-raise with context
                raise json.JSONDecodeError(f"Error parsing object after {read_count} items: {e.msg}", e.doc, e.pos)
            read_count += 1
            if is_zero_value(obj):
                dropped += 1
                continue
            if not first:
                fout.write(',\n')
            fout.write(json.dumps(obj, ensure_ascii=False))
            first = False
            kept += 1
            if kept and kept % 100000 == 0:
                print(f"Kept {kept:,} objects...", file=sys.stderr)
        fout.write(']\n')
    return read_count, kept, dropped


def main():
    p = argparse.ArgumentParser(description="Filter out entries with value == 0.0 from large JSON (NDJSON or array).")
    p.add_argument('input', help='Path to input JSON file (NDJSON or JSON array)')
    p.add_argument('-o', '--output', help='Path to output file. Default: <input>.cleaned.json')
    p.add_argument('--inplace', action='store_true', help='Replace the input file in-place (creates a .bak backup)')
    p.add_argument('--format', choices=['ndjson', 'array'], help='Force input format. Default: auto-detect')
    args = p.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    fmt = args.format or sniff_format(input_path)
    if args.output:
        output_path = args.output
    elif args.inplace:
        # write to temp then replace
        output_path = input_path + '.cleaning.tmp'
    else:
        base, ext = os.path.splitext(input_path)
        output_path = base + '.cleaned' + (ext or '.json')

    print(f"Detected format: {fmt}")
    try:
        if fmt == 'ndjson':
            read_count, kept, dropped = filter_ndjson(input_path, output_path)
        else:
            read_count, kept, dropped = filter_array(input_path, output_path)
    except json.JSONDecodeError as e:
        if not args.format:
            # If autodetect was wrong, try the other format once
            alt = 'array' if fmt == 'ndjson' else 'ndjson'
            print(f"Autodetect as {fmt} failed: {e}. Retrying as {alt}...", file=sys.stderr)
            if alt == 'ndjson':
                read_count, kept, dropped = filter_ndjson(input_path, output_path)
            else:
                read_count, kept, dropped = filter_array(input_path, output_path)
        else:
            raise

    print(f"Processed: {read_count:,} | Kept: {kept:,} | Dropped (value==0): {dropped:,}")

    if args.inplace:
        backup_path = input_path + '.bak'
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.replace(input_path, backup_path)
            os.replace(output_path, input_path)
            print(f"Replaced input in-place. Backup at: {backup_path}")
        except Exception as e:
            print(f"In-place replace failed: {e}", file=sys.stderr)
            print(f"Cleaned output left at: {output_path}")
            sys.exit(2)


if __name__ == '__main__':
    main()
