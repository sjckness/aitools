"""Parser delle card .graph/cards/<ID>.md. Solo standard library."""
import re

SECTIONS = ("Obiettivo", "Puoi modificare", "Leggi",
            "Criteri di accettazione", "Fuori scope", "Correzioni richieste")

_ITEM = re.compile(r"^\s*(?:[-*]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)(.*\S)\s*$")


def _title(raw):
    t = re.sub(r"\([^)]*\)", "", raw)
    return re.sub(r"\s+", " ", t).strip()


def parse_card(text):
    out = {}
    cur = None
    buf = []
    fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(buf).strip("\n")
            cur = _title(line[3:])
            buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip("\n")
    return out


def section_items(text, section):
    body = parse_card(text).get(section)
    if not body:
        return []
    items = []
    for line in body.splitlines():
        m = _ITEM.match(line)
        if m:
            items.append(m.group(1).strip())
        elif items and line.startswith((" ", "\t")) and line.strip():
            items[-1] += " " + line.strip()  # riga di continuazione
    return items


def section_paths(text, section):
    paths = []
    for item in section_items(text, section):
        m = re.search(r"`([^`]+)`", item)
        tok = m.group(1) if m else (item.split() or [""])[0]
        paths.append(tok.rstrip(".,;:)"))
    return paths


def count_criteria(text):
    return len(section_items(text, "Criteri di accettazione"))
