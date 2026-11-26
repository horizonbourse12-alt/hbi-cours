#!/usr/bin/env python3
"""Télécharge les rapports publiés par la BRVM (rapports d'activité trimestriels / semestriels,
états financiers annuels) et met à jour publications/index.json.

Source : https://www.brvm.org/fr/rapports-societe-cotes/<slug>  (tableau « titre | Télécharger »,
pagination ?page=0,1,2…). Les PDF sont rangés dans publications/rapports/ avec le même
nommage que l'application : <SOCIETE>_<T1|S1|T3|Annuel>-<année>.pdf.

Usage : python3 scripts/fetch_rapports.py [NOM_SOCIETE ...]   (sans argument : toutes celles de SOCIETES)
Stdlib uniquement.
"""
import json, os, re, sys, time, unicodedata, urllib.request
from html.parser import HTMLParser

BASE = "https://www.brvm.org"
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "publications", "rapports")
INDEX = os.path.join(RACINE, "publications", "index.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; HBI-rapports/1.0; +https://horizonbourse12-alt.github.io/hbi-cours/)"}

# nom dans l'application -> identifiant de la page BRVM (…/rapports-societe-cotes/<slug>)
SOCIETES = {
    "SGBCI": "sgci",
}
ANNEE_MIN = 2021          # l'application ne suit que 2021 et après
MAX_PAGES = 6


def get(url, binaire=False, essais=3):
    err = None
    for i in range(essais):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if binaire else data.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"{url} : {err}")


class Lignes(HTMLParser):
    """Extrait (titre, href) de chaque ligne de tableau qui contient un lien .pdf."""
    def __init__(self):
        super().__init__()
        self.lignes, self._tr, self._txt, self._href, self._in_td = [], False, [], None, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._tr, self._txt, self._href = True, [], None
        elif tag == "td" and self._tr:
            self._in_td = True
        elif tag == "a" and self._tr and a.get("href", "").lower().split("?")[0].endswith(".pdf"):
            self._href = a["href"]

    def handle_endtag(self, tag):
        if tag == "td":
            self._in_td = False
        elif tag == "tr" and self._tr:
            self._tr = False
            titre = " ".join(" ".join(self._txt).split())
            if self._href and titre:
                self.lignes.append((titre, self._href))

    def handle_data(self, data):
        if self._tr and self._in_td and data.strip():
            self._txt.append(data.strip())


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def classer(titre):
    """-> (code, libellé, année) ou None si le document n'est pas un rapport à garder."""
    t = sans_accents(titre).replace("’", "'")
    if any(m in t for m in ("attestation", "rapport des commissaires", "rapport des cac", "rapport des cacs",
                            "remuneration", "convocation", "avis ", "communique")):
        return None
    ans = re.findall(r"\b(20[12]\d)\b", t)
    if not ans:
        return None
    an = int(ans[-1])
    if re.search(r"\b(1er|1|premier)\s*(er)?\s*trimestre|\b1\s*t\s*20|1er\s*trim", t):
        return ("T1", f"Rapport d'activités — 1er trimestre {an}", an)
    if re.search(r"\b(3|3e|3eme|3ieme|troisieme)\s*trimestre|3eme trimestre", t):
        return ("T3", f"Rapport d'activités — 3e trimestre {an}", an)
    if re.search(r"\b(2|2e|2eme|deuxieme)\s*trimestre", t):
        return ("T2", f"Rapport d'activités — 2e trimestre {an}", an)
    if re.search(r"\b(2|2e|2eme|deuxieme)\s*semestre", t):
        return ("S2", f"Rapport d'activités — 2e semestre {an}", an)
    if "semestre" in t:
        return ("S1", f"Rapport d'activités — 1er semestre {an}", an)
    if "etats financiers" in t or "rapport annuel" in t or "annuel" in t or "exercice" in t:
        return ("Annuel", f"Rapport d'activités annuel et états financiers — exercice {an}", an)
    return None


def date_du_fichier(href):
    m = re.search(r"/(20\d{2})(\d{2})(\d{2})_", href)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""


def cle_date(d):
    j, m, a = (d or "00/00/0000").split("/")
    return (a, m, j)


def lire_societe(nom, slug):
    trouves = {}
    for p in range(MAX_PAGES):
        url = f"{BASE}/fr/rapports-societe-cotes/{slug}" + (f"?page={p}" if p else "")
        pg = Lignes()
        pg.feed(get(url))
        if not pg.lignes:
            break
        for titre, href in pg.lignes:
            c = classer(titre)
            if not c or c[2] < ANNEE_MIN:
                continue
            code, libelle, an = c
            lien = href if href.startswith("http") else BASE + href
            d = date_du_fichier(href)
            k = (code, an)
            # « annule et remplace » / doublons : on garde la publication la plus récente
            if k not in trouves or cle_date(d) > cle_date(trouves[k]["date"]):
                trouves[k] = {"code": code, "titre": libelle, "an": an, "date": d, "url": lien}
    return trouves


def main():
    noms = sys.argv[1:] or list(SOCIETES)
    os.makedirs(DOSSIER, exist_ok=True)
    index = []
    if os.path.exists(INDEX):
        index = json.load(open(INDEX, encoding="utf-8"))
    par_fichier = {e["fichier"]: e for e in index}
    nouveaux = 0
    for nom in noms:
        slug = SOCIETES[nom]
        try:
            docs = lire_societe(nom, slug)
        except Exception as e:  # noqa: BLE001
            print(f"[{nom}] échec : {e}")
            continue
        print(f"[{nom}] {len(docs)} rapport(s) trouvé(s)")
        base = re.sub(r"[^A-Za-z0-9]+", "-", nom).strip("-")
        for (code, an), d in sorted(docs.items(), key=lambda x: x[0][1]):
            suffixe = f"Annuel-{an}" if code == "Annuel" else f"{code}-{an}"
            rel = f"publications/rapports/{base}_{suffixe}.pdf"
            chemin = os.path.join(RACINE, rel)
            if not os.path.exists(chemin):
                try:
                    pdf = get(d["url"], binaire=True)
                except Exception as e:  # noqa: BLE001
                    print(f"  ✗ {rel} : {e}")
                    continue
                if not pdf.startswith(b"%PDF"):
                    print(f"  ✗ {rel} : ce n'est pas un PDF")
                    continue
                open(chemin, "wb").write(pdf)
                nouveaux += 1
                print(f"  + {rel} ({len(pdf)//1024} Ko)")
            ko = os.path.getsize(chemin) // 1024
            periode = f"Exercice {an}" if code == "Annuel" else f"{code} {an}"
            par_fichier[rel] = {"societe": nom, "titre": d["titre"], "periode": periode,
                                "date": d["date"], "fichier": rel, "ko": ko}
    index = sorted(par_fichier.values(), key=lambda e: (e["societe"], cle_date(e["date"])), reverse=False)
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    json.dump(index, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{nouveaux} nouveau(x) fichier(s) ; {len(index)} entrée(s) dans l'index")


if __name__ == "__main__":
    main()
