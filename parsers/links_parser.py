import re

LINE_RE = re.compile(
    r"^\s*Глава\s+(\d+)\s*:\s*(https?://\S+)\s*$", re.I
)

def parse_links_file(path):
    result = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = LINE_RE.match(line)
            if match:
                result.append({
                    "number": int(match.group(1)),
                    "url": match.group(2),
                })
    return result
