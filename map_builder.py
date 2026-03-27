"""
Construction de la carte Folium pour la visualisation des trajectoires 
et de la dérive MOTHY.
"""

import folium
from datetime import datetime, timedelta, timezone
from parsers import DriftData, VesselTrack, TrackPoint

# Palette de couleurs pour les navires
VESSEL_COLORS = [
    '#e74c3c',  # rouge
    '#2ecc71',  # vert
    '#9b59b6',  # violet
    '#e67e22',  # orange
    '#1abc9c',  # turquoise
    '#f39c12',  # jaune-doré
    '#3498db',  # bleu
    '#e91e63',  # rose
    '#00bcd4',  # cyan
    '#8bc34a',  # vert clair
    '#ff5722',  # rouge profond
    '#607d8b',  # gris-bleu
    '#795548',  # marron
    '#cddc39',  # lime
    '#9e9e9e',  # gris
]

DRIFT_COLOR = '#3498db'       # bleu pour les particules de surface
BARYCENTRE_COLOR = '#e74c3c'  # rouge pour le barycentre


def compute_bounds(drift_data=None, vessel_tracks=None):
    """Calcule les bornes géographiques de toutes les données."""
    all_lats = []
    all_lons = []

    if drift_data:
        for p in drift_data.points:
            all_lats.append(p.lat)
            all_lons.append(p.lon)

    if vessel_tracks:
        for track in vessel_tracks:
            for p in track.points:
                all_lats.append(p.lat)
                all_lons.append(p.lon)

    if not all_lats:
        return None

    padding = 0.05
    return [
        [min(all_lats) - padding, min(all_lons) - padding],
        [max(all_lats) + padding, max(all_lons) + padding]
    ]


def _create_base_map(bounds):
    """Crée une carte Folium de base avec les fonds de carte."""
    if bounds:
        center = [
            (bounds[0][0] + bounds[1][0]) / 2,
            (bounds[0][1] + bounds[1][1]) / 2
        ]
    else:
        center = [49.0, -1.5]

    m = folium.Map(
        location=center,
        zoom_start=10,
    )

    # Fond de carte océan
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
        attr='Esri Ocean',
        name='Esri Ocean',
        overlay=False
    ).add_to(m)

    if bounds:
        m.fit_bounds(bounds)

    return m


def _add_layer_control(m):
    """Ajoute le contrôle de couches de manière compatible."""
    try:
        folium.LayerControl(position='topright', collapsed=False).add_to(m)
    except Exception:
        try:
            folium.LayerControl().add_to(m)
        except Exception:
            pass  # Skip si vraiment incompatible


def build_static_map(drift_data=None, vessel_tracks=None, 
                      current_time=None, show_trails=True,
                      trail_hours=6, show_barycentre=True):
    """
    Construit une carte Folium statique pour un instant donné.
    """
    bounds = compute_bounds(drift_data, vessel_tracks)
    m = _create_base_map(bounds)

    # === Dérive MOTHY ===
    if drift_data and current_time:
        drift_group = folium.FeatureGroup(name='Dérive MOTHY - Surface', show=True)
        barycentre_group = folium.FeatureGroup(name='Dérive MOTHY - Barycentre', show=True)

        # Trouver le timestep le plus proche
        closest_time = min(drift_data.timesteps, 
                          key=lambda t: abs((t - current_time).total_seconds()))

        # Points de surface
        surface_points = drift_data.get_points_at_time(closest_time, include_barycentre=False)
        for p in surface_points:
            folium.CircleMarker(
                location=[p.lat, p.lon],
                radius=3,
                color=DRIFT_COLOR,
                fill=True,
                fill_color=DRIFT_COLOR,
                fill_opacity=0.7,
                weight=1,
                popup=folium.Popup(
                    f"Particule {p.particle_id}<br>Pas: {p.timestep}<br>"
                    f"{p.time.strftime('%Y-%m-%d %H:%M') if p.time else ''}",
                    max_width=200
                ),
            ).add_to(drift_group)

        # Barycentre
        if show_barycentre:
            bary = drift_data.get_barycentre_at_time(closest_time)
            if bary:
                folium.CircleMarker(
                    location=[bary.lat, bary.lon],
                    radius=8,
                    color=BARYCENTRE_COLOR,
                    fill=True,
                    fill_color=BARYCENTRE_COLOR,
                    fill_opacity=0.9,
                    weight=2,
                    popup=folium.Popup(
                        f"Barycentre<br>{bary.time.strftime('%Y-%m-%d %H:%M') if bary.time else ''}",
                        max_width=200
                    ),
                ).add_to(barycentre_group)

        # Traînée du barycentre
        if show_barycentre and show_trails:
            bary_trail = []
            for t in drift_data.timesteps:
                if t <= closest_time:
                    b = drift_data.get_barycentre_at_time(t)
                    if b:
                        bary_trail.append([b.lat, b.lon])
            if len(bary_trail) > 1:
                folium.PolyLine(
                    bary_trail,
                    color=BARYCENTRE_COLOR,
                    weight=2,
                    opacity=0.6,
                    dash_array='5 10',
                ).add_to(barycentre_group)

        drift_group.add_to(m)
        barycentre_group.add_to(m)

    # === Trajectoires des navires ===
    if vessel_tracks:
        for i, track in enumerate(vessel_tracks):
            color = VESSEL_COLORS[i % len(VESSEL_COLORS)]
            vessel_group = folium.FeatureGroup(name=track.name, show=True)

            if current_time:
                trail_start = current_time - timedelta(hours=trail_hours)
                
                trail_points = []
                current_points = []
                for p in track.points:
                    if p.time and trail_start <= p.time <= current_time:
                        trail_points.append(p)
                    if p.time and abs((p.time - current_time).total_seconds()) <= 1800:
                        current_points.append(p)

                # Traînée
                if show_trails and len(trail_points) > 1:
                    coords = [[p.lat, p.lon] for p in trail_points]
                    folium.PolyLine(
                        coords,
                        color=color,
                        weight=3,
                        opacity=0.7,
                    ).add_to(vessel_group)

                # Position actuelle
                if current_points:
                    closest = min(current_points, 
                                 key=lambda p: abs((p.time - current_time).total_seconds()))
                    info_parts = [f"<b>{track.name}</b>", f"Source: {track.source}"]
                    if track.mmsi:
                        info_parts.append(f"MMSI: {track.mmsi}")
                    if closest.time:
                        info_parts.append(f"Position: {closest.time.strftime('%Y-%m-%d %H:%M')}")
                    if closest.sog is not None:
                        info_parts.append(f"SOG: {closest.sog:.1f} kts")
                    if closest.cog is not None:
                        info_parts.append(f"COG: {closest.cog:.1f}&deg;")
                    info = "<br>".join(info_parts)

                    folium.CircleMarker(
                        location=[closest.lat, closest.lon],
                        radius=7,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.9,
                        weight=2,
                        popup=folium.Popup(info, max_width=250),
                        tooltip=track.name,
                    ).add_to(vessel_group)
            else:
                # Mode complet
                if track.points:
                    coords = [[p.lat, p.lon] for p in track.points]
                    if len(coords) > 1:
                        folium.PolyLine(
                            coords,
                            color=color,
                            weight=2,
                            opacity=0.6,
                        ).add_to(vessel_group)
                    # Marqueur début
                    folium.CircleMarker(
                        location=[track.points[0].lat, track.points[0].lon],
                        radius=6,
                        color='green',
                        fill=True,
                        fill_color='green',
                        fill_opacity=0.8,
                        weight=2,
                        popup=folium.Popup(
                            f"{track.name} - Début<br>"
                            f"{track.points[0].time.strftime('%Y-%m-%d %H:%M') if track.points[0].time else ''}",
                            max_width=200
                        ),
                    ).add_to(vessel_group)
                    # Marqueur fin
                    folium.CircleMarker(
                        location=[track.points[-1].lat, track.points[-1].lon],
                        radius=6,
                        color='red',
                        fill=True,
                        fill_color='red',
                        fill_opacity=0.8,
                        weight=2,
                        popup=folium.Popup(
                            f"{track.name} - Fin<br>"
                            f"{track.points[-1].time.strftime('%Y-%m-%d %H:%M') if track.points[-1].time else ''}",
                            max_width=200
                        ),
                    ).add_to(vessel_group)

            vessel_group.add_to(m)

    _add_layer_control(m)
    return m


def build_full_trajectory_map(drift_data=None, vessel_tracks=None, show_barycentre=True):
    """
    Construit une carte montrant les trajectoires complètes (sans filtrage temporel).
    """
    bounds = compute_bounds(drift_data, vessel_tracks)
    m = _create_base_map(bounds)

    # Dérive MOTHY — toutes les positions
    if drift_data and drift_data.timesteps:
        drift_group = folium.FeatureGroup(name='Dérive MOTHY - Toutes positions', show=True)
        barycentre_group = folium.FeatureGroup(name='Dérive MOTHY - Barycentre', show=True)

        last_t = drift_data.timesteps[-1]
        for t in drift_data.timesteps:
            opacity = 0.8 if t == last_t else 0.15
            pts = drift_data.get_points_at_time(t, include_barycentre=False)
            for p in pts:
                folium.CircleMarker(
                    location=[p.lat, p.lon],
                    radius=2 if t != last_t else 4,
                    color=DRIFT_COLOR,
                    fill=True,
                    fill_color=DRIFT_COLOR,
                    fill_opacity=opacity,
                    weight=0.5,
                ).add_to(drift_group)

        if show_barycentre:
            bary_trail = []
            for t in drift_data.timesteps:
                b = drift_data.get_barycentre_at_time(t)
                if b:
                    bary_trail.append([b.lat, b.lon])
                    folium.CircleMarker(
                        location=[b.lat, b.lon],
                        radius=4,
                        color=BARYCENTRE_COLOR,
                        fill=True,
                        fill_color=BARYCENTRE_COLOR,
                        fill_opacity=0.7,
                        weight=1,
                        popup=folium.Popup(
                            f"Barycentre<br>{t.strftime('%Y-%m-%d %H:%M')}",
                            max_width=200
                        ),
                    ).add_to(barycentre_group)
            if len(bary_trail) > 1:
                folium.PolyLine(
                    bary_trail,
                    color=BARYCENTRE_COLOR,
                    weight=2,
                    opacity=0.6,
                    dash_array='5 10',
                ).add_to(barycentre_group)

        drift_group.add_to(m)
        barycentre_group.add_to(m)

    # Trajectoires complètes des navires
    if vessel_tracks:
        for i, track in enumerate(vessel_tracks):
            color = VESSEL_COLORS[i % len(VESSEL_COLORS)]
            vessel_group = folium.FeatureGroup(name=track.name, show=True)

            if track.points:
                coords = [[p.lat, p.lon] for p in track.points]
                if len(coords) > 1:
                    folium.PolyLine(
                        coords,
                        color=color,
                        weight=3,
                        opacity=0.7,
                    ).add_to(vessel_group)

                # Marqueurs début et fin (CircleMarker au lieu de Marker+Icon)
                folium.CircleMarker(
                    location=[track.points[0].lat, track.points[0].lon],
                    radius=6,
                    color='green',
                    fill=True,
                    fill_color='green',
                    fill_opacity=0.8,
                    weight=2,
                    popup=folium.Popup(
                        f"{track.name} - Début<br>"
                        f"{track.points[0].time.strftime('%Y-%m-%d %H:%M') if track.points[0].time else ''}",
                        max_width=200
                    ),
                ).add_to(vessel_group)
                folium.CircleMarker(
                    location=[track.points[-1].lat, track.points[-1].lon],
                    radius=6,
                    color='red',
                    fill=True,
                    fill_color='red',
                    fill_opacity=0.8,
                    weight=2,
                    popup=folium.Popup(
                        f"{track.name} - Fin<br>"
                        f"{track.points[-1].time.strftime('%Y-%m-%d %H:%M') if track.points[-1].time else ''}",
                        max_width=200
                    ),
                ).add_to(vessel_group)

            vessel_group.add_to(m)

    _add_layer_control(m)
    return m
