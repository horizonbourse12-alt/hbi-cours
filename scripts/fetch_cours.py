#!/usr/bin/env python3
"""Lit la page des cours de la BRVM (différée de 15 minutes) et écrit cours.json (format : voir FORMAT.md)."""
import json, re, sys, time, unicodedata, urllib.request
from html.parser import HTMLParser

URL = "https://www.brvm.org/fr/cours-actions/0"
OUT = "cours.json"
MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().replace("\xa0", " ").strip()


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._t, self._r, self._c = [], None, None, None
    def handle_starttag(self, tag, attrs):
        if tag == "table": self._t = []
        elif tag == "tr" and self._t is not None: self._r = []
        elif tag in ("td", "th") and self._r is not None: self._c = []
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._c is not None and self._r is not None:
            self._r.append(" ".join("".join(self._c).split())); self._c = None
        elif tag == "tr" and self._r is not None and self._t is not None:
            if self._r: self._t.append(self._r)
            self._r = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t); self._t = None
    def handle_data(self, data):
        if self._c is not None: self._c.append(data)


def num(s):
    s = (s or "").replace("\xa0", "").replace(" ", "").replace("FCFA", "").replace(",", ".")
    s = s.replace(" ", "")
    try: return float(s)
    except ValueError: return None


def fetch():
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (compatible; HBI-cours/1.0)", "Accept-Language": "fr"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e; time.sleep(5 * (i + 1))
    raise SystemExit(f"Lecture impossible : {last}")


def parse(html):
    p = Tables(); p.feed(html)
    best = None
    for t in p.tables:
        for hi, row in enumerate(t[:3]):
            h = [norm(c) for c in row]
            if any(c.startswith("symbole") for c in h) and any("veille" in c for c in h):
                best = (t, hi, h); break
        if best: break
    if not best: raise SystemExit("Tableau des cours introuvable (structure de la page modifiée ?)")
    t, hi, h = best
    def col(*keys):
        for i, c in enumerate(h):
            if all(k in c for k in keys): return i
        return None
    iS, iV, iVol = col("symbole"), col("veille"), col("volume")
    iC = col("cloture") if col("cloture") is not None else col("dernier")
    if None in (iS, iV, iC): raise SystemExit(f"Colonnes manquantes : {h}")
    rows = []
    for r in t[hi + 1:]:
        if len(r) <= max(iS, iV, iC): continue
        sym = r[iS].strip().upper()
        veille, dernier = num(r[iV]), num(r[iC])
        vol = num(r[iVol]) if iVol is not None and iVol < len(r) else None
        if not re.fullmatch(r"[A-Z]{3,6}", sym) or not veille: continue
        if dernier is not None and dernier == veille and not vol: dernier = None
        rows.append({"s": sym, "veille": int(veille), "dernier": None if dernier is None else int(dernier),
                     "volume": None if vol is None else int(vol)})
    txt = " ".join(" ".join(x) for x in [[re.sub(r"<[^>]+>", " ", html)]])
    m = re.search(r"Derni[eè]re mise [àa] jour\s*:?\s*[A-Za-zéèûôîà]*,?\s*(\d{1,2})\s+([A-Za-zéèûôîà]+),?\s*(\d{4})\s*-\s*(\d{1,2}):(\d{2})", txt)
    if not m: raise SystemExit("Date de mise à jour introuvable")
    jj, mois, aaaa, hh, mm = int(m.group(1)), MOIS.get(norm(m.group(2))), int(m.group(3)), int(m.group(4)), int(m.group(5))
    if not mois: raise SystemExit(f"Mois inconnu : {m.group(2)}")
    return {"date": f"{jj:02d}/{mois:02d}/{aaaa}", "heure": f"{hh:02d}h{mm:02d}", "provisoire": True, "source": "brvm.org (différé 15 min)", "rows": rows}


if __name__ == "__main__":
    data = parse(fetch())
    if len(data["rows"]) < 40:
        raise SystemExit(f"Relevé incomplet ({len(data['rows'])} lignes) : fichier non modifié")
    try:
        old = json.load(open(OUT, encoding="utf-8"))
        if old.get("date") == data["date"] and old.get("heure") == data["heure"]:
            print("Aucun nouveau relevé"); sys.exit(0)
    except Exception:
        pass
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"cours.json écrit : {data['date']} {data['heure']} ({len(data['rows'])} sociétés)")
