#!/usr/bin/env python3
"""Télécharge les rapports publiés par la BRVM (rapports d'activité trimestriels / semestriels,
états financiers annuels) et met à jour publications/index.json.

Source : https://www.brvm.org/fr/rapports-societe-cotes/<slug>  (tableau « titre | Télécharger »,
pagination ?page=0,1,2…). Les PDF sont rangés dans publications/rapports/ avec le même
nommage que l'application : <SOCIETE>_<T1|S1|T3|Annuel>-<année>.pdf.

Usage : python3 scripts/fetch_rapports.py [NOM_SOCIETE ...]   (sans argument : toutes celles de SOCIETES)
Stdlib uniquement.
"""
import json, os, re, sys, time, unicodedata, urllib.error, urllib.request
from html.parser import HTMLParser

BASE = "https://www.brvm.org"
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "publications", "rapports")
INDEX = os.path.join(RACINE, "publications", "index.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; HBI-rapports/1.0; +https://horizonbourse12-alt.github.io/hbi-cours/)"}

# nom dans l'application -> page BRVM (…/rapports-societe-cotes/<slug>) ; "~mot+mot|…" = slug à retrouver dans la liste des émetteurs
SOCIETES = {
    "SGBCI": "sgci",
    "NESTLE CI": "nestle-ci", "PALM CI": "palm-ci", "SAPH CI": "saph-ci", "SUCRIVOIRE": "sucrivoire",
    "SICOR CI": "sicor", "SOLIBRA CI": "solibra", "SOGB CI": "sogb", "SITAB CI": "sitab",
    "SERVAIR ABIDJAN CI": "servair-abidjan-ci", "BERNABE CI": "bernabe-ci", "CFAO MOTORS CI": "cfao-motors-ci",
    "LOTERIE NATIONALE DU BENIN": "lnb", "NEI-CEDA CI": "nei-ceda-ci", "SMB CI": "smb",
    "ECOBANK COTE D'IVOIRE": "ecobank-ci", "SOCIETE IVOIRIENNE DE BANQUE": "sib", "BIIC BN": "biic",
    "BICI CI": "bici-ci", "BOA BN": "bank-africa-bn", "BOA BF": "bank-africa-bf", "BOA CI": "bank-africa-ci",
    "BOA ML": "bank-africa-ml", "BOA NG": "bank-africa-ng", "BOA SENEGAL": "bank-africa-sn",
    "CORIS BANK INTERNATIONAL": "coris-bank-international", "ECOBANK TRANS. INCORP. TG": "ecobank-tg",
    "NSIA BANQUE COTE D'IVOIRE": "nsbc", "ORAGROUP TOGO": "oragroup", "SAFCA CI": "safca-ci",
    "BRIDGE BANK GROUP CI": "bbgci", "SICABLE CI": "sicable", "FILTISAC CI": "filtisac-ci",
    "AFRICA GLOBAL LOGISTICS CI": "bollore-transport-logistics", "EVIOSYS PACKAGING SIEM CI": "crown-siem-ci",
    "ERIUM CI (Ex AIR LIQUIDE CI)": "air-liquide-ci", "SETAO CI": "setao-ci", "CIE CI": "cie-ci",
    "SODE CI": "sodeci", "ONATEL BF": "onatel-bf", "ORANGE COTE D'IVOIRE": "orange-ci", "SONATEL SN": "sonatel",
    # pages non vérifiées : retrouvées dans la liste des émetteurs de la BRVM
    "UNILEVER CI": "~unilever", "UNIWAX CI": "~uniwax", "TRACTAFRIC MOTORS CI": "~tractafric",
    "VIVO ENERGY CI": "~vivo|shell", "TOTALENERGIES MARKETING CI": "~total+ci|total+cote|total+ivoire",
    "TOTALENERGIES MARKETING SN": "~total+sn|total+senegal",
}
# noms utilisés par le BOC (colonne « Emetteur ») quand ils diffèrent de ceux de l'application
ALIAS = {"ECOBANK TG": "ECOBANK TRANS. INCORP. TG", "ETI TG": "ECOBANK TRANS. INCORP. TG", "ETI": "ECOBANK TRANS. INCORP. TG",
         "SG CI": "SGBCI", "SGB CI": "SGBCI", "SGCI": "SGBCI", "SOCIETE GENERALE CI": "SGBCI",
         "AIR LIQUIDE CI": "ERIUM CI (Ex AIR LIQUIDE CI)", "ERIUM CI": "ERIUM CI (Ex AIR LIQUIDE CI)",
         "BOLLORE AFRICA LOGISTICS CI": "AFRICA GLOBAL LOGISTICS CI", "CROWN SIEM CI": "EVIOSYS PACKAGING SIEM CI",
         "SODECI": "SODE CI", "SIB": "SOCIETE IVOIRIENNE DE BANQUE", "LNB": "LOTERIE NATIONALE DU BENIN",
         "NSBC": "NSIA BANQUE COTE D'IVOIRE", "ORAGROUP": "ORAGROUP TOGO", "ORANGE CI": "ORANGE COTE D'IVOIRE",
         "ONATEL": "ONATEL BF", "SONATEL": "SONATEL SN", "SICOR": "SICOR CI", "SITAB": "SITAB CI",
         "SMB": "SMB CI", "SOGB": "SOGB CI", "SOLIBRA": "SOLIBRA CI", "SICABLE": "SICABLE CI",
         "BBGCI": "BRIDGE BANK GROUP CI", "BIIC": "BIIC BN", "SUCRIVOIRE CI": "SUCRIVOIRE"}
ANNEE_MIN = time.gmtime().tm_year - 2   # trois dernières années (ex. en 2026 : 2024, 2025, 2026)
MAX_PAGES = 6


def get(url, binaire=False, essais=3):
    err = None
    for i in range(essais):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if binaire else data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                raise RuntimeError(f"{url} : HTTP {e.code}")
            err = e
            time.sleep(2 + 3 * i)
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


_LISTE = {}


def slug_de(nom):
    """Page BRVM d'une société ; pour « ~mots », on cherche dans la liste officielle des émetteurs."""
    v = SOCIETES[nom]
    if not v.startswith("~"):
        return v
    if not _LISTE:
        for p in range(6):
            try:
                html = get(f"{BASE}/fr/rapports-societes-cotees" + (f"?page={p}" if p else ""))
            except Exception:  # noqa: BLE001
                break
            slugs = set(re.findall(r"/fr/rapports-societe-cotes/([a-z0-9\-]+)", html))
            if not slugs - set(_LISTE):
                break
            _LISTE.update({x: 1 for x in slugs})
    for alt in v[1:].split("|"):
        mots = alt.split("+")
        for sl in _LISTE:
            toks = set(sl.split("-"))
            if all(any(t == m or (len(m) > 3 and t.startswith(m)) for t in toks) for m in mots):
                return sl
    raise RuntimeError(f"page BRVM de {nom} introuvable dans la liste des émetteurs")


def resoudre(nom):
    """Nom de l'application correspondant à un nom lu dans le BOC (ou None)."""
    cle = re.sub(r"\s+", " ", sans_accents(nom).upper().replace("’", "'")).strip()
    for k in SOCIETES:
        if re.sub(r"\s+", " ", sans_accents(k).upper()) == cle:
            return k
    for k, v in ALIAS.items():
        if re.sub(r"\s+", " ", sans_accents(k).upper()) == cle:
            return v
    return None


def lire_societe(nom, slug):
    trouves = {}
    for p in range(MAX_PAGES):
        url = f"{BASE}/fr/rapports-societe-cotes/{slug}" + (f"?page={p}" if p else "")
        pg = Lignes()
        pg.feed(get(url))
        if not pg.lignes:
            break
        anciens = gardes = 0
        for titre, href in pg.lignes:
            c = classer(titre)
            if c and c[2] < ANNEE_MIN:
                anciens += 1
            if not c or c[2] < ANNEE_MIN:
                continue
            gardes += 1
            code, libelle, an = c
            lien = href if href.startswith("http") else BASE + href
            d = date_du_fichier(href)
            k = (code, an)
            # « annule et remplace » / doublons : on garde la publication la plus récente
            if k not in trouves or cle_date(d) > cle_date(trouves[k]["date"]):
                trouves[k] = {"code": code, "titre": libelle, "an": an, "date": d, "url": lien}
        if anciens and not gardes:   # page entièrement antérieure à ANNEE_MIN : inutile de lire les suivantes
            break
        time.sleep(1)
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
        try:
            docs = lire_societe(nom, slug_de(nom))
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
