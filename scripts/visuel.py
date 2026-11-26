#!/usr/bin/env python3
"""Visuel du jour : capture l'affiche « Les opportunités du moment sur le marché » de l'application
(page ?visuel=opportunites) et l'enregistre dans opportunites.png (même adresse chaque jour).
Usage : python3 scripts/visuel.py [URL_BASE]   (défaut http://localhost:8765/)   — nécessite playwright + chromium.
"""
import os, sys
from playwright.sync_api import sync_playwright

racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
AFFICHES = [  # (paramètre, élément capturé, fichier, passer par Menu > Actualités ?)
    ("opportunites", "visuel-opportunites", "opportunites.png", True),
    ("top-cours", "visuel-top-cours", "top-cours.png", False),
    ("top-volume", "visuel-top-volume", "top-volume.png", False),
]
with sync_playwright() as p:
    b = p.chromium.launch()
    for param, ident, fichier, via_menu in AFFICHES:
        try:
            pg = b.new_context(viewport={"width": 700, "height": 1100}, device_scale_factor=2).new_page()
            pg.goto(base + "index.html?visuel=" + param)
            pg.wait_for_timeout(1500)
            champ = pg.query_selector("input")
            if champ:                      # l'application demande un prénom au premier lancement
                champ.fill("Robot"); pg.keyboard.press("Enter"); pg.wait_for_timeout(2500)
            if via_menu:
                pg.get_by_text("Menu", exact=False).first.click(); pg.wait_for_timeout(500)
                pg.get_by_text("Actualités & Pouls du Marché").first.click()
            pg.wait_for_selector("#" + ident, timeout=20000)
            pg.add_style_tag(content="button,[style*='position: fixed']{display:none !important}")   # boutons flottants de l'application
            pg.wait_for_timeout(2500)      # laisse arriver cours.json
            pg.locator("#" + ident).screenshot(path=os.path.join(racine, fichier))
            print(fichier, "écrit")
        except Exception as e:  # noqa: BLE001
            print(fichier, "non généré :", e)
    b.close()
