#!/usr/bin/env python3
"""Robot du soir : lit le BOC (bulletin officiel de la cote) publié sur bfin.brvm.org,
en tire (1) les cours de clôture officiels -> cours.json, (2) la liste des publications
annoncées (section « COMMUNIQUES ») -> boc/AAAAMMJJ.json, puis lance le téléchargement des
rapports des sociétés concernées (scripts/fetch_rapports.py).

Liste des BOC : https://bfin.brvm.org/boc/boc_jour.aspx   (liens .../BOC_JOUR/BOC_AAAAMMJJ.pdf)
Nécessite pdftotext (poppler-utils). Stdlib uniquement.

Usage : python3 scripts/fetch_boc.py            (cas normal : traite le dernier BOC non traité)
        python3 scripts/fetch_boc.py --fichier BOC.pdf --essai   (lecture locale, n'écrit rien)
"""
import json, os, re, subprocess, sys, tempfile, time, urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTE = "https://bfin.brvm.org/boc/boc_jour.aspx"
URL_PDF = "https://bfin.brvm.org/boc/BOC_JOUR/BOC_{}.pdf"
UA = {"User-Agent": "Mozilla/5.0 (compatible; HBI-boc/1.0; +https://horizonbourse12-alt.github.io/hbi-cours/)"}
ETAT = os.path.join(RACINE, "boc", "etat.json")
NB = r"-?\d{1,3}(?: \d{3})*"


def get(url, binaire=False, essais=3):
    err = None
    for i in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                d = r.read()
            return d if binaire else d.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"{url} : {err}")


def pdf_vers_texte(chemin):
    return subprocess.run(["pdftotext", "-layout", chemin, "-"], capture_output=True, text=True, check=True).stdout


def entier(s):
    s = (s or "").strip()
    return int(s.replace(" ", "")) if re.fullmatch(NB, s) else None


def lire_actions(texte):
    """Lignes du tableau « MARCHE DES ACTIONS » : symbole, précédent, ouverture, clôture, volume."""
    out = {}
    for lig in texte.splitlines():
        if "TOTAL - MARCHE DES ACTIONS" in lig:
            break
        t = [x for x in re.split(r"\s{2,}", lig.strip()) if x]
        if len(t) < 7 or not re.fullmatch(r"[A-Z]{3,6}", t[0]) or entier(t[2]) is None:
            continue
        # t = [symbole, titre, précédent, ouv., clôt., variation %, volume, valeur, …]
        i = 2
        prec = entier(t[i])
        suspendu = t[i + 1] in ("SP", "NC", "-") and t[i + 2] in ("SP", "NC", "-")   # valeur suspendue / non cotée ce jour
        ouv, clo = (prec, prec) if suspendu else (entier(t[i + 1]), entier(t[i + 2]))
        if None in (prec, ouv, clo) or not re.fullmatch(r"-?\d+,\d+ ?%", t[i + 3]):
            continue
        out[t[0]] = {"s": t[0], "veille": prec, "ouv": ouv, "dernier": clo, "volume": 0 if suspendu else (entier(t[i + 4]) or 0)}
    return out


def lire_communiques(texte):
    """Section « COMMUNIQUES » : émetteur | N° | nature | objet."""
    m = re.search(r"^COMMUNIQUES\s*$", texte, re.M)
    if not m:
        return []
    bloc = texte[m.end():]
    fin = re.search(r"^\s*\d{1,3}\s*$", bloc, re.M)  # numéro de page qui clôt la section
    bloc = bloc[:fin.start()] if fin else bloc
    items, cur = [], None
    for lig in bloc.splitlines():
        if not lig.strip() or lig.strip().startswith("Emetteur"):
            continue
        t = [x for x in re.split(r"\s{2,}", lig.strip()) if x]
        if len(t) >= 3 and re.fullmatch(r"\d{8}(-\d+)?", t[1]):
            cur = {"emetteur": t[0], "numero": t[1], "nature": t[2], "objet": " ".join(t[3:])}
            items.append(cur)
        elif cur and t:
            cur["objet"] = (cur["objet"] + " " + " ".join(t)).strip()
    for it in items:
        s = (it["nature"] + " " + it["objet"]).lower()
        it["rapport"] = bool(re.search(r"rapport d.activit|etats? financiers|états? financiers|rapport annuel", s)) \
            and "communiqué de presse" not in it["nature"].lower() and "press release" not in s
    return items


def construire(texte, date_iso):
    actions = lire_actions(texte)
    n = re.search(r"N°\s*(\d+)", texte)
    jj = f"{date_iso[6:8]}/{date_iso[4:6]}/{date_iso[0:4]}"
    rows = []
    for a in actions.values():
        bas, haut = min(a["ouv"], a["dernier"]), max(a["ouv"], a["dernier"])
        rows.append({"s": a["s"], "veille": a["veille"], "dernier": a["dernier"] if a["volume"] else None,
                     "bas": bas, "haut": haut, "volume": a["volume"]})
    cours = {"date": jj, "heure": "clôture", "provisoire": False,
             "source": f"BOC n° {n.group(1)}" if n else "BOC", "rows": rows}
    return cours, lire_communiques(texte)


def etat():
    return json.load(open(ETAT, encoding="utf-8")) if os.path.exists(ETAT) else {"traites": [], "attente": {}}


def traiter(date_iso, pdf_path):
    texte = pdf_vers_texte(pdf_path)
    cours, annonces = construire(texte, date_iso)
    print(f"BOC {date_iso} : {len(cours['rows'])} cours, {len(annonces)} communiqué(s), "
          f"{sum(1 for a in annonces if a['rapport'])} rapport(s) annoncé(s)")
    return cours, annonces


def main():
    if "--fichier" in sys.argv:
        pdf = sys.argv[sys.argv.index("--fichier") + 1]
        m = re.search(r"(20\d{6})", os.path.basename(pdf))
        date_iso = m.group(1) if m else "20000101"
        cours, annonces = traiter(date_iso, pdf)
        if "--essai" in sys.argv:
            print(json.dumps(annonces, ensure_ascii=False, indent=1))
            print([r["s"] for r in cours["rows"]])
            return
    st = etat()
    page = get(LISTE)
    dates = sorted(set(re.findall(r"BOC_(20\d{6})\.pdf", page)))
    if not dates:
        print("Aucun BOC listé : page illisible ?")
        return
    nouveaux = [d for d in dates if d not in st["traites"]]
    if not st["traites"]:          # premier lancement : seulement le plus récent
        nouveaux = dates[-1:]
    if nouveaux:
        d = nouveaux[-1]           # on traite le plus récent ; les jours manqués n'ont plus d'intérêt pour les cours
        try:
            data = get(URL_PDF.format(d), binaire=True)
        except Exception as e:  # noqa: BLE001
            print(f"BOC {d} pas encore téléchargeable : {e}")
            data = None
        if data and data.startswith(b"%PDF"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(data)
            cours, annonces = traiter(d, f.name)
            os.unlink(f.name)
            try:
                actuel = json.load(open(os.path.join(RACINE, "cours.json"), encoding="utf-8"))
                ja = actuel["date"].split("/"); jb = cours["date"].split("/")
                plus_recent = ja[::-1] > jb[::-1]      # cours.json contient déjà une séance plus récente que ce BOC
            except Exception:  # noqa: BLE001
                plus_recent = False
            if plus_recent:
                print(f"cours.json ({actuel['date']}) est plus récent que ce BOC ({cours['date']}) : inchangé")
            elif len(cours["rows"]) >= 30:
                json.dump(cours, open(os.path.join(RACINE, "cours.json"), "w", encoding="utf-8"), ensure_ascii=False)
                print("cours.json : clôture officielle écrite")
            else:
                print("Moins de 30 cours lus : cours.json inchangé")
            os.makedirs(os.path.join(RACINE, "boc"), exist_ok=True)
            json.dump({"date": cours["date"], "source": cours["source"], "communiques": annonces},
                      open(os.path.join(RACINE, "boc", f"{d}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            st["traites"] = (st["traites"] + [d])[-30:]
            for a in annonces:
                if a["rapport"]:
                    st["attente"][a["emetteur"]] = d
    # rapports annoncés : on les cherche (et on réessaie aux passages suivants tant qu'ils ne sont pas là)
    if st["attente"]:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import fetch_rapports as fr
        for nom_boc in list(st["attente"]):
            nom = fr.resoudre(nom_boc)
            if not nom:
                print(f"[{nom_boc}] rapport annoncé, société inconnue : à ajouter dans fetch_rapports.py (ALIAS)")
                continue
            avant = len([f for f in os.listdir(fr.DOSSIER) if f.endswith(".pdf")]) if os.path.isdir(fr.DOSSIER) else 0
            sys.argv = ["fetch_rapports.py", nom]
            fr.main()
            apres = len([f for f in os.listdir(fr.DOSSIER) if f.endswith(".pdf")])
            if apres > avant:
                del st["attente"][nom_boc]
    os.makedirs(os.path.dirname(ETAT), exist_ok=True)
    json.dump(st, open(ETAT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
