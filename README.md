# Dérive & Trajectoires Maritimes

Application Streamlit pour la visualisation de simulations de dérive MOTHY et de trajectoires de navires sur carte interactive (Folium).

## Fonctionnalités

- **Chargement multi-format** : GPX rposi (MOTHY), GPX Histoire (VTS), CSV trails (ANAIS)
- **Détection automatique** du type de fichier (dérive ou trajectoire)
- **Rejeu temporel** : slider pour naviguer dans le temps avec traînées configurables
- **Vue complète** : visualisation de toutes les trajectoires sans filtrage
- **Carte interactive** : Folium avec fond Esri Ocean et OpenStreetMap
- **Légende dynamique** : couleurs par navire, MMSI, plages temporelles
- **Couches activables** : surface, barycentre, navires individuels

## Formats de fichiers supportés

| Format | Source | Extension | Description |
|--------|--------|-----------|-------------|
| rposi GPX | MOTHY | `.gpx` | Waypoints de dérive (surface + barycentre) |
| Histoire GPX | VTS | `.gpx` | Trajectoire d'un navire (trackpoints) |
| Trails CSV | ANAIS | `.csv` | Positions de flotte multi-navires (par MMSI) |

### Structure du fichier MOTHY (rposi)
```xml
<wpt lat="49.8888" lon="-1.1131">
  <name>surface</name>     <!-- 'surface' ou 'barycentre' -->
  <cmt>0000</cmt>          <!-- identifiant du pas de temps -->
  <desc>1155</desc>         <!-- identifiant de la particule -->
  <time>2025-02-11T11:00:00Z</time>
</wpt>
```

### Structure du fichier VTS (Histoire)
```xml
<trk><trkseg>
  <trkpt lat="49.8258" lon="-1.3206">
    <time>2025-02-11T08:16:04Z</time>
  </trkpt>
</trkseg></trk>
```

### Structure du fichier ANAIS (CSV)
```csv
timestamp,mmsi,lon,lat,hdms,sog,cog
2025-02-13T21:31:39,236567000,-0.0818,49.5369,...,13.90,358.30
```

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

```bash
streamlit run app.py
```

1. Charger un fichier de dérive MOTHY (.gpx) dans le panneau latéral
2. Charger un ou plusieurs fichiers de trajectoire (.gpx / .csv)
3. Utiliser le slider pour naviguer dans le temps
4. Ajuster les paramètres (traînées, barycentre, pas temporel)

## Architecture

```
maritime-app/
├── app.py              # Application Streamlit principale
├── parsers.py          # Parsers pour GPX (MOTHY/VTS) et CSV (ANAIS)
├── map_builder.py      # Construction des cartes Folium
├── requirements.txt    # Dépendances Python
└── data/               # Fichiers de données (exemples)
```

## Dépendances

- `streamlit` — interface web
- `streamlit-folium` — intégration carte Folium dans Streamlit
- `folium` — cartes interactives
- `gpxpy` — parsing GPX
- `pandas` — traitement CSV / données tabulaires
