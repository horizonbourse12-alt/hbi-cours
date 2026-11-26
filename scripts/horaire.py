#!/usr/bin/env python3
"""Horaires de cotation BRVM (https://www.brvm.org/fr/horaires-de-cotation), heures UTC = Abidjan.
Normal : pré-ouverture 9h00, fixing 9h45, continu jusqu'à 14h00, pré-clôture 14h00-14h30, fixing de clôture 14h30,
dernier cours 14h30-15h00, fermeture/officialisation 15h00 (±60 s).
Veille de jour férié : fermeture à 12h00.
Affiche : "FERIE" (marché fermé aujourd'hui) ou "FIN HHMM FERMETURE_HHMM" (arrêt du robot, heure de fermeture).
Jours fériés : https://www.brvm.org/fr/jours-feries (2026 seulement publié ; fêtes mobiles confirmées par avis).
À COMPLÉTER chaque année.
"""
import datetime as dt

FERIES = {
    "2026-01-01", "2026-03-17", "2026-03-20", "2026-04-06", "2026-05-01", "2026-05-14",
    "2026-05-25", "2026-05-27", "2026-08-07", "2026-08-26", "2026-12-25",
    "2027-01-01",   # Jour de l'an (fixe) ; les autres dates 2027 seront ajoutées quand la BRVM les publiera
}


def horaire(jour):
    if jour.weekday() >= 5 or jour.isoformat() in FERIES:
        return None
    if (jour + dt.timedelta(days=1)).isoformat() in FERIES:
        return ("1210", "1200")      # veille de férié
    return ("1510", "1500")


if __name__ == "__main__":
    h = horaire(dt.datetime.now(dt.timezone.utc).date())
    print("FERIE" if h is None else f"FIN {h[0]} {h[1]}")
