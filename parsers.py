"""
Parsers pour les différents formats de fichiers de données maritimes.

Formats supportés :
- rposi GPX (MOTHY) : fichier de dérive avec waypoints (surface/barycentre)
- Histoire GPX (VTS) : trajectoires de navires avec trackpoints
- ANAIS CSV : positions de flotte avec MMSI multiples
"""

import gpxpy
import pandas as pd
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
import io
import re


@dataclass
class DriftPoint:
    """Un point de dérive MOTHY."""
    lat: float
    lon: float
    time: datetime
    name: str  # 'surface' ou 'barycentre'
    particle_id: str  # desc field
    timestep: str  # cmt field (ex: '0000', '0001')


@dataclass
class TrackPoint:
    """Un point de trajectoire de navire."""
    lat: float
    lon: float
    time: datetime
    sog: Optional[float] = None
    cog: Optional[float] = None


@dataclass
class VesselTrack:
    """Trajectoire complète d'un navire."""
    name: str
    source: str  # 'VTS', 'ANAIS', 'SEG'
    mmsi: Optional[str] = None
    points: list = field(default_factory=list)

    @property
    def time_range(self):
        if not self.points:
            return None, None
        times = [p.time for p in self.points if p.time]
        if not times:
            return None, None
        return min(times), max(times)


@dataclass
class DriftData:
    """Données complètes de dérive MOTHY."""
    source_name: str
    points: list = field(default_factory=list)
    timesteps: list = field(default_factory=list)  # sorted unique timesteps

    @property
    def time_range(self):
        if not self.timesteps:
            return None, None
        return self.timesteps[0], self.timesteps[-1]

    def get_points_at_time(self, t, include_barycentre=True):
        """Retourne les points pour un horodatage donné."""
        result = []
        for p in self.points:
            if p.time == t:
                if include_barycentre or p.name != 'barycentre':
                    result.append(p)
        return result

    def get_barycentre_at_time(self, t):
        """Retourne le barycentre pour un horodatage donné."""
        for p in self.points:
            if p.time == t and p.name == 'barycentre':
                return p
        return None


def parse_mothy_gpx(file_content: str, filename: str = "mothy") -> DriftData:
    """
    Parse un fichier GPX de dérive MOTHY (rposi).
    
    Structure : waypoints <wpt> avec :
    - name : 'surface' ou 'barycentre'
    - cmt : identifiant du pas de temps (ex: '0000')
    - desc : identifiant de la particule
    - time : horodatage
    """
    gpx = gpxpy.parse(file_content)
    drift = DriftData(source_name=filename)
    times_set = set()

    for wpt in gpx.waypoints:
        t = wpt.time
        if t and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        elif t:
            t = t.astimezone(timezone.utc)

        point = DriftPoint(
            lat=wpt.latitude,
            lon=wpt.longitude,
            time=t,
            name=wpt.name or 'surface',
            particle_id=wpt.description or '',
            timestep=wpt.comment or ''
        )
        drift.points.append(point)
        if t:
            times_set.add(t)

    drift.timesteps = sorted(times_set)
    return drift


def parse_histoire_gpx(file_content: str, filename: str = "vessel") -> VesselTrack:
    """
    Parse un fichier GPX VTS (Histoire).
    
    Structure : <trk><trkseg><trkpt> avec lat, lon, time
    """
    gpx = gpxpy.parse(file_content)
    
    # Extraire le nom du navire depuis le nom de fichier
    # Format: NOM-NAVIRE_HistoireYYYYMMDDTHHMMSSZ-N.gpx
    name = filename
    match = re.match(r'^(.+?)_Histoire', filename)
    if match:
        name = match.group(1).replace('-', ' ').replace('_', ' ')

    track = VesselTrack(name=name, source='VTS')

    for trk in gpx.tracks:
        for seg in trk.segments:
            for pt in seg.points:
                t = pt.time
                if t and t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                elif t:
                    t = t.astimezone(timezone.utc)
                track.points.append(TrackPoint(
                    lat=pt.latitude,
                    lon=pt.longitude,
                    time=t
                ))

    # Also parse waypoints (some files may use them)
    for wpt in gpx.waypoints:
        t = wpt.time
        if t and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        elif t:
            t = t.astimezone(timezone.utc)
        track.points.append(TrackPoint(
            lat=wpt.latitude,
            lon=wpt.longitude,
            time=t
        ))

    # Sort by time
    track.points.sort(key=lambda p: p.time if p.time else datetime.min.replace(tzinfo=timezone.utc))
    return track


def parse_anais_csv(file_content: str, filename: str = "anais") -> list:
    """
    Parse un fichier CSV ANAIS (trails de flotte).
    
    Colonnes : timestamp, mmsi, lon, lat, hdms, sog, cog
    Retourne une liste de VesselTrack, un par MMSI.
    """
    df = pd.read_csv(io.StringIO(file_content))

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    tracks = []
    for mmsi, group in df.groupby('mmsi'):
        track = VesselTrack(
            name=f"MMSI {mmsi}",
            source='ANAIS',
            mmsi=str(mmsi)
        )
        for _, row in group.iterrows():
            try:
                t = pd.to_datetime(row['timestamp'])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                else:
                    t = t.astimezone(timezone.utc)
                track.points.append(TrackPoint(
                    lat=float(row['lat']),
                    lon=float(row['lon']),
                    time=t.to_pydatetime(),
                    sog=float(row['sog']) if 'sog' in row and pd.notna(row['sog']) else None,
                    cog=float(row['cog']) if 'cog' in row and pd.notna(row['cog']) else None
                ))
            except Exception:
                continue

        # Sort by time
        track.points.sort(key=lambda p: p.time if p.time else datetime.min.replace(tzinfo=timezone.utc))
        if track.points:
            tracks.append(track)

    return tracks


def detect_and_parse_file(file_content: str, filename: str):
    """
    Détecte automatiquement le type de fichier et le parse.
    
    Retourne un tuple (type, data) :
    - ('mothy', DriftData)
    - ('vessel', VesselTrack)
    - ('fleet', [VesselTrack, ...])
    """
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''

    if ext == 'csv':
        tracks = parse_anais_csv(file_content, filename)
        return ('fleet', tracks)
    elif ext == 'gpx':
        # Distinguish between MOTHY (waypoints only) and VTS (tracks)
        if '<wpt ' in file_content and '<trk>' not in file_content:
            # Pure waypoint file = MOTHY drift
            drift = parse_mothy_gpx(file_content, filename)
            return ('mothy', drift)
        elif '<trk>' in file_content:
            # Track-based = vessel trajectory
            track = parse_histoire_gpx(file_content, filename)
            return ('vessel', track)
        else:
            # Try MOTHY first
            try:
                drift = parse_mothy_gpx(file_content, filename)
                if drift.points:
                    return ('mothy', drift)
            except Exception:
                pass
            track = parse_histoire_gpx(file_content, filename)
            return ('vessel', track)
    else:
        raise ValueError(f"Format de fichier non supporté : {ext}")
