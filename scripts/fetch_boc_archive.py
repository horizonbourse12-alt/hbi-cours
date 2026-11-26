#!/usr/bin/env python3
"""Archive des BOC : télécharge les BOC des 31 derniers jours (liste bfin.brvm.org/boc/boc_jour.aspx)
dans publications/boc/BOC_AAAAMMJJ.pdf et tient à jour publications/boc/index.json
(date, indice composite, variation, pages, taille) lu par l'application.
Les BOC plus anciens que 31 jours sont retirés du dossier (l'historique Git les garde) pour limiter le poids du dépôt.
Nécessite pdftotext + pdfinfo (poppler-utils). Stdlib uniquement.
"""
import datetime as dt, json, os, re, subprocess, sys, time, urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER = os.path.join(RACINE, "publications", "boc")
LISTE = "https://bfin.brvm.org/boc/boc_jour.aspx"
URL_PDF = "https://bfin.brvm.org/boc/BOC_JOUR/BOC_{}.pdf"
UA = {"User-Agent": "Mozilla/5.0 (compatible; HBI-boc/1.0; +https://horizonbourse12-alt.github.io/le_Semeur.app/)"}
JOURS = 31


def get(url, essais=3):
    err = None
    for i in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"{url} : {err}")


def infos(chemin):
    """(composite, variation, pages) lus dans le PDF ; None si illisible."""
    try:
        t = subprocess.run(["pdftotext", "-layout", "-l", "1", chemin, "-"], capture_output=True, text=True, check=True).stdout
        p = subprocess.run(["pdfinfo", chemin], capture_output=True, text=True, check=True).stdout
        pages = int(re.search(r"Pages:\s+(\d+)", p).group(1))
        comp = re.search(r"BRVM COMPOSITE\s+(\d[\d ]*,\d+)", t)
        var = re.search(r"Variation Jour\s+(-?\d+,\d+ ?%)", t)
        return (comp.group(1).strip() if comp else None, var.group(1).replace(" ", " ") if var else None, pages)
    except Exception as e:  # noqa: BLE001
        print("infos illisibles :", e)
        return (None, None, None)


def main():
    os.makedirs(DOSSIER, exist_ok=True)
    page = get(LISTE).decode("utf-8", "replace")
    dates = sorted(set(re.findall(r"BOC_(20\d{6})\.pdf", page)))
    limite = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=JOURS)).strftime("%Y%m%d")
    voulus = [d for d in dates if d >= limite]
    print(f"{len(dates)} BOC listés, {len(voulus)} dans les {JOURS} derniers jours")
    for d in voulus:
        f = os.path.join(DOSSIER, f"BOC_{d}.pdf")
        if os.path.exists(f):
            continue
        try:
            data = get(URL_PDF.format(d))
        except Exception as e:  # noqa: BLE001
            print(f"BOC {d} : {e}")
            continue
        if not data.startswith(b"%PDF"):
            print(f"BOC {d} : pas un PDF")
            continue
        open(f, "wb").write(data)
        print(f"BOC {d} : {len(data) // 1024} Ko")
        time.sleep(1)
    # nettoyage + index
    idx = []
    for nom in sorted(os.listdir(DOSSIER)):
        m = re.fullmatch(r"BOC_(20\d{6})\.pdf", nom)
        if not m:
            continue
        d = m.group(1)
        f = os.path.join(DOSSIER, nom)
        if d < limite:
            os.remove(f)
            print(f"BOC {d} retiré (plus de {JOURS} jours)")
            continue
        comp, var, pages = infos(f)
        idx.append({"date": f"{d[6:]}/{d[4:6]}/{d[:4]}", "composite": comp, "variation": var, "pages": pages,
                    "fichier": f"publications/boc/{nom}", "ko": os.path.getsize(f) // 1024})
    idx.sort(key=lambda e: e["date"][6:] + e["date"][3:5] + e["date"][:2], reverse=True)
    json.dump(idx, open(os.path.join(DOSSIER, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"index.json : {len(idx)} BOC")


if __name__ == "__main__":
    main()
