# hbi-cours — Analyse BRVM (hébergement + cours automatiques)

- `index.html` : l'application Analyse BRVM (fichier unique).
- `cours.json` : dernier relevé de cours, écrit toutes les ~10 minutes (séance) par `.github/workflows/cours.yml` via `scripts/fetch_cours.py` (page des cours de la BRVM, différée de 15 min). Format : `FORMAT.md`.
- L'application relit `cours.json` toutes les 5 minutes et met à jour les cours partout.

## Activer le site (GitHub Pages)
1. Le dépôt doit être **public** (Settings, General, Danger Zone, Change visibility).
2. Settings, **Pages**, Source : **Deploy from a branch**, Branch : `main`, dossier `/ (root)`, Save.
3. Adresse du site : `https://horizonbourse12-alt.github.io/hbi-cours/`

## Tester la lecture des cours
Onglet **Actions**, workflow « Cours BRVM », **Run workflow**.
