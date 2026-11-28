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
    iS, iV, iVol, iVar = col("symbole"), col("veille"), col("volume"), col("variation")
    iC = col("cloture") if col("cloture") is not None else col("dernier")
    if None in (iS, iV, iC): raise SystemExit(f"Colonnes manquantes : {h}")
    rows = []
    for r in t[hi + 1:]:
        if len(r) <= max(iS, iV, iC): continue
        sym = r[iS].strip().upper()
        veille, dernier = num(r[iV]), num(r[iC])
        vol = num(r[iVol]) if iVol is not None and iVol < len(r) else None
        if not re.fullmatch(r"[A-Z]{3,6}", sym) or not veille: continue
        var = num(r[iVar]) if iVar is not None and iVar < len(r) else None
        if dernier is not None and dernier == veille and not vol: dernier = None
        rows.append({"s": sym, "veille": int(veille), "dernier": None if dernier is None else int(dernier),
                     "volume": None if vol is None else int(vol), "_var": var})
    txt = " ".join(" ".join(x) for x in [[re.sub(r"<[^>]+>", " ", html)]])
    m = re.search(r"Derni[eè]re mise [àa] jour\s*:?\s*[A-Za-zéèûôîà]*,?\s*(\d{1,2})\s+([A-Za-zéèûôîà]+),?\s*(\d{4})\s*-\s*(\d{1,2}):(\d{2})", txt)
    if not m: raise SystemExit("Date de mise à jour introuvable")
    jj, mois, aaaa, hh, mm = int(m.group(1)), MOIS.get(norm(m.group(2))), int(m.group(3)), int(m.group(4)), int(m.group(5))
    if not mois: raise SystemExit(f"Mois inconnu : {m.group(2)}")
    out = {"date": f"{jj:02d}/{mois:02d}/{aaaa}", "heure": f"{hh:02d}h{mm:02d}", "provisoire": True, "source": "brvm.org (différé 15 min)", "rows": rows}
    try:
        ind = lire_indices(html)
        if ind: out["indices"] = ind
    except Exception as e:
        print("Indices illisibles (ignorés) :", e)
    return out


def lire_indices(html):
    """Indices affichés par la BRVM (BRVM-C = Composite, BRVM-30, BRVM-PRES = Prestige) : valeur et variation du jour."""
    txt = " ".join(re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").replace("\xa0", " ").split())
    res = []
    for code, nom in (("BRVM-C", "BRVM Composite"), ("BRVM-30", "BRVM 30"), ("BRVM-PRES", "BRVM Prestige")):
        m = re.search(re.escape(code) + r"\s*([\d ]+[,.]\d+)\s*([-−+]?\s*\d+[,.]\d+)\s*%", txt)
        if not m: continue
        v = num(m.group(1)); pct = num(m.group(2).replace("−", "-").replace(" ", ""))
        if v and pct is not None and abs(pct) < 30: res.append({"n": nom, "v": v, "p": pct})
    return res


CP = "data/cloture_precedente.json"


def iso(d):
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return m.group(3) + m.group(2) + m.group(1) if m else ""


HIST = "data/historique_cloture.json"
HIST_IND = "data/historique_indices.json"


def archiver_cloture(cp):
    """Archive la clôture de chaque séance (dernier relevé du jour) : sert de cours de référence au palmarès « 1 an », « 5 ans »..."""
    try: h = json.load(open(HIST, encoding="utf-8"))
    except Exception: h = {}
    h[cp["date"]] = cp["closes"]
    json.dump(dict(sorted(h.items(), key=lambda kv: iso(kv[0]))), open(HIST, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


def archiver_indices(old):
    """Archive les niveaux des indices (Composite, 30, Prestige) du dernier relevé d'une séance, pour le récap hebdomadaire."""
    try:
        ind = {x["n"]: x["v"] for x in (old.get("indices") or []) if x.get("n") and x.get("v")}
        if not ind: return
        try: h = json.load(open(HIST_IND, encoding="utf-8"))
        except Exception: h = {}
        h[old["date"]] = ind
        json.dump(dict(sorted(h.items(), key=lambda kv: iso(kv[0]))), open(HIST_IND, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    except Exception: pass


def clotures_precedentes(data, old):
    """Clôtures de la dernière séance antérieure au relevé, mémorisées dans data/cloture_precedente.json."""
    try: cp = json.load(open(CP, encoding="utf-8"))
    except Exception: cp = {}
    if old and old.get("rows") and iso(old.get("date")) and iso(old["date"]) < iso(data["date"]) and cp.get("date") != old["date"]:
        cp = {"date": old["date"], "closes": {r["s"]: (r["dernier"] if r.get("dernier") else r["veille"]) for r in old["rows"]}}
        import os; os.makedirs(os.path.dirname(CP), exist_ok=True)
        json.dump(cp, open(CP, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        archiver_cloture(cp)
        archiver_indices(old)
    return cp.get("closes", {}) if iso(cp.get("date")) and iso(cp["date"]) < iso(data["date"]) else {}


def corriger_veille(data, old):
    """La colonne « Cours veille » de la page BRVM reprend en réalité le cours d'ouverture du jour : ce n'est pas la clôture de la veille.
    La vraie clôture de la veille est (1) celle de la séance précédente mémorisée par le robot, (2) à défaut, déduite du cours et de la
    colonne « Variation (%) » de la page. Contrôle de cohérence avec la variation affichée."""
    prev = clotures_precedentes(data, old)
    nb_ok = nb_est = 0
    for r in data["rows"]:
        v = r.pop("_var", None); d = r["dernier"]
        est = None
        if d and v is not None:
            if abs(v) < 1e-9: est = d
            elif v > -99: est = d / (1 + v / 100.0)
        cand = prev.get(r["s"])
        coherent = lambda x: not (d and v is not None) or abs((d / x - 1) * 100 - v) <= 0.02
        if cand and coherent(cand): r["veille"] = int(cand); nb_ok += 1
        elif est: r["veille"] = int(round(est)); nb_est += 1
        elif cand: r["veille"] = int(cand); nb_ok += 1
    print(f"Clôture de la veille : {nb_ok} reprises de la séance précédente, {nb_est} déduites de la variation")
    return data


if __name__ == "__main__":
    data = parse(fetch())
    try: data = corriger_veille(data, json.load(open(OUT, encoding="utf-8")))
    except Exception as e: data = corriger_veille(data, None); print("Relevé précédent illisible :", e)
    if len(data["rows"]) < 40:
        raise SystemExit(f"Relevé incomplet ({len(data['rows'])} lignes) : fichier non modifié")
    try:
        old = json.load(open(OUT, encoding="utf-8"))
        if old.get("date") == data["date"] and old.get("heure") == data["heure"]:
            print("Aucun nouveau relevé"); sys.exit(0)
        if old.get("provisoire") is False and old.get("date") == data["date"]:
            print("Clôture officielle (BOC) déjà en place : cours différés ignorés"); sys.exit(0)
    except Exception:
        pass
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"cours.json écrit : {data['date']} {data['heure']} ({len(data['rows'])} sociétés)")
