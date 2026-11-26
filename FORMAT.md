# Format du fichier `cours.json`

Le module de lecture de brvm.org dépose `cours.json` à la racine de ce dépôt (branche principale), à chaque relevé.
Une tâche planifiée le publie dans l'application « Analyse BRVM » (jamais plus d'une fois par relevé).

```json
{
  "date": "26/11/2026",
  "heure": "12h30",
  "provisoire": true,
  "rows": [
    { "s": "SCRC", "veille": 1335, "dernier": 1390, "bas": 1340, "haut": 1435, "volume": 11337, "t": "11:59" },
    { "s": "SICC", "veille": 8400, "dernier": null, "volume": null }
  ]
}
```

- `date` : JJ/MM/AAAA. `heure` : HHhMM (heure du relevé).
- `provisoire` : `true` pendant la séance, `false` pour la clôture officielle.
- `s` : symbole BRVM (ABJC, BBGC, BICB, BICC, BNBC…). Une ligne par société.
- `veille` : cours de la veille (obligatoire). `dernier` : dernier cours (`null` si aucune transaction).
- `volume` : titres échangés depuis l'ouverture. `bas`, `haut`, `t` : facultatifs.
- Un relevé de moins de 30 sociétés est ignoré par l'application.
