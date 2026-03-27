"""
Application Streamlit - Simulation de Dérive MOTHY et Trajectoires de Navires.

Supporte :
- Fichiers de dérive MOTHY (rposi .gpx) : waypoints surface/barycentre
- Trajectoires VTS (Histoire .gpx) : trackpoints navires
- Positions ANAIS (.csv) : flotte multi-navires par MMSI
"""

import streamlit as st
from streamlit_folium import st_folium
from datetime import datetime, timedelta, timezone
from parsers import detect_and_parse_file, DriftData, VesselTrack
from map_builder import build_static_map, build_full_trajectory_map, VESSEL_COLORS

st.set_page_config(
    page_title="Dérive & Trajectoires Maritimes",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .file-tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75em;
        font-weight: 600;
        margin-left: 6px;
    }
    .tag-mothy { background: #2196F3; color: white; }
    .tag-vts { background: #4CAF50; color: white; }
    .tag-anais { background: #FF9800; color: white; }
    .legend-item {
        display: flex;
        align-items: center;
        margin: 4px 0;
        font-size: 0.85em;
    }
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
        flex-shrink: 0;
    }
    .info-box {
        background: #1a1d24;
        border: 1px solid #2d3139;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    if 'drift_data' not in st.session_state:
        st.session_state.drift_data = None
    if 'vessel_tracks' not in st.session_state:
        st.session_state.vessel_tracks = []
    if 'all_times' not in st.session_state:
        st.session_state.all_times = []
    if 'time_index' not in st.session_state:
        st.session_state.time_index = 0
    if 'playing' not in st.session_state:
        st.session_state.playing = False
    if 'loaded_files' not in st.session_state:
        st.session_state.loaded_files = set()


def compute_time_axis(drift_data, vessel_tracks, step_minutes=60):
    """
    Calcule un axe temporel commun couvrant toutes les données.
    Utilise en priorité les timesteps MOTHY s'ils existent.
    """
    if drift_data and drift_data.timesteps:
        return drift_data.timesteps

    # Sinon, construire un axe à partir des bornes des trajectoires
    all_times = set()
    min_t = None
    max_t = None

    if drift_data:
        t_min, t_max = drift_data.time_range
        if t_min:
            min_t = t_min if not min_t else min(min_t, t_min)
            max_t = t_max if not max_t else max(max_t, t_max)

    for track in vessel_tracks:
        t_min, t_max = track.time_range
        if t_min:
            min_t = t_min if not min_t else min(min_t, t_min)
            max_t = t_max if not max_t else max(max_t, t_max)

    if min_t and max_t:
        current = min_t
        step = timedelta(minutes=step_minutes)
        while current <= max_t:
            all_times.add(current)
            current += step
        return sorted(all_times)

    return []


def process_uploaded_files(drift_files, trajectory_files):
    """Parse tous les fichiers uploadés et met à jour le state."""
    drift_data = None
    vessel_tracks = []
    
    # Process drift files
    if drift_files:
        for f in drift_files:
            file_key = f"drift_{f.name}_{f.size}"
            content = f.read().decode('utf-8', errors='replace')
            f.seek(0)
            try:
                ftype, data = detect_and_parse_file(content, f.name)
                if ftype == 'mothy':
                    drift_data = data
                elif ftype == 'vessel':
                    # GPX with tracks but uploaded as drift — treat as vessel
                    vessel_tracks.append(data)
                elif ftype == 'fleet':
                    vessel_tracks.extend(data)
            except Exception as e:
                st.error(f"Erreur lors du parsing de {f.name}: {e}")
    
    # Process trajectory files
    if trajectory_files:
        for f in trajectory_files:
            file_key = f"traj_{f.name}_{f.size}"
            content = f.read().decode('utf-8', errors='replace')
            f.seek(0)
            try:
                ftype, data = detect_and_parse_file(content, f.name)
                if ftype == 'vessel':
                    vessel_tracks.append(data)
                elif ftype == 'fleet':
                    vessel_tracks.extend(data)
                elif ftype == 'mothy':
                    # GPX uploaded as trajectory but is actually drift
                    if drift_data is None:
                        drift_data = data
            except Exception as e:
                st.error(f"Erreur lors du parsing de {f.name}: {e}")
    
    return drift_data, vessel_tracks


def main():
    init_session_state()

    # ====== SIDEBAR ======
    with st.sidebar:
        st.markdown("## 📁 Chargement des fichiers")

        st.markdown("""
        <div class="info-box">
        <b>Formats supportés :</b><br>
        • <span class="file-tag tag-mothy">MOTHY</span> Dérive rposi (.gpx)<br>
        • <span class="file-tag tag-vts">VTS</span> Histoire trajectoire (.gpx)<br>
        • <span class="file-tag tag-anais">ANAIS</span> Trails flotte (.csv)
        </div>
        """, unsafe_allow_html=True)

        drift_files = st.file_uploader(
            "Fichier(s) de dérive MOTHY",
            type=['gpx'],
            accept_multiple_files=True,
            key='drift_upload',
            help="Fichier rposi GPX contenant les waypoints de dérive (surface + barycentre)"
        )

        trajectory_files = st.file_uploader(
            "Fichiers de trajectoires navires",
            type=['gpx', 'csv'],
            accept_multiple_files=True,
            key='traj_upload',
            help="Fichiers GPX (VTS/Histoire) ou CSV (ANAIS trails)"
        )

        st.divider()
        st.markdown("## ⚙️ Paramètres")

        show_trails = st.checkbox("Afficher les traînées", value=True)
        trail_hours = st.slider(
            "Durée des traînées (heures)", 
            min_value=1, max_value=48, value=6,
            disabled=not show_trails
        )
        show_barycentre = st.checkbox("Afficher le barycentre", value=True)
        
        step_minutes = st.select_slider(
            "Pas temporel",
            options=[15, 30, 60, 120, 180, 360],
            value=60,
            format_func=lambda x: f"{x} min" if x < 60 else f"{x//60}h{'%02d' % (x%60) if x%60 else ''}"
        )

    # ====== PROCESS FILES ======
    drift_data, vessel_tracks = process_uploaded_files(drift_files, trajectory_files)
    
    has_data = drift_data is not None or len(vessel_tracks) > 0

    # ====== HEADER ======
    st.markdown("# 🌊 Dérive & Trajectoires Maritimes")

    if not has_data:
        st.info(
            "Chargez vos fichiers dans le panneau latéral pour commencer.\n\n"
            "**Fichiers de dérive** : GPX rposi (sortie MOTHY) avec les waypoints de dérive.\n\n"
            "**Fichiers de trajectoires** : GPX Histoire (VTS) ou CSV trails (ANAIS)."
        )
        return

    # ====== DATA SUMMARY ======
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        if drift_data:
            t_min, t_max = drift_data.time_range
            st.metric(
                "Dérive MOTHY",
                f"{len(drift_data.timesteps)} pas de temps",
                f"{len(drift_data.points)} particules"
            )
            if t_min and t_max:
                st.caption(f"🕐 {t_min.strftime('%d/%m/%Y %H:%M')} → {t_max.strftime('%d/%m/%Y %H:%M')} UTC")
    
    with col_info2:
        if vessel_tracks:
            total_pts = sum(len(t.points) for t in vessel_tracks)
            st.metric(
                "Trajectoires navires",
                f"{len(vessel_tracks)} navires",
                f"{total_pts} positions"
            )

    # ====== LEGEND ======
    if vessel_tracks:
        with st.expander("🎨 Légende des navires", expanded=True):
            cols = st.columns(min(len(vessel_tracks), 4))
            for i, track in enumerate(vessel_tracks):
                color = VESSEL_COLORS[i % len(VESSEL_COLORS)]
                t_min, t_max = track.time_range
                time_info = ""
                if t_min and t_max:
                    time_info = f"<br><small>{t_min.strftime('%d/%m %H:%M')} → {t_max.strftime('%d/%m %H:%M')}</small>"
                with cols[i % len(cols)]:
                    st.markdown(
                        f'<div class="legend-item">'
                        f'<div class="legend-dot" style="background:{color};"></div>'
                        f'<span><b>{track.name}</b> ({track.source})'
                        f'{f" — MMSI {track.mmsi}" if track.mmsi else ""}'
                        f'{time_info}</span></div>',
                        unsafe_allow_html=True
                    )

    # ====== TIME AXIS ======
    time_axis = compute_time_axis(drift_data, vessel_tracks, step_minutes)
    
    if not time_axis:
        st.warning("Aucun horodatage trouvé dans les données.")
        # Show full trajectory map
        m = build_full_trajectory_map(drift_data, vessel_tracks, show_barycentre)
        st_folium(m, use_container_width=True, height=600, returned_objects=[])
        return

    # ====== TABS ======
    tab_replay, tab_full = st.tabs(["▶️ Rejeu temporel", "🗺️ Vue complète"])

    with tab_replay:
        # Time slider
        st.markdown("### ⏱️ Navigation temporelle")
        
        time_labels = [t.strftime('%d/%m/%Y %H:%M') for t in time_axis]
        
        time_idx = st.slider(
            "Sélectionner l'instant",
            min_value=0,
            max_value=len(time_axis) - 1,
            value=0,
            format=f"Pas %d / {len(time_axis) - 1}",
            key='time_slider'
        )
        
        current_time = time_axis[time_idx]
        
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.markdown(f"**Début :** {time_axis[0].strftime('%d/%m/%Y %H:%M')} UTC")
        with col_t2:
            st.markdown(f"**Actuel :** `{current_time.strftime('%d/%m/%Y %H:%M')} UTC`")
        with col_t3:
            st.markdown(f"**Fin :** {time_axis[-1].strftime('%d/%m/%Y %H:%M')} UTC")

        # Build map for current time
        m = build_static_map(
            drift_data=drift_data,
            vessel_tracks=vessel_tracks,
            current_time=current_time,
            show_trails=show_trails,
            trail_hours=trail_hours,
            show_barycentre=show_barycentre
        )

        st_folium(m, use_container_width=True, height=600, returned_objects=[])

        # Stats for current timestep
        if drift_data:
            pts = drift_data.get_points_at_time(
                min(drift_data.timesteps, key=lambda t: abs((t - current_time).total_seconds())),
                include_barycentre=False
            )
            st.caption(f"🔵 {len(pts)} particules de surface affichées à cet instant")

    with tab_full:
        st.markdown("### 🗺️ Trajectoires complètes")
        st.caption("Affiche l'intégralité des trajectoires sans filtrage temporel.")

        m_full = build_full_trajectory_map(drift_data, vessel_tracks, show_barycentre)
        st_folium(m_full, use_container_width=True, height=700, returned_objects=[])

    # ====== DATA TABLE ======
    with st.expander("📊 Détails des données", expanded=False):
        if drift_data:
            st.markdown("#### Dérive MOTHY")
            st.markdown(f"- Fichier source : `{drift_data.source_name}`")
            st.markdown(f"- Nombre de pas de temps : {len(drift_data.timesteps)}")
            st.markdown(f"- Nombre total de waypoints : {len(drift_data.points)}")
            if drift_data.timesteps:
                st.markdown(f"- Premier pas : {drift_data.timesteps[0].strftime('%Y-%m-%d %H:%M')} UTC")
                st.markdown(f"- Dernier pas : {drift_data.timesteps[-1].strftime('%Y-%m-%d %H:%M')} UTC")

        if vessel_tracks:
            st.markdown("#### Navires")
            for i, track in enumerate(vessel_tracks):
                t_min, t_max = track.time_range
                time_str = ""
                if t_min and t_max:
                    fmt = "%d/%m %H:%M"
                    time_str = f" — {t_min.strftime(fmt)} → {t_max.strftime(fmt)} UTC"
                mmsi_str = f" — MMSI {track.mmsi}" if track.mmsi else ""
                st.markdown(
                    f"**{i+1}. {track.name}** ({track.source}) — "
                    f"{len(track.points)} points{mmsi_str}{time_str}"
                )


if __name__ == "__main__":
    main()
