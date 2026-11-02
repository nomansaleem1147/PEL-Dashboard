# -*- coding: utf-8 -*-
"""PEL Assets Map: three-column, wireframe-aligned Streamlit GIS dashboard."""
from __future__ import annotations

from pathlib import Path
import base64
import html
import hashlib
import json
import re
from io import BytesIO
import shutil
import zipfile
from typing import Any

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st
from folium.plugins import MeasureControl, Draw, MarkerCluster
from streamlit_folium import st_folium

try:
    import mapclassify
except Exception:
    mapclassify = None

APP_TITLE = "PEL ASSETS MAP"
ROOT = Path(__file__).resolve().parent
UPLOAD_DIR, PROCESSED_DIR, ASSET_DIR = ROOT / "uploads", ROOT / "processed", ROOT / "assets"
for directory in (UPLOAD_DIR, PROCESSED_DIR, ASSET_DIR):
    directory.mkdir(parents=True, exist_ok=True)

NAVY, BLUE, GOLD = "#073B70", "#0756B8", "#F2A900"
WHITE, RED, GREEN, GREY = "#FFFFFF", "#E53935", "#20A64A", "#9CA3AF"
PALETTES = {
    "PEL Navy–Gold": ["#073B70", "#0756B8", "#2878B5", "#F2A900", "#FFF0B3"],
    "Blue Gradient": ["#E0F2FE", "#7DD3FC", "#0284C7", "#0756B8", "#073B70"],
    "Traffic Light": ["#20A64A", "#A3D977", "#F2A900", "#F28C28", "#E53935"],
    "Warm Spectrum": ["#FFF7BC", "#FEC44F", "#FE9929", "#EC7014", "#CC4C02"],
    "Viridis": ["#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725"],
    "Plasma": ["#0D0887", "#7E03A8", "#CC4778", "#F89540", "#F0F921"],
    "Inferno": ["#000004", "#57106E", "#BC3754", "#F98E09", "#FCFFA4"],
    "Magma": ["#000004", "#51127C", "#B73779", "#FC8961", "#FCFDBF"],
    "Terrain": ["#006837", "#78C679", "#FFFFBF", "#D9A066", "#8C510A"],
    "Elevation": ["#153B50", "#2D708E", "#56B1A5", "#F6D186", "#A64B2A"],
    "Ocean": ["#081D58", "#225EA8", "#41B6C4", "#A1DAB4", "#FFFFD9"],
    "Grayscale": ["#111111", "#555555", "#888888", "#BBBBBB", "#F5F5F5"],
    "RdYlGn": ["#A50026", "#F46D43", "#FFFFBF", "#A6D96A", "#006837"],
    "Spectral": ["#9E0142", "#F46D43", "#FFFFBF", "#66C2A5", "#5E4FA2"],
}

# Petroleum and GIS point-symbol gallery (Unicode symbols render quickly in Leaflet).
POINT_SYMBOLS = {
    "Oil well": "🛢️", "Exploration well": "🛠️", "Gas well": "🔥", "Dry well": "⚒️",
    "Producing well": "🛢", "Abandoned well": "🚫", "Drilling rig": "🏗️", "Rig location": "⛏️",
    "Mining lease": "⛏", "Exploration block": "⬟", "Petroleum field": "🛢️", "Gas field": "🔥",
    "Pipeline valve": "⚙️", "Pipeline station": "🏭", "Compressor station": "🔩", "Pump station": "🚰",
    "Refinery": "🏭", "Storage tank": "🛢️", "Processing plant": "🏭", "Flare stack": "🔥",
    "Seismic point": "📍", "Seismic shot point": "💥", "Survey point": "🎯", "GPS station": "📡",
    "Benchmark": "📐", "Monitoring station": "📡", "Water well": "💧", "Water point": "💧",
    "Spring": "♨️", "River gauge": "🌊", "Camp": "⛺", "Field office": "🏢",
    "Airport": "✈️", "Helipad": "🚁", "Road junction": "➕", "Bridge": "🌉",
    "Power station": "⚡", "Substation": "🔌", "Telecom tower": "📶", "Warning": "⚠️",
    "Hazard": "☢️", "Fire": "🔥", "Emergency": "🆘", "Hospital": "🏥",
    "School": "🏫", "Village": "🏘️", "City": "🏙️", "Settlement": "🏠",
    "District centre": "🏛️", "Boundary marker": "🚩", "Protected area": "🌳", "Forest": "🌲",
    "Water body": "🌊", "Dam": "🧱", "Canal": "〰️", "Mine": "⛏️",
    "Quarry": "🪨", "Geology site": "🪨", "Landslide": "⛰️", "Flood risk": "🌊",
    "Earthquake": "〰️", "Weather station": "🌦️", "Rain gauge": "🌧️", "Wind station": "💨",
    "Generic point": "●", "Star": "★", "Circle": "●", "Square": "■", "Triangle": "▲",
    "Diamond": "◆", "Flag": "🚩", "Pin": "📍", "Target": "🎯", "Information": "ℹ️",
}
LINE_SYMBOLS = {
    "Solid": None, "Dashed": "8 5", "Dotted": "2 5", "Dash-dot": "8 4 2 4",
    "Long dash": "14 6", "Railway": "10 4 2 4 2 4", "Pipeline": "12 4",
    "Seismic line": "4 3 1 3", "Access road": "6 3", "Boundary": "3 2",
}
POLYGON_SYMBOLS = ["Solid fill", "Transparent fill", "Outline only", "Light fill"]

# Explicit XYZ tile URLs are used for every basemap. This avoids provider-name
# resolution differences between Folium/xyzservices versions.
BASEMAPS = {
    "OpenStreetMap": (
        "OpenStreetMap",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "&copy; OpenStreetMap contributors",
    ),
    "Satellite": (
        "Esri World Imagery",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    ),
    "Terrain": (
        "OpenTopoMap",
        "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        "Map data: &copy; OpenStreetMap contributors, SRTM | Map style: &copy; OpenTopoMap",
    ),
    "Dark": (
        "CARTO Dark Matter",
        "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "&copy; OpenStreetMap contributors &copy; CARTO",
    ),
    "Light": (
        "CARTO Positron",
        "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "&copy; OpenStreetMap contributors &copy; CARTO",
    ),
}
st.set_page_config(page_title=APP_TITLE, page_icon="🗺️", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root{--pel-gold:#FFC73C;--pel-gold-deep:#F2A900;--pel-panel:#FFE699;--pel-panel-edge:#F2C94C;
--pel-navy:#172C51;--pel-orange:#ED7D31;--pel-note:#FFF2CC;--pel-black:#000000}
.stApp{background:#FFFFFF;color:#111}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{display:none}
.block-container{max-width:100%;padding:2.9rem .8rem .8rem}
label,.stMarkdown p{font-size:12px!important}
div[data-testid="stCaptionContainer"]{font-size:11.5px}

/* ---------- header banner ---------- */
.pel-banner{background:linear-gradient(180deg,#FFD25A 0%,#FFC73C 45%,#F2B100 100%);border-radius:6px;padding:12px 14px;
box-shadow:0 3px 6px rgba(0,0,0,.28);margin-bottom:6px}
.pel-banner-in{background:#fff;border-radius:16px;display:grid;grid-template-columns:96px minmax(220px,1fr) 300px;
align-items:center;gap:14px;padding:8px 14px;min-height:74px}
.pel-logo{width:84px;height:60px;object-fit:contain;background:#fff}
.pel-title{font-size:clamp(22px,2.5vw,38px);font-weight:900;color:#111;line-height:1.02;letter-spacing:.2px}
.pel-subtitle{color:#F0A800;font-weight:800;font-size:clamp(12px,1.1vw,16px);font-variant:small-caps;margin-top:3px}
.pel-credit{border:2px solid var(--pel-navy);border-radius:14px;padding:6px 12px;font-size:12.5px;color:#111;line-height:1.25}
.pel-credit .pb{font-weight:900;font-size:12px;text-decoration:underline}
.pel-credit b{display:block;font-weight:800}
@media (max-width:1100px){.pel-banner-in{grid-template-columns:72px 1fr;}.pel-credit{grid-column:1 / -1}}

/* ---------- left yellow panel ---------- */
.st-key-left_panel{background:var(--pel-panel);border:2px solid var(--pel-panel-edge);padding:8px 8px 10px;border-radius:2px}
.st-key-left_panel [data-testid="stVerticalBlock"]{gap:.32rem}
.st-key-layout_slot [data-testid="stVerticalBlock"]{gap:.32rem}

/* ---------- section tabs & boxes ---------- */
.sec-tab{display:block;background:#fff;border:1.5px solid var(--pel-navy);padding:6px 12px;font-weight:800;font-size:14px;
color:#111;margin:4px 0 0;line-height:1.25}
.sec-tab.narrow{display:inline-block;min-width:250px}
[class*="st-key-box_"]{background:#fff;border:1.5px solid var(--pel-navy);padding:9px 11px;border-radius:0}
.st-key-box_open{min-height:150px;display:flex;align-items:center;justify-content:center}
.helper{font-size:10px;font-weight:800;color:#111;border:1.5px solid var(--pel-navy);background:#fff;padding:7px 8px;margin-bottom:6px}
.toc-title{font-weight:800;font-size:12px;margin-bottom:2px}
.gray-help{color:#8a8a8a;font-size:10.5px;line-height:1.45;margin-bottom:6px}
.box-title{color:#111;font-weight:800;font-size:12.5px;margin:2px 0 5px}
[class*="st-key-toc_"]{border:1px solid #c9d1de;padding:4px 6px;background:#fff}

/* ---------- map frame ---------- */
.map-label{font-weight:900;font-size:14px;margin:2px 0 4px;color:#111}
.st-key-map_frame{border:3px solid var(--pel-navy);border-radius:44px;padding:12px;overflow:hidden;background:#fff}
.st-key-map_frame iframe{border-radius:32px}

/* ---------- notes ---------- */
.pel-note{background:var(--pel-note);border:2px solid #E3B93C;border-radius:12px;padding:8px 12px;font-weight:800;
font-size:12.5px;color:#111;margin:6px 0 4px}
.legend-row{display:flex;align-items:center;gap:7px;font-size:11px;margin:4px 0;color:#25384b;overflow-wrap:anywhere}
.legend-swatch{width:17px;height:12px;display:inline-block;border:2px solid;flex-shrink:0}

/* ---------- buttons ---------- */
div[data-testid="stButton"] button,div[data-testid="stDownloadButton"] button{border-radius:3px;font-size:12px;font-weight:800;
padding:.38rem .5rem;border:1px solid var(--pel-navy);background:#fff;color:#111}
div[data-testid="stButton"] button[kind="primary"],div[data-testid="stButton"] button[data-testid="stBaseButton-primary"],
div[data-testid="stDownloadButton"] button[kind="primary"]{
background:linear-gradient(180deg,#2b2b2b 0%,#000 55%,#000 100%);color:#fff;border:1px solid #000;
text-transform:uppercase;letter-spacing:.4px;box-shadow:3px 4px 6px rgba(0,0,0,.45)}
div[data-testid="stButton"] button[kind="primary"] p,div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] p{color:#fff!important;font-weight:900}
div[data-testid="stButton"] button[kind="primary"]:hover{background:#222;border-color:var(--pel-orange);color:#fff}
.st-key-clear_profile_line button{background:linear-gradient(180deg,#FFE08A 0%,#F2B400 100%)!important;color:#000!important;
border:1px solid #C99700!important;text-transform:none;box-shadow:2px 3px 5px rgba(0,0,0,.35)}
.st-key-clear_profile_line button p{color:#000!important;font-weight:900}
.st-key-open_elevation_profile button{padding:1.1rem .6rem!important;font-size:14px!important;line-height:1.5}
/* layer table-of-content select buttons */
[class*="st-key-select_"] button{text-transform:none!important;letter-spacing:0!important;box-shadow:none!important;text-align:left;
background:#fff!important;color:#111!important;border:1px solid var(--pel-navy)!important}
[class*="st-key-select_"] button p{color:#111!important;font-weight:700!important}
[class*="st-key-select_"] button[kind="primary"],[class*="st-key-select_"] button[data-testid="stBaseButton-primary"]{
background:var(--pel-orange)!important;border-color:var(--pel-orange)!important}
[class*="st-key-select_"] button[kind="primary"] p,[class*="st-key-select_"] button[data-testid="stBaseButton-primary"] p{color:#fff!important}

/* ---------- widgets ---------- */
div[data-baseweb="select"]>div,div[data-baseweb="input"],div[data-baseweb="base-input"]{border-radius:2px!important;
border-color:var(--pel-navy)!important;background:#fff!important}
div[data-testid="stFileUploader"] section{padding:.35rem .5rem;border:1px dashed var(--pel-navy);background:#fffdf3}
div[data-testid="stFileUploaderDropzoneInstructions"] small{display:none}
div[data-testid="stFileUploader"] button{padding:.2rem .5rem}
div[data-testid="stDataFrame"]{border:1px solid #c9d1de;border-radius:2px}
div[data-testid="stExpander"]{border:1.5px solid var(--pel-navy);border-radius:0;background:#fff}
div[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"]{background:var(--pel-orange)!important}

</style>
""", unsafe_allow_html=True)

def esc(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    return html.escape(str(value))


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", Path(str(value)).stem).strip("_") or "layer"


def infer_kind(name: str) -> str:
    n = name.lower().replace("_", " ")
    if "well" in n:
        return "Wells"
    if "mining" in n or "lease" in n:
        return "Mining Lease"
    if "explor" in n or "block" in n:
        return "Exploration Blocks"
    return name


def output_name(name: str) -> str:
    kind = infer_kind(name).lower()
    if kind == "wells":
        return "PEL_Wells"
    if kind == "mining lease":
        return "PEL_Mining_Lease"
    if kind == "exploration blocks":
        return "PEL_Exploration_Blocks"
    return "PEL_" + safe_name(name)


def force_2d(geom):
    if geom is None or geom.is_empty:
        return geom
    try:
        from shapely import force_2d as _force_2d
        return _force_2d(geom)
    except Exception:
        try:
            from shapely.ops import transform
            return transform(lambda x, y, z=None: (x, y), geom)
        except Exception:
            return geom


def normalize_gdf(gdf: gpd.GeoDataFrame, layer_name: str = "layer") -> gpd.GeoDataFrame:
    """Normalize a vector layer for reliable display and processing.

    Duplicate attribute names can appear in source DBF files. Make them unique
    before any row-wise GeoDataFrame construction, and keep a valid CRS.
    """
    if gdf is None or not isinstance(gdf, gpd.GeoDataFrame):
        raise ValueError(f"{layer_name}: unsupported or empty vector dataset.")
    if gdf.empty:
        raise ValueError(f"{layer_name}: the vector dataset contains no features.")
    gdf = gdf.copy()

    # Make duplicated attribute names unique while preserving the first/original
    # field name (important for fields such as ET_Operato and ET_Joint_V).
    original_columns = list(gdf.columns)
    used = set()
    unique_columns = []
    counts = {}
    for col in original_columns:
        name = str(col)
        if name not in used:
            unique_name = name
            counts[name] = 1
        else:
            counts[name] = counts.get(name, 1) + 1
            unique_name = f"{name}_{counts[name]}"
            while unique_name in used:
                counts[name] += 1
                unique_name = f"{name}_{counts[name]}"
        used.add(unique_name)
        unique_columns.append(unique_name)
    gdf.columns = unique_columns

    # Geometry column remains present after column-name de-duplication.
    geom_col = gdf.geometry.name
    if gdf.crs is None:
        raise ValueError(f"{layer_name}: coordinate reference system is missing. Include a valid .prj file or define the CRS before loading.")
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[~gdf.geometry.is_empty].copy()
    if gdf.empty:
        raise ValueError(f"{layer_name}: no non-empty geometries remain.")
    try:
        gdf[geom_col] = gdf.geometry.force_2d()
    except Exception:
        # Compatibility fallback for Shapely versions without GeoSeries.force_2d.
        from shapely import force_2d
        gdf[geom_col] = gdf.geometry.apply(lambda geom: force_2d(geom) if geom is not None else None)
    for col in gdf.columns:
        if col == geom_col:
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype("string").fillna("")
    gdf = gdf.to_crs("EPSG:4326")
    # GeoPackage field names are case-insensitive. Do not add ET_Name beside an
    # existing ET_NAME (or similar case-only duplicate): that causes GDAL/OGR
    # to fail with "Error adding field 'ET_Name' to layer" during clipping.
    lookup = {str(c).casefold(): c for c in gdf.columns}
    if "et_name" not in lookup:
        name_col = next((c for c in gdf.columns if c != geom_col and any(t in str(c).casefold() for t in ("name", "asset", "well", "block", "lease", "facility"))), None)
        gdf["ET_Name"] = gdf[name_col].astype("string").fillna("") if name_col else [f"{layer_name} {i+1}" for i in range(len(gdf))]
    # If ET_NAME/et_name already exists, preserve its original field name.
    lookup = {str(c).casefold(): c for c in gdf.columns}
    if "et_status" not in lookup:
        status_col = next((c for c in gdf.columns if c != geom_col and "status" in str(c).casefold()), None)
        gdf["ET_Status"] = gdf[status_col].astype("string").fillna("Not specified") if status_col else "Not specified"
    # If ET_STATUS already exists with different casing, preserve it rather than
    # creating a case-insensitive duplicate.
    lookup = {str(c).casefold(): c for c in gdf.columns}
    if "et_area" not in lookup:
        try:
            polygon_mask = gdf.geometry.geom_type.str.lower().isin(["polygon", "multipolygon"])
            areas = pd.Series(0.0, index=gdf.index)
            if polygon_mask.any():
                areas.loc[polygon_mask] = gdf.loc[polygon_mask].to_crs("EPSG:6933").geometry.area / 1_000_000.0
            gdf["ET_Area"] = areas
        except Exception:
            gdf["ET_Area"] = 0.0
    # If ET_AREA already exists with different casing, preserve it too.
    return gdf.reset_index(drop=True)


def _leaflet_safe_geometry(geom):
    """Return a GeoJSON geometry that Folium/Branca can safely traverse.

    Branca's bounds calculation expects a ``coordinates`` member and does not
    handle GeometryCollection objects. Spatial intersections can create those
    collections (for example, a polygon touching another polygon at an edge).
    For map display, retain the highest-dimensional usable component.
    """
    if geom is None:
        return None
    try:
        if geom.is_empty:
            return None
        geom_type = getattr(geom, "geom_type", "")
        if geom_type == "GeometryCollection":
            parts = [g for g in geom.geoms if g is not None and not g.is_empty]
            # Prefer polygon components, then lines, then points.
            for wanted in ("Polygon", "LineString", "Point"):
                selected = []
                multi_type = {"Polygon": "MultiPolygon",
                              "LineString": "MultiLineString",
                              "Point": "MultiPoint"}[wanted]
                for part in parts:
                    if part.geom_type == wanted:
                        selected.append(part)
                    elif part.geom_type == multi_type:
                        selected.extend(list(part.geoms))
                if selected:
                    from shapely.ops import unary_union
                    try:
                        result = unary_union(selected)
                        if result is not None and not result.is_empty and result.geom_type != "GeometryCollection":
                            return result
                    except Exception:
                        return selected[0]
            return None
        if geom_type not in {
            "Point", "MultiPoint", "LineString", "MultiLineString",
            "Polygon", "MultiPolygon",
        }:
            return None
        return geom
    except Exception:
        return None


def json_safe_geojson(gdf):
    """Serialize only valid, Leaflet-compatible features.

    GeometryCollections and null/empty geometries are normalized or omitted so
    streamlit-folium's map-bounds calculation cannot fail with KeyError:
    'coordinates'.
    """
    if gdf is None or gdf.empty:
        return {"type": "FeatureCollection", "features": []}
    safe = gdf.loc[:, ~gdf.columns.duplicated(keep="first")].copy()
    geometry_col = safe.geometry.name
    safe[geometry_col] = safe.geometry.apply(_leaflet_safe_geometry)
    safe = safe[safe[geometry_col].notna()].copy()
    safe = safe[~safe.geometry.is_empty].copy()
    if safe.empty:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(json.dumps(safe.__geo_interface__, default=str))


def unique_file_path(folder: Path, filename: str) -> Path:
    """Return a non-existing path so uploads/outputs never overwrite prior files."""
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    counter = 2
    while True:
        trial = folder / f"{stem}_{counter}{suffix}"
        if not trial.exists():
            return trial
        counter += 1


def read_vector(path: Path) -> gpd.GeoDataFrame:
    ext = path.suffix.lower()
    if ext == ".kmz":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".kml") and not n.startswith("../")]
            if not names:
                raise ValueError("KMZ archive contains no KML file.")
            extracted = UPLOAD_DIR / f"{safe_name(path.stem)}_from_kmz.kml"
            extracted.write_bytes(archive.read(names[0]))
            path = extracted
            ext = ".kml"
    if ext == ".kml":
        try:
            return gpd.read_file(path, driver="KML")
        except Exception:
            return gpd.read_file(path)
    # Shapefile DBF files can contain duplicate date-like field names. The
    # pyogrio engine emits repeated datetime-key warnings for these datasets;
    # Fiona is a safer first reader for SHP/DBF, with pyogrio as fallback.
    if ext == ".shp":
        try:
            return gpd.read_file(path, engine="fiona")
        except Exception:
            pass
    try:
        return gpd.read_file(path, engine="pyogrio")
    except Exception:
        return gpd.read_file(path)


def raster_layer_from_path(path: Path, display_name: str | None = None) -> dict:
    """Validate a georeferenced raster and create a lightweight layer record."""
    import rasterio
    from rasterio.warp import calculate_default_transform
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError("Raster is not georeferenced: a valid CRS is required.")
        if src.transform is None or src.transform.is_identity or src.width < 1 or src.height < 1:
            raise ValueError("Raster is missing a usable georeferencing transform. Define its CRS and geotransform before loading.")
        if src.count < 1:
            raise ValueError("Raster contains no bands.")
        preview_scale = min(1.0, 1400.0 / max(src.width, src.height))
        preview_width = max(1, int(src.width * preview_scale))
        preview_height = max(1, int(src.height * preview_scale))
        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds,
            dst_width=preview_width, dst_height=preview_height)
        west, south = transform * (0, height)
        east, north = transform * (width, 0)
        bounds = [float(west), float(south), float(east), float(north)]
        band = int(1)
        # Approximate statistics from a small overview sample. Calling GDAL's
        # statistics() on each Streamlit rerun can repeatedly scan large rasters.
        try:
            from rasterio.enums import Resampling
            sample_h = min(src.height, 512)
            sample_w = min(src.width, 512)
            sample = src.read(band, out_shape=(sample_h, sample_w), masked=True,
                              resampling=Resampling.nearest)
            values = np.asarray(sample.compressed(), dtype="float64")
            values = values[np.isfinite(values)]
            if values.size:
                min_value, max_value = float(values.min()), float(values.max())
            else:
                min_value = max_value = None
        except Exception:
            min_value = max_value = None
    if not all(np.isfinite(bounds)) or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError("Raster georeferencing produced invalid map bounds.")
    name = display_name or path.stem
    empty = gpd.GeoDataFrame({"Name": []}, geometry=gpd.GeoSeries([], crs="EPSG:4326"), crs="EPSG:4326")
    return {"name": name, "kind": "raster", "gdf": empty, "source": str(path),
            "raster_path": str(path), "raster_bounds": bounds, "raster_min": min_value,
            "raster_max": max_value, "raster_band": 1}


def raster_png_data(layer: dict, ramp_name: str = "Terrain", opacity: float = 0.75,
                    classification: str = "Continuous Stretch", classes: int = 5) -> tuple[str, list[list[float]]]:
    """Render a georeferenced raster as a reprojected PNG overlay; supports continuous and classified styles."""
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap, BoundaryNorm
    from matplotlib import colors as mpl_colors

    path = Path(layer["raster_path"])
    with rasterio.open(path) as src:
        preview_scale = min(1.0, 1200.0 / max(src.width, src.height))
        preview_width = max(1, int(src.width * preview_scale))
        preview_height = max(1, int(src.height * preview_scale))
        dst_transform, width, height = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds,
            dst_width=preview_width, dst_height=preview_height)
        width, height = max(1, int(width)), max(1, int(height))
        dest = np.full((height, width), np.nan, dtype="float32")
        reproject(source=rasterio.band(src, int(layer.get("raster_band", 1))), destination=dest,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=dst_transform, dst_crs="EPSG:4326", dst_nodata=np.nan,
                  resampling=Resampling.nearest if classification == "Unique Values" else Resampling.bilinear)
        west, south = dst_transform * (0, height)
        east, north = dst_transform * (width, 0)

    finite = dest[np.isfinite(dest)]
    if finite.size == 0:
        raise ValueError("Raster band contains no valid pixels.")
    low, high = np.nanpercentile(finite, [2, 98])
    if not np.isfinite(low) or not np.isfinite(high) or low == high:
        low, high = float(np.nanmin(finite)), float(np.nanmax(finite) + 1e-6)
    palette = PALETTES.get(ramp_name, PALETTES["Terrain"])
    cmap = LinearSegmentedColormap.from_list("pel_raster_ramp", palette)
    norm = None
    mode = classification or "Continuous Stretch"
    if mode in {"Equal Interval", "Quantile"}:
        n = max(2, min(12, int(classes)))
        vals = finite.astype("float64")
        if mode == "Quantile":
            edges = np.unique(np.quantile(vals, np.linspace(0, 1, n + 1)))
        else:
            edges = np.linspace(float(np.nanmin(vals)), float(np.nanmax(vals)), n + 1)
        if len(edges) >= 3:
            cmap = ListedColormap([palette[i % len(palette)] for i in range(len(edges) - 1)])
            norm = BoundaryNorm(edges, cmap.N, clip=True)
    elif mode == "Unique Values":
        unique = np.unique(finite)
        if len(unique) <= 15:
            cmap = ListedColormap([palette[i % len(palette)] for i in range(len(unique))])
            # A listed colormap with integer-like values is useful for categorical rasters.
            if len(unique) > 1:
                edges = np.concatenate(([unique[0] - 0.5 * (unique[1] - unique[0])],
                                        (unique[:-1] + unique[1:]) / 2,
                                        [unique[-1] + 0.5 * (unique[-1] - unique[-2])]))
                norm = BoundaryNorm(edges, cmap.N, clip=True)
    rgba = cmap(norm(dest) if norm is not None else np.clip((dest - low) / (high - low), 0, 1))
    rgba[..., 3] = np.where(np.isfinite(dest), float(opacity), 0.0)
    fig = plt.figure(figsize=(8, 8 * height / max(width, 1)), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(rgba, interpolation="nearest")
    ax.axis("off")
    buf = BytesIO()
    fig.savefig(buf, format="png", transparent=True, dpi=100, bbox_inches=None, pad_inches=0)
    plt.close(fig)
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return uri, [[float(south), float(west)], [float(north), float(east)]]


def clip_raster_by_boundary(raster_name: str, boundary_name: str,
                            feature_indices: list[int] | None = None) -> dict:
    """Clip a georeferenced raster by selected polygon feature(s), preserving CRS and pixel grid."""
    import rasterio
    from rasterio.mask import mask
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    if raster_name not in st.session_state.layers or st.session_state.layers[raster_name].get("kind") != "raster":
        raise ValueError("Choose a valid raster layer to clip.")
    if boundary_name not in st.session_state.layers or st.session_state.layers[boundary_name].get("kind") == "raster":
        raise ValueError("Choose a valid vector polygon boundary layer.")
    boundary_gdf = st.session_state.layers[boundary_name]["gdf"].copy()
    if feature_indices is not None:
        feature_indices = [int(i) for i in feature_indices if 0 <= int(i) < len(boundary_gdf)]
        if not feature_indices:
            raise ValueError("Select at least one boundary feature.")
        boundary_gdf = boundary_gdf.iloc[feature_indices].copy()
    boundary_gdf = boundary_gdf[boundary_gdf.geometry.notna() & ~boundary_gdf.geometry.is_empty]
    boundary_gdf = boundary_gdf[boundary_gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if boundary_gdf.empty:
        raise ValueError("The selected boundary has no valid polygon geometry.")
    raster_path = Path(st.session_state.layers[raster_name]["raster_path"])
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError("Input raster has no CRS.")
        if boundary_gdf.crs is None:
            raise ValueError("Boundary layer has no CRS.")
        boundary_projected = boundary_gdf.to_crs(src.crs)
        geoms = [mapping(g) for g in boundary_projected.geometry if g is not None and not g.is_empty]
        if not geoms:
            raise ValueError("No valid boundary geometry remains after reprojection.")
        try:
            clipped, clipped_transform = mask(src, geoms, crop=True, all_touched=False, filled=False)
        except ValueError as exc:
            raise ValueError("The selected area does not overlap this raster, or lies outside its extent.") from exc
        data = clipped.filled(src.nodata if src.nodata is not None else -9999)
        profile = src.profile.copy()
        profile.update(height=data.shape[1], width=data.shape[2], transform=clipped_transform)
        if src.nodata is None:
            profile["nodata"] = -9999
        output_name = f"Clip_{Path(raster_name).stem}_by_{safe_name(boundary_name)}.tif"
        output_path = unique_file_path(PROCESSED_DIR, output_name)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data)
    return raster_layer_from_path(output_path, Path(output_path).stem)


def load_raster_uploads(files) -> tuple[list[dict], list[str]]:
    layers, errors = [], []
    for file in files or []:
        name = Path(file.name).name
        path = unique_file_path(UPLOAD_DIR, name)
        try:
            path.write_bytes(file.getbuffer())
            layers.append(raster_layer_from_path(path, Path(name).stem))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return layers, errors


def register_new_layers(new_layers: list[dict], replace: bool = False):
    """Add layers without removing prior layers; replace=True is deliberately unused by UI."""
    added = []
    for item in new_layers:
        base = item["name"]
        name = base
        suffix = 2
        while name in st.session_state.layers:
            name = f"{base}_{suffix}"
            suffix += 1
        item = dict(item)
        item["name"] = name
        st.session_state.layers[name] = item
        st.session_state.layer_order.append(name)
        st.session_state.visible[name] = True
        st.session_state.layer_checks[name] = True
        st.session_state.filters[name] = {"field": "(No filter)", "text_mode": "Chosen values", "values": [], "contains": "", "range": (0.0, 1.0), "include_na": False}
        st.session_state.styles[name] = {"mode": "Single Symbol", "field": "", "color": RED, "fill_color": RED,
            "ramp": "PEL Navy–Gold", "palette": PALETTES["PEL Navy–Gold"][:], "classes": 5,
            "raster_ramp": "Terrain", "raster_opacity": 0.75, "raster_classification": "Continuous Stretch", "raster_classes": 5,
            "point_symbol": "Oil well", "point_icon_color": NAVY, "point_icon_size": 24,
            "line_symbol": "Solid", "polygon_symbol": "Solid fill"}
        added.append(name)
    if added:
        st.session_state.selected_layer = added[0]
    return added


def run_raster_analysis(layer_name: str, analysis: str, interval: float = 100.0):
    """Run terrain derivatives from a georeferenced DEM; append results, never replace inputs."""
    import rasterio
    from rasterio.transform import xy
    from scipy.ndimage import gaussian_filter
    source_layer = st.session_state.layers[layer_name]
    if source_layer.get("kind") != "raster":
        raise ValueError("Choose a raster layer (preferably a DEM) for terrain analysis.")
    src_path = Path(source_layer["raster_path"])
    with rasterio.open(src_path) as src:
        arr = src.read(int(source_layer.get("raster_band", 1)), masked=True).astype("float64").filled(np.nan)
        profile = src.profile.copy()
        transform, crs, nodata = src.transform, src.crs, src.nodata
        px_x, px_y = abs(transform.a), abs(transform.e)
    valid = np.isfinite(arr)
    if not valid.any():
        raise ValueError("Selected raster band has no valid numeric pixels.")
    fill = np.where(valid, arr, np.nanmedian(arr[valid]))
    # Convert geographic-degree cell size to approximate metres for terrain derivatives.
    if crs.is_geographic:
        mid_lat = (transform.f + transform.e * arr.shape[0] / 2)
        px_x *= 111320 * max(0.05, np.cos(np.deg2rad(mid_lat)))
        px_y *= 110574
    dx = max(px_x, 1e-6); dy = max(px_y, 1e-6)
    gy, gx = np.gradient(fill, dy, dx)
    if analysis == "Slope":
        result = np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy))).astype("float32")
        out_name = f"Slope_{layer_name}"
    elif analysis == "Aspect":
        result = ((np.degrees(np.arctan2(-gx, gy)) + 360) % 360).astype("float32")
        result[np.sqrt(gx * gx + gy * gy) < 1e-10] = -1
        out_name = f"Aspect_{layer_name}"
    elif analysis == "Hillshade":
        slope = np.arctan(np.sqrt(gx * gx + gy * gy))
        aspect = np.arctan2(-gx, gy)
        az, alt = np.deg2rad(315), np.deg2rad(45)
        result = (255 * (np.cos(alt) * np.cos(slope) + np.sin(alt) * np.sin(slope) * np.cos(az - aspect))).clip(0, 255).astype("float32")
        out_name = f"Hillshade_{layer_name}"
    elif analysis == "Gaussian smooth":
        result = gaussian_filter(fill, sigma=1).astype("float32")
        out_name = f"Smooth_{layer_name}"
    elif analysis == "Contours":
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from shapely.geometry import LineString
        from shapely.affinity import affine_transform
        finite = fill[valid]
        low, high = float(np.nanmin(finite)), float(np.nanmax(finite))
        if not np.isfinite(interval) or interval <= 0:
            raise ValueError("Contour interval must be greater than zero.")
        levels = np.arange(np.ceil(low / interval) * interval, high, interval)
        if len(levels) == 0:
            raise ValueError("No contour levels fall within this raster range. Reduce the contour interval.")
        fig, ax = plt.subplots()
        cs = ax.contour(np.ma.masked_where(~valid, fill), levels=levels)
        lines, values = [], []
        for level, segments in zip(cs.levels, cs.allsegs):
            for verts in segments:
                if len(verts) < 2: continue
                # Contour vertices are in array-index coordinates; shift to pixel centres.
                coords = [transform * (float(col) + 0.5, float(row) + 0.5) for col, row in verts]
                line = LineString(coords)
                if line.is_valid and not line.is_empty:
                    lines.append(line); values.append(float(level))
        plt.close(fig)
        if not lines:
            raise ValueError("No contour lines could be generated for the chosen interval.")
        out_name = f"Contours_{layer_name}"
        contour_gdf = gpd.GeoDataFrame({"elevation": values}, geometry=lines, crs=crs)
        contour_gdf = normalize_gdf(contour_gdf, out_name)
        out_path = unique_file_path(PROCESSED_DIR, f"{safe_name(out_name)}.gpkg")
        contour_gdf.to_file(out_path, layer=safe_name(out_name), driver="GPKG")
        new_layer = {"name": out_name, "kind": "vector", "gdf": contour_gdf, "source": str(out_path)}
        return new_layer
    else:
        raise ValueError(f"Unsupported analysis: {analysis}")
    result[~valid] = np.nan
    out_path = unique_file_path(PROCESSED_DIR, f"{safe_name(out_name)}.tif")
    profile.update(driver="GTiff", count=1, dtype="float32", nodata=-9999.0, compress="deflate")
    out = np.where(np.isfinite(result), result, -9999.0).astype("float32")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out, 1)
    return raster_layer_from_path(out_path, out_name)


def upload_to_layers(files) -> tuple[list[dict], list[str]]:
    layers, errors = [], []
    groups: dict[str, list] = {}
    singles = []
    allowed_shp = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix"}
    for file in files or []:
        ext = Path(file.name).suffix.lower()
        if ext in allowed_shp:
            groups.setdefault(Path(file.name).stem.casefold(), []).append(file)
        elif ext in {".kml", ".kmz", ".geojson", ".json", ".gpkg"}:
            singles.append(file)
    for group in groups.values():
        files_by_ext = {Path(f.name).suffix.lower(): f for f in group}
        if ".shp" not in files_by_ext:
            continue
        shp_file = files_by_ext[".shp"]
        stem = Path(shp_file.name).stem
        missing = [ext for ext in (".shx", ".dbf", ".prj") if ext not in files_by_ext]
        if missing:
            errors.append(f"{stem}: missing required component(s): {', '.join(missing)}.")
            continue
        folder = UPLOAD_DIR / safe_name(stem)
        if folder.exists():
            counter = 2
            while (UPLOAD_DIR / f"{safe_name(stem)}_{counter}").exists():
                counter += 1
            folder = UPLOAD_DIR / f"{safe_name(stem)}_{counter}"
        folder.mkdir(parents=True, exist_ok=True)
        for file in group:
            (folder / Path(file.name).name).write_bytes(file.getbuffer())
        try:
            gdf = normalize_gdf(read_vector(folder / Path(shp_file.name).name), stem)
            layers.append({"name": stem, "gdf": gdf, "source": str(folder / Path(shp_file.name).name)})
        except Exception as exc:
            errors.append(f"{stem}: {exc}")
    for file in singles:
        path = unique_file_path(UPLOAD_DIR, Path(file.name).name)
        path.write_bytes(file.getbuffer())
        try:
            gdf = normalize_gdf(read_vector(path), Path(file.name).stem)
            layers.append({"name": Path(file.name).stem, "gdf": gdf, "source": str(path)})
        except Exception as exc:
            errors.append(f"{file.name}: {exc}")
    return layers, errors


def load_from_upload_folder() -> tuple[list[dict], list[str]]:
    layers, errors = [], []
    supported = {".shp", ".kml", ".kmz", ".geojson", ".json", ".gpkg"}
    for path in sorted(UPLOAD_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in supported:
            continue
        if path.suffix.lower() == ".shp":
            missing = [ext for ext in (".shx", ".dbf", ".prj")
                       if not path.with_suffix(ext).exists()]
            if missing:
                errors.append(f"{path.name}: missing required shapefile component(s): {', '.join(missing)}.")
                continue
        if path.suffix.lower() in {".shp", ".kml", ".kmz", ".geojson", ".json", ".gpkg"}:
            try:
                gdf = normalize_gdf(read_vector(path), path.stem)
                layers.append({"name": path.stem, "gdf": gdf, "source": str(path)})
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
    # Load georeferenced GeoTIFFs alongside vectors when restarting the app.
    for path in sorted(UPLOAD_DIR.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".tif", ".tiff"}:
            try:
                layers.append(raster_layer_from_path(path, path.stem))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
    # Avoid duplicate layer names from nested paths.
    unique, seen = [], set()
    for layer in layers:
        name = layer["name"]
        if name in seen:
            name = f"{name}_{len(seen)+1}"
            layer["name"] = name
        seen.add(name)
        unique.append(layer)
    return unique, errors


def sample_layers() -> list[dict]:
    """Small built-in Pakistan sample used only when uploads/ is empty."""
    from shapely.geometry import Point, Polygon, LineString
    blocks = gpd.GeoDataFrame(
        {"AssetName": ["Sample Exploration Block"], "Operator": ["PEL"], "Status": ["Sample only"]},
        geometry=[Polygon([(67.1, 27.5), (67.8, 27.5), (67.8, 28.0), (67.1, 28.0)])],
        crs="EPSG:4326")
    wells = gpd.GeoDataFrame(
        {"WellName": ["Sample Well 1", "Sample Well 2"], "Operator": ["PEL", "PEL"]},
        geometry=[Point(67.35, 27.68), Point(67.6, 27.82)], crs="EPSG:4326")
    pipelines = gpd.GeoDataFrame(
        {"Name": ["Sample Pipeline"], "Operator": ["PEL"]},
        geometry=[LineString([(67.15, 27.58), (67.45, 27.72), (67.7, 27.9)])], crs="EPSG:4326")
    facilities = gpd.GeoDataFrame(
        {"Facility": ["Sample Facility"], "Operator": ["PEL"]},
        geometry=[Point(67.45, 27.72)], crs="EPSG:4326")
    return [{"name": name, "gdf": normalize_gdf(gdf, name), "source": "built-in sample"}
            for name, gdf in [("Exploration Blocks Sample", blocks), ("Wells Sample", wells),
                              ("Pipelines Sample", pipelines), ("Facilities Sample", facilities)]]


def candidate_text_fields(gdf: gpd.GeoDataFrame) -> list[str]:
    """Return likely PEL ownership fields first, followed by other text fields."""
    priority_tokens = (
        "operator", "operato", "company", "owner", "licence", "license",
        "joint", "venture", "partner", "working_interest", "working interest",
    )
    cols = [
        c for c in gdf.columns
        if c != gdf.geometry.name
        and (pd.api.types.is_object_dtype(gdf[c]) or pd.api.types.is_string_dtype(gdf[c]))
    ]
    preferred = [c for c in cols if any(token in str(c).casefold() for token in priority_tokens)]
    fallback = [c for c in cols if c not in preferred]
    return preferred + fallback


def detect_pel(gdf: gpd.GeoDataFrame, field: str, keyword: str) -> tuple[gpd.GeoDataFrame, list[str]]:
    """Find PEL-related assets using strict whole-word matching.

    Auto-detection searches ownership/operator/licence/joint-venture fields first.
    Other text fields are used only if no priority fields exist, preventing a
    stray PEL mention in an unrelated name/description from selecting OGDCL-only
    or otherwise unrelated records.
    """
    if gdf is None or gdf.empty:
        return gdf.copy() if gdf is not None else gpd.GeoDataFrame(), []

    if field and field != "(Auto-detect)" and field in gdf.columns:
        fields = [field]
    else:
        all_candidates = candidate_text_fields(gdf)
        priority_tokens = (
            "operator", "operato", "company", "owner", "licence", "license",
            "joint", "venture", "partner", "working_interest", "working interest",
        )
        priority_fields = [
            c for c in all_candidates
            if any(token in str(c).casefold() for token in priority_tokens)
        ]
        fields = priority_fields if priority_fields else all_candidates

    term = (keyword or "PEL").strip() or "PEL"
    if term.casefold() in {"pel", "petroleum exploration"}:
        pattern = r"(?<![A-Za-z0-9])PEL(?![A-Za-z0-9])|petroleum\s+exploration"
    else:
        # Whole phrase/word matching avoids partial matches such as PEL inside
        # unrelated identifiers. Escaped user input is treated literally.
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"

    # Reset index and use positional boolean arrays so duplicate source indices
    # cannot cause pandas alignment/reindex errors.
    source = gdf.copy().reset_index(drop=True)
    mask = np.zeros(len(source), dtype=bool)
    searched = []
    for col in fields:
        searched.append(str(col))
        values = source[col].astype("string").fillna("")
        mask |= values.str.contains(pattern, case=False, na=False, regex=True).to_numpy(dtype=bool)
    result = source.loc[mask].copy().reset_index(drop=True)
    return result, searched


def filtered_gdf(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    field = config.get("field", "(No filter)")
    if field == "(No filter)" or field not in gdf.columns:
        return gdf.copy()
    series = gdf[field]
    if pd.api.types.is_numeric_dtype(series):
        values = pd.to_numeric(series, errors="coerce")
        low, high = config.get("range", (float(values.min()), float(values.max())))
        return gdf.loc[values.between(low, high, inclusive="both") | values.isna() & config.get("include_na", False)].copy()
    mode = config.get("text_mode", "Chosen values")
    text = series.astype("string").fillna("(No data)")
    if mode == "Contains text":
        term = config.get("contains", "").strip()
        return gdf.loc[text.str.contains(re.escape(term), case=False, na=False) if term else pd.Series(True, index=gdf.index)].copy()
    selected = config.get("values", [])
    if not selected:
        return gdf.iloc[0:0].copy()
    return gdf.loc[text.isin(selected)].copy()


def popup_html(row, layer_name: str) -> str:
    """Build a compact PEL popup so large/wide DBF rows do not freeze Leaflet."""
    def field_value(target, aliases=()):
        wanted = {target.casefold(), *(str(alias).casefold() for alias in aliases)}
        for col in row.index:
            if str(col).casefold() in wanted:
                value = row[col]
                if value is not None and not pd.isna(value) and str(value).strip() and str(value).strip().casefold() not in {"nan", "none"}:
                    return value
        return None

    name_value = field_value("ET_Name", ("NAME", "FEATURE_NAME", "ASSET_NAME", "WELL_NAME", "BLOCK_NAME", "LEASE_NAME"))
    status_value = field_value("ET_Status", ("STATUS",))
    area_value = field_value("ET_Area", ("AREA",))
    title = str(name_value).strip() if name_value is not None else layer_name
    try:
        area_display = f"{float(area_value):,.2f} sq km"
    except (TypeError, ValueError):
        area_display = "Not available"

    summary = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:8px;background:#f3f7fc">'
        f'<div style="background:white;border:1px solid #d6e2ef;border-left:4px solid {GOLD};padding:7px;border-radius:5px"><small style="color:#62758b">FEATURE NAME</small><div style="font-weight:bold;color:{NAVY}">{esc(title)}</div></div>'
        f'<div style="background:white;border:1px solid #d6e2ef;border-left:4px solid #16a34a;padding:7px;border-radius:5px"><small style="color:#62758b">AREA</small><div style="font-weight:bold;color:{NAVY}">{esc(area_display)}</div></div>'
        f'<div style="grid-column:1/-1;background:white;border:1px solid #d6e2ef;border-left:4px solid {BLUE};padding:7px;border-radius:5px"><small style="color:#62758b">STATUS</small><div style="font-weight:bold;color:{NAVY}">{esc(status_value if status_value is not None else "Not specified")}</div></div></div>'
    )
    # Avoid embedding unbounded DBF text into every Leaflet popup. This is only
    # the map popup; the full attribute table remains available in the dashboard.
    rows = []
    shown = 0
    total = sum(1 for col in row.index if str(col).casefold() != "geometry")
    for col, value in row.items():
        if str(col).casefold() == "geometry":
            continue
        if shown >= 12:
            break
        text_value = "" if value is None else str(value)
        if len(text_value) > 160:
            text_value = text_value[:157] + "..."
        rows.append(f'<tr><th style="text-align:left;padding:5px;background:#f2f6fb;border-bottom:1px solid #dce5ef">{esc(col)}</th><td style="padding:5px;border-bottom:1px solid #dce5ef">{esc(text_value)}</td></tr>')
        shown += 1
    extra_note = f'<div style="padding:5px;color:#62758b;font-size:10px">Showing {shown} of {total} attributes. Full attributes remain in the dashboard table.</div>' if total > shown else ""
    return (f'<div style="font-family:Arial;max-height:340px;overflow:auto;min-width:250px;max-width:440px">'
            f'<div style="background:linear-gradient(100deg,{NAVY},{BLUE});color:white;padding:10px;border-bottom:4px solid {GOLD}"><b style="font-size:10px;color:#ffe18a">PETROLEUM EXPLORATION (PVT) LIMITED</b><br><span style="font-size:17px;font-weight:bold">{esc(title)}</span><br>Feature information</div>{summary}'
            f'<div style="font-weight:bold;color:{NAVY};padding:7px 5px">Attributes</div><table style="width:100%;border-collapse:collapse;font-size:12px">{"".join(rows)}</table>{extra_note}'
            f'<div style="background:#fff7df;color:{NAVY};padding:8px;border-left:4px solid {GOLD};font-size:11px"><b>Prepared by Nouman Saleem</b> · GIS Specialist</div></div>')


def class_info(gdf: gpd.GeoDataFrame, style: dict) -> dict:
    """Return class labels and colours once; shared by map and legend."""
    mode = style.get("mode", "Single Symbol")
    color = style.get("fill_color", style.get("color", RED))
    palette = style.get("palette", PALETTES["PEL Navy–Gold"])
    class_colors = style.get("class_colors", {})
    field = style.get("field", "")
    if mode == "Single Symbol" or field not in gdf.columns:
        return {"mode": "Single Symbol", "color": color, "classes": []}
    series = gdf[field]
    if mode == "Unique Values":
        vals = series.fillna("(No data)").astype(str)
        unique = vals.value_counts(dropna=False).index.tolist()
        shown = unique[:20]
        entries = [{"label": val, "color": class_colors.get(val, palette[i % len(palette)]), "value": val} for i, val in enumerate(shown)]
        if len(unique) > 20:
            entries.append({"label": "Other", "color": class_colors.get("Other", GREY), "values": unique[20:]})
        return {"mode": mode, "field": field, "classes": entries, "color": color}
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return {"mode": "Single Symbol", "color": color, "classes": []}
    n_classes = min(max(2, int(style.get("classes", 5))), int(valid.nunique()))
    if n_classes < 2:
        return {"mode": "Single Symbol", "color": color, "classes": []}
    method = {"Equal Interval": "equal", "Quantile": "quantiles", "Natural Breaks": "natural"}.get(mode, "quantiles")
    try:
        if method == "natural" and mapclassify is not None:
            classifier = mapclassify.NaturalBreaks(valid.to_numpy(), k=n_classes)
            bins = np.asarray(classifier.bins, dtype=float)
        elif method == "equal":
            bins = np.linspace(float(valid.min()), float(valid.max()), n_classes + 1)[1:]
        else:
            bins = np.unique(np.quantile(valid.to_numpy(), np.linspace(0, 1, n_classes + 1)[1:]))
        bins = np.unique(bins)
        if len(bins) < 1:
            raise ValueError("No class breaks")
    except Exception:
        bins = np.unique(np.quantile(valid.to_numpy(), np.linspace(0, 1, n_classes + 1)[1:]))
    low = float(valid.min())
    edges = [low] + [float(x) for x in bins if x > low]
    if len(edges) == 1:
        return {"mode": "Single Symbol", "color": color, "classes": []}
    entries = []
    for i, upper in enumerate(edges[1:]):
        lower = edges[i]
        label = f"{lower:,.3f}".rstrip("0").rstrip(".") + " - " + f"{upper:,.3f}".rstrip("0").rstrip(".")
        entries.append({"label": label, "color": class_colors.get(label, palette[i % len(palette)]),
                        "lower": lower, "upper": upper, "last": i == len(edges[1:]) - 1})
    return {"mode": mode, "field": field, "classes": entries, "color": color}


def style_for_value(value, info: dict) -> str:
    mode = info.get("mode", "Single Symbol")
    if mode == "Single Symbol":
        return info.get("color", RED)
    if mode == "Unique Values":
        text = "(No data)" if pd.isna(value) else str(value)
        for entry in info["classes"]:
            if entry["label"] == text or (entry.get("label") == "Other" and text in entry.get("values", [])):
                return entry["color"]
        return GREY
    try:
        number = float(value)
    except (TypeError, ValueError):
        return GREY
    for entry in info["classes"]:
        if number <= entry["upper"]:
            return entry["color"]
    return info["classes"][-1]["color"] if info["classes"] else info.get("color", RED)


def add_layer_to_map(m, name, gdf, style, filtered):
    """Add a layer without repeatedly copying its full GeoDataFrame per feature."""
    layer_record = st.session_state.layers.get(name, {})
    if layer_record.get("kind") == "raster":
        try:
            image_uri, image_bounds = raster_png_data(
                layer_record, style.get("raster_ramp", "Terrain"),
                style.get("raster_opacity", 0.75),
                style.get("raster_classification", "Continuous Stretch"),
                int(style.get("raster_classes", 5)))
            folium.raster_layers.ImageOverlay(
                image=image_uri, bounds=image_bounds, name=name,
                opacity=float(style.get("raster_opacity", 0.75)),
                interactive=True, cross_origin=False, zindex=2).add_to(m)
        except Exception as exc:
            st.session_state.messages.append(f"Raster layer '{name}' could not be rendered: {exc}")
        return
    if gdf is None or gdf.empty:
        return

    from shapely.geometry import mapping
    info = class_info(gdf, style)
    field = info.get("field", "")
    group = folium.FeatureGroup(name=name, show=True)
    # Deduplicate columns once. Previously the whole GeoDataFrame was copied for
    # every feature, making large/wide DBF layers extremely slow to render.
    data = gdf.loc[:, ~gdf.columns.duplicated(keep="first")]
    geom_col = data.geometry.name
    # Thousands of separate Leaflet markers can block the browser main thread.
    # Cluster point features and enable chunked loading so the basemap stays
    # responsive while markers are added in batches.
    has_points = any(
        geom is not None and not geom.is_empty and "point" in geom.geom_type.lower()
        for geom in data.geometry
    )
    point_cluster = None
    if has_points:
        point_cluster = MarkerCluster(
            name=f"{name} point cluster",
            options={
                "chunkedLoading": True,
                "chunkInterval": 100,
                "chunkDelay": 25,
                "removeOutsideVisibleBounds": True,
                "spiderfyOnMaxZoom": True,
                "showCoverageOnHover": False,
                "maxClusterRadius": 55,
            },
        ).add_to(group)
    for row_pos in range(len(data)):
        row = data.iloc[row_pos]
        geom = row[geom_col]
        if geom is None or geom.is_empty:
            continue
        value = row[field] if field in row.index else None
        color = style_for_value(value, info)
        outline_color = style.get("outline_color", NAVY)
        fill_opacity = float(style.get("fill_opacity", 0.30))
        stroke_size = float(style.get("size", 2.2))
        popup = folium.Popup(popup_html(row, name), max_width=460, parse_html=False)

        if "point" in geom.geom_type.lower():
            symbol_label = style.get("point_symbol", "Generic point")
            glyph = POINT_SYMBOLS.get(symbol_label, "●")
            icon_color = style.get("point_icon_color", color)
            icon_px = int(style.get("point_icon_size", max(18, int(stroke_size * 8))))
            html_icon = (f'<div style="font-size:{icon_px}px;line-height:{icon_px}px;color:{icon_color};'
                         f'text-shadow:-1px -1px 0 white,1px -1px 0 white,-1px 1px 0 white,1px 1px 0 white;'
                         f'text-align:center;white-space:nowrap">{html.escape(glyph)}</div>')
            points = [geom] if geom.geom_type == "Point" else list(geom.geoms)
            for point in points:
                folium.Marker(
                    location=[point.y, point.x],
                    icon=folium.DivIcon(html=html_icon,
                        icon_size=(icon_px + 4, icon_px + 4),
                        icon_anchor=((icon_px + 4)//2, (icon_px + 4)//2)),
                    popup=popup, tooltip=f"{name} — {symbol_label}").add_to(point_cluster or group)
        else:
            safe_geom = _leaflet_safe_geometry(geom)
            if safe_geom is None:
                continue
            # Build a tiny feature directly from the geometry. Do not make a
            # one-row GeoDataFrame or serialize every DBF field for every shape.
            feature = {"type": "Feature", "properties": {}, "geometry": mapping(safe_geom)}
            line_dash = LINE_SYMBOLS.get(style.get("line_symbol", "Solid"))
            polygon_mode = style.get("polygon_symbol", "Solid fill")
            this_fill_opacity = (0.0 if polygon_mode in {"Transparent fill", "Outline only"}
                                 else min(fill_opacity, .18) if polygon_mode == "Light fill"
                                 else fill_opacity)
            folium.GeoJson(
                feature,
                style_function=lambda feature, c=color, o=outline_color, w=stroke_size, fo=this_fill_opacity, dash=line_dash: {
                    "color": o, "weight": w, "fillColor": c, "fillOpacity": fo,
                    **({"dashArray": dash} if dash else {})},
                highlight_function=lambda feature: {"weight": 4, "color": GOLD, "fillOpacity": .42},
                popup=popup, tooltip=f"{name} — click for details").add_to(group)
    group.add_to(m)


def _profile_line_coords(feature):
    """Extract WGS84 lon/lat vertices from a GeoJSON LineString feature."""
    if not isinstance(feature, dict):
        return None
    geom = feature.get("geometry", feature)
    if not isinstance(geom, dict) or geom.get("type") != "LineString":
        return None
    coords = geom.get("coordinates") or []
    cleaned = []
    for item in coords:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                lon, lat = float(item[0]), float(item[1])
                if np.isfinite(lon) and np.isfinite(lat):
                    cleaned.append((lon, lat))
            except (TypeError, ValueError):
                pass
    return cleaned if len(cleaned) >= 2 else None


def _densify_profile_line(coords, spacing_m=30.0, max_samples=1200):
    """Densify a drawn WGS84 line in a local UTM CRS with metre-based spacing."""
    from shapely.geometry import LineString
    from pyproj import CRS, Transformer
    line_wgs = LineString(coords)
    lon0, lat0 = line_wgs.centroid.x, line_wgs.centroid.y
    zone = max(1, min(60, int((lon0 + 180) // 6) + 1))
    utm_epsg = (32600 if lat0 >= 0 else 32700) + zone
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
    line_utm = LineString([to_utm.transform(x, y) for x, y in coords])
    if line_utm.length <= 0:
        raise ValueError("The drawn line has zero length.")
    count = int(np.ceil(line_utm.length / max(1.0, float(spacing_m)))) + 1
    count = max(2, min(int(max_samples), count))
    distances = np.linspace(0.0, float(line_utm.length), count)
    points_utm = [line_utm.interpolate(float(d)) for d in distances]
    points_wgs = [to_wgs.transform(pt.x, pt.y) for pt in points_utm]
    return line_utm, distances, points_utm, points_wgs, f"EPSG:{utm_epsg}"


@st.cache_data(ttl=86400, show_spinner=False)
def _query_public_srtm30m(locations: tuple[str, ...]):
    """Cached query to the public OpenTopoData SRTM 30 m elevation service."""
    import requests
    url = "https://api.opentopodata.org/v1/srtm30m"
    response = requests.post(url, data={"locations": "|".join(locations), "interpolation": "bilinear"}, timeout=18)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK":
        raise RuntimeError(payload.get("error", "Elevation service returned no data."))
    return [r.get("elevation") for r in payload.get("results", [])]


def calculate_elevation_profile(coords, raster_name=None, local_vertical_unit="Meters"):
    """Sample a drawn line from a local georeferenced DEM; use public SRTM 30 m API as fallback."""
    import rasterio
    from pyproj import Transformer
    local_dem_available = bool(raster_name and raster_name in st.session_state.layers
                               and st.session_state.layers[raster_name].get("kind") == "raster"
                               and Path(st.session_state.layers[raster_name].get("raster_path", "")).exists())
    # Local DEM: sample at ~30 m up to 1,200 samples. Online service: keep to
    # one 100-location request so the public API remains fast and rate-limit-safe.
    line_utm, distances, points_utm, points_wgs, profile_crs = _densify_profile_line(coords, 30.0, 1200 if local_dem_available else 100)
    elevations = None
    source_label = ""
    if raster_name and raster_name in st.session_state.layers:
        record = st.session_state.layers[raster_name]
        if record.get("kind") == "raster" and Path(record.get("raster_path", "")).exists():
            with rasterio.open(record["raster_path"]) as src:
                if src.crs is None:
                    raise ValueError("The selected DEM has no CRS.")
                transformer = Transformer.from_crs(profile_crs, src.crs, always_xy=True)
                sample_xy = [transformer.transform(pt.x, pt.y) for pt in points_utm]
                band = int(record.get("raster_band", 1))
                raw_samples = list(src.sample(sample_xy, indexes=band, masked=True))
                values = []
                for sample in raw_samples:
                    cell = sample[0]
                    if np.ma.is_masked(cell):
                        values.append(np.nan)
                    else:
                        try:
                            value = float(cell)
                            values.append(value if np.isfinite(value) and (src.nodata is None or not np.isclose(value, src.nodata)) else np.nan)
                        except (TypeError, ValueError):
                            values.append(np.nan)
                elevations = np.asarray(values, dtype="float64")
                source_label = f"Local raster: {raster_name}"
    if elevations is None or not np.isfinite(elevations).any():
        # Public OpenTopoData ALOS dataset (nominal 30 m). Requests are batched to
        # 100 locations and cached by URL; if offline, report clearly rather than invent values.
        try:
            import requests
            import time
            locs = [f"{lat:.6f},{lon:.6f}" for lon, lat in points_wgs]
            url = "https://api.opentopodata.org/v1/srtm30m"
            response = requests.post(url, data={"locations": "|".join(locs), "interpolation": "bilinear"}, timeout=18)
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "OK":
                raise RuntimeError(payload.get("error", "Elevation service returned no data."))
            samples = [r.get("elevation") for r in payload.get("results", [])]
            elevations = np.asarray([np.nan if v is None else float(v) for v in samples], dtype="float64")
            source_label = "OpenTopoData SRTM 30 m (USGS)"
        except Exception as exc:
            if elevations is None:
                raise RuntimeError(f"Could not sample the selected DEM and the public SRTM 30 m service is unavailable: {exc}. Upload/select a local georeferenced DEM or check internet access.") from exc
    if source_label.startswith("Local raster:") and str(local_vertical_unit).lower().startswith("feet"):
        elevations = elevations * 0.3048
        source_label += " (converted from feet to metres)"
    valid = np.isfinite(elevations)
    if valid.sum() < 2:
        raise ValueError("Fewer than two valid elevation samples were found along this line. Check DEM coverage and nodata areas.")
    # Fill only short internal gaps for a continuous profile display; preserve original validity mask in table.
    series = pd.Series(elevations, dtype="float64")
    filled = series.interpolate(limit_direction="both").to_numpy()
    df = pd.DataFrame({"Distance (km)": distances / 1000.0,
                       "Elevation (m)": filled,
                       "Valid DEM sample": valid})
    stats = {"minimum": float(np.nanmin(elevations)), "maximum": float(np.nanmax(elevations)),
             "mean": float(np.nanmean(elevations)), "valid_count": int(valid.sum()),
             "sample_count": int(len(elevations)), "length_km": float(line_utm.length / 1000.0),
             "source": source_label}
    return df, stats


@st.dialog("Interactive Elevation Profile", width="large")
def show_elevation_profile_dialog(profile_df, profile_stats):
    """Show the interactive gradient elevation chart and profile statistics in a modal window."""
    import plotly.graph_objects as go
    from matplotlib.colors import LinearSegmentedColormap, to_hex
    ramp = PALETTES["Terrain"]
    cmap = LinearSegmentedColormap.from_list("pel_profile_gradient", ramp)
    x = profile_df["Distance (km)"].to_numpy()
    y = profile_df["Elevation (m)"].to_numpy()
    fig = go.Figure()
    # Draw a gradient with at most 99 line segments for responsive rendering;
    # retain all sampled points in the interactive hover layer and CSV export.
    segment_indices = np.unique(np.linspace(0, len(x) - 1, min(100, len(x))).astype(int))
    for j in range(len(segment_indices) - 1):
        i0, i1 = int(segment_indices[j]), int(segment_indices[j + 1])
        seg_y = y[i0:i1 + 1]
        col = to_hex(cmap(float(np.clip((np.nanmean(seg_y) - np.nanmin(y)) /
                                      max(np.nanmax(y)-np.nanmin(y), 1e-9), 0, 1))))
        fig.add_trace(go.Scatter(x=x[i0:i1 + 1], y=seg_y, mode="lines",
                                 line={"color": col, "width": 3}, showlegend=False,
                                 hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name="Elevation",
                             marker={"size": 5, "color": y, "colorscale": [[0, ramp[0]], [0.25, ramp[1]], [0.5, ramp[2]], [0.75, ramp[3]], [1, ramp[4]]],
                                      "showscale": True, "colorbar": {"title": "m"}},
                             customdata=profile_df[["Valid DEM sample"]].astype(str).to_numpy(),
                             hovertemplate="Distance: %{x:.3f} km<br>Elevation: %{y:.2f} m<br>Valid DEM sample: %{customdata[0]}<extra></extra>"))
    fig.update_layout(height=440, margin={"l": 15, "r": 20, "t": 20, "b": 20},
                      xaxis_title="Distance along line (km)", yaxis_title="Elevation (m)",
                      hovermode="closest", template="plotly_white")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
    cols = st.columns(4)
    cols[0].metric("Minimum elevation", f"{profile_stats['minimum']:.2f} m")
    cols[1].metric("Mean elevation", f"{profile_stats['mean']:.2f} m")
    cols[2].metric("Maximum elevation", f"{profile_stats['maximum']:.2f} m")
    cols[3].metric("Profile length", f"{profile_stats['length_km']:.2f} km")
    st.caption(f"Source: {profile_stats['source']} · {profile_stats['valid_count']}/{profile_stats['sample_count']} valid samples · elevations in metres")
    st.download_button("Download profile CSV", profile_df.to_csv(index=False).encode("utf-8"),
                       file_name="PEL_Elevation_Profile.csv", mime="text/csv", use_container_width=True)
    if st.button("Close profile window", key="close_elevation_profile_dialog", use_container_width=True):
        st.session_state.elevation_profile_dialog_open = False
        st.rerun()


def logo_markup():
    candidates = [ASSET_DIR / "PEL_Logo.png", ASSET_DIR / "PEL_Logo.jpg",
                  ASSET_DIR / "PEL_Logo.jpeg", ASSET_DIR / "PEL_Logo.webp"]
    for path in candidates:
        if path.exists():
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/webp"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f'<img class="pel-logo" src="data:{mime};base64,{encoded}" alt="PEL Logo">'
    return '<div style="width:108px;height:62px;border:1px dashed #b8c7d9;display:flex;align-items:center;justify-content:center;color:#60758a">Logo</div>'


# --- Manual-only layer session state.
# Never scan uploads/ or processed/ on startup, and never insert built-in sample data.
# A versioned reset clears any layers that may have been auto-loaded by an older app run.
if st.session_state.get("_manual_layers_only_version") != 1:
    st.session_state.layers = {}
    st.session_state.layer_order = []
    st.session_state.selected_layer = None
    st.session_state.visible = {}
    st.session_state.filters = {}
    st.session_state.styles = {}
    st.session_state.messages = []
    st.session_state.startup_errors = []
    st.session_state.startup_sample = False
    # Clear any previously selected uploader values so every layer must be chosen by the user.
    st.session_state.pop("vector_files", None)
    st.session_state.pop("raster_files", None)
    st.session_state["_manual_layers_only_version"] = 1
# Ensure style defaults migrate for existing session layers and raster/vector styles
for name in st.session_state.layer_order:
    st.session_state.filters.setdefault(name, {"field": "(No filter)", "text_mode": "Chosen values", "values": [], "contains": "", "range": (0.0, 1.0), "include_na": False})
    st.session_state.styles.setdefault(name, {"mode": "Single Symbol", "field": "", "color": RED, "fill_color": RED, "ramp": "PEL Navy–Gold", "palette": PALETTES["PEL Navy–Gold"][:], "classes": 5, "raster_ramp": "Terrain", "raster_opacity": 0.75, "raster_classification": "Continuous Stretch", "raster_classes": 5, "point_symbol": "Oil well", "point_icon_color": NAVY, "point_icon_size": 24, "line_symbol": "Solid", "polygon_symbol": "Solid fill"})
    st.session_state.styles[name].setdefault("point_symbol", "Oil well")
    st.session_state.styles[name].setdefault("point_icon_color", NAVY)
    st.session_state.styles[name].setdefault("point_icon_size", 24)
    st.session_state.styles[name].setdefault("line_symbol", "Solid")
    st.session_state.styles[name].setdefault("polygon_symbol", "Solid fill")
if "basemap" not in st.session_state:
    st.session_state.basemap = "OpenStreetMap"
if "layer_checks" not in st.session_state:
    st.session_state.layer_checks = dict(st.session_state.visible)

# Synchronize checkbox widget keys only at the start of a rerun, before the
# corresponding widgets are instantiated. This avoids StreamlitWidgetAlreadyInstantiatedError.
pending_visibility = st.session_state.pop("pending_visibility_sync", None)
if pending_visibility:
    for layer_name, is_visible in pending_visibility.items():
        st.session_state.visible[layer_name] = bool(is_visible)
        st.session_state.layer_checks[layer_name] = bool(is_visible)
        st.session_state[f"vis_{safe_name(layer_name)}"] = bool(is_visible)


def add_message(message: str):
    st.session_state.messages.append(message)


def select_layer(name: str):
    st.session_state.selected_layer = name


def delete_layer(layer_name: str):
    """Delete a layer and its associated settings."""
    if layer_name not in st.session_state.layers:
        return
    st.session_state.layers.pop(layer_name, None)
    st.session_state.layer_order = [n for n in st.session_state.layer_order if n != layer_name]
    for state_key in ("visible", "filters", "styles", "layer_checks"):
        st.session_state.get(state_key, {}).pop(layer_name, None)
    if st.session_state.get("selected_layer") == layer_name:
        st.session_state.selected_layer = st.session_state.layer_order[0] if st.session_state.layer_order else None
    st.session_state.messages.append(f"Deleted layer: {layer_name}")


def rename_layer(old_name: str, new_name: str):
    """Rename a layer while preserving its data, style, visibility and filter."""
    new_name = str(new_name).strip()
    if old_name not in st.session_state.layers:
        st.session_state.messages.append("The layer to rename no longer exists.")
        return False
    if not new_name:
        st.session_state.messages.append("Enter a non-empty layer name.")
        return False
    if new_name == old_name:
        st.session_state.messages.append("The layer name is unchanged.")
        return False
    if new_name in st.session_state.layers:
        st.session_state.messages.append(f"A layer named '{new_name}' already exists. Choose another name.")
        return False
    st.session_state.layers[new_name] = st.session_state.layers.pop(old_name)
    st.session_state.layers[new_name]["name"] = new_name
    st.session_state.layer_order = [new_name if n == old_name else n for n in st.session_state.layer_order]
    for key in ("visible", "filters", "styles", "layer_checks"):
        mapping = st.session_state.get(key, {})
        if old_name in mapping:
            mapping[new_name] = mapping.pop(old_name)
    if st.session_state.get("selected_layer") == old_name:
        st.session_state.selected_layer = new_name
    if st.session_state.get("zoom_to_layer") == old_name:
        st.session_state.zoom_to_layer = new_name
    selected_map = st.session_state.get("map_selected_feature") or {}
    if selected_map.get("layer") == old_name:
        selected_map["layer"] = new_name
        if selected_map.get("label"):
            selected_map["label"] = selected_map["label"].replace(old_name, new_name, 1)
        st.session_state.map_selected_feature = selected_map
    st.session_state.messages.append(f"Renamed layer '{old_name}' to '{new_name}'.")
    return True


def clear_layers():
    st.session_state.layers = {}
    st.session_state.layer_order = []
    st.session_state.selected_layer = None
    st.session_state.visible = {}
    st.session_state.filters = {}
    st.session_state.styles = {}
    st.session_state.layer_checks = {}
    st.session_state.messages.append("All layers cleared.")


def clip_selected_sources():
    created, reports = [], []
    keyword = st.session_state.get("clip_keyword", "PEL") or "PEL"
    chosen_sources = st.session_state.get("clip_input_layers", []) or []
    source_names = [name for name in st.session_state.layer_order
                    if name in chosen_sources
                    and st.session_state.layers[name].get("kind") != "raster"]
    if not source_names:
        st.session_state.messages.append("Select at least one source layer in Clip Assets.")
        return
    field_choice = st.session_state.get("clip_field", "(Auto-detect)")
    for source_name in source_names:
        source = st.session_state.layers[source_name]["gdf"]
        field = field_choice if field_choice != "(Auto-detect)" and field_choice in source.columns else "(Auto-detect)"
        result, searched = detect_pel(source, field, keyword)
        reports.append(f"{source_name}: {len(result)} of {len(source)} features matched; searched fields: {', '.join(searched) if searched else 'none'}.")
        if result.empty:
            continue
        name = output_name(source_name)
        base_name = name
        suffix = 2
        while name in st.session_state.layers:
            name = f"{base_name}_{suffix}"
            suffix += 1
        path = unique_file_path(PROCESSED_DIR, f"{safe_name(name)}.gpkg")
        try:
            result.to_file(path, layer=safe_name(name), driver="GPKG", engine="pyogrio")
        except Exception:
            try:
                result.to_file(path, layer=safe_name(name), driver="GPKG")
            except Exception as exc:
                reports.append(f"Could not save {name}: {exc}")
                continue
        st.session_state.layers[name] = {"name": name, "gdf": result, "source": str(path)}
        if name not in st.session_state.layer_order:
            st.session_state.layer_order.append(name)
        st.session_state.filters.setdefault(name, {"field": "(No filter)", "text_mode": "Chosen values", "values": [], "contains": "", "range": (0.0, 1.0), "include_na": False})
        old_style = st.session_state.styles.get(source_name, {})
        st.session_state.styles[name] = {**old_style, "mode": "Single Symbol", "field": "", "color": old_style.get("color", RED)}
        created.append(name)
    if created:
        # Keep every existing layer and its current visibility; new outputs are visible.
        for name in created:
            st.session_state.visible[name] = True
            st.session_state.layer_checks[name] = True
        st.session_state.pending_visibility_sync = {n: True for n in created}
        st.session_state.selected_layer = created[0]
        st.session_state.messages.append("Created PEL layers; all source layers were retained: " + ", ".join(created))
    else:
        st.session_state.messages.extend(reports)
        st.session_state.messages.append("No PEL matches found. Check the match field and keyword.")
    st.session_state.messages.extend(reports)


def clip_layers_by_boundary(source_names: list[str], boundary_name: str, boundary_feature_indices: list[int] | None = None):
    """ArcGIS-style spatial Clip: intersect selected input layers with a polygon layer."""
    reports, created = [], []
    if not source_names:
        st.session_state.messages.append("Select at least one input layer to clip.")
        return
    if not boundary_name or boundary_name not in st.session_state.layers:
        st.session_state.messages.append("Choose a valid polygon clip layer.")
        return

    boundary = st.session_state.layers[boundary_name]["gdf"]
    if boundary_feature_indices is not None:
        valid_indices = [int(i) for i in boundary_feature_indices if 0 <= int(i) < len(boundary)]
        if not valid_indices:
            st.session_state.messages.append("Select at least one feature from the clip boundary layer.")
            return
        boundary = boundary.iloc[valid_indices].copy()
    if boundary.empty:
        st.session_state.messages.append(f"Clip layer {boundary_name} is empty.")
        return
    try:
        clip_mask = boundary[boundary.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
        if clip_mask.empty:
            st.session_state.messages.append(
                f"{boundary_name} contains no polygon geometry. Select a polygon layer as the clip boundary."
            )
            return
        clip_mask = clip_mask[["geometry"]].dissolve()
    except Exception as exc:
        st.session_state.messages.append(f"Could not prepare clip boundary {boundary_name}: {exc}")
        return

    for source_name in source_names:
        if source_name not in st.session_state.layers:
            continue
        source_gdf = st.session_state.layers[source_name]["gdf"]
        if source_gdf.empty:
            reports.append(f"{source_name}: skipped because it is empty.")
            continue
        try:
            # Both datasets are normalized to EPSG:4326; use GeoPandas' robust
            # overlay clip and retain only non-empty intersections.
            # ArcGIS-style Clip preserves the input layer's geometry dimension.
            # This avoids mixed point/line artifacts where polygons touch only
            # along the clip boundary or at vertices.
            clipped = gpd.clip(source_gdf, clip_mask, keep_geom_type=True)
            clipped = clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty].copy()
            if not clipped.empty:
                source_types = set(source_gdf.geometry.geom_type.dropna().tolist())
                if source_types & {"Polygon", "MultiPolygon"}:
                    cleaned = clipped.geometry.apply(_leaflet_safe_geometry)
                    clipped = clipped.loc[cleaned.notna()].copy()
                    clipped.geometry = cleaned.loc[cleaned.notna()]
                clipped = normalize_gdf(clipped, source_name) if not clipped.empty else clipped
        except Exception as exc:
            reports.append(f"{source_name}: clip failed — {exc}")
            continue
        if clipped.empty:
            reports.append(f"{source_name}: no features intersect the selected clip area.")
            continue

        output_base = f"Clip_{safe_name(source_name)}_by_{safe_name(boundary_name)}"
        output_name_value = output_base
        suffix = 2
        while output_name_value in st.session_state.layers:
            output_name_value = f"{output_base}_{suffix}"
            suffix += 1
        output_path = unique_file_path(PROCESSED_DIR, f"{safe_name(output_name_value)}.gpkg")
        try:
            try:
                clipped.to_file(output_path, layer=safe_name(output_name_value), driver="GPKG", engine="pyogrio")
            except Exception:
                clipped.to_file(output_path, layer=safe_name(output_name_value), driver="GPKG")
        except Exception as exc:
            reports.append(f"{output_name_value}: could not save GeoPackage — {exc}")
            continue

        st.session_state.layers[output_name_value] = {
            "name": output_name_value, "gdf": clipped, "source": str(output_path)
        }
        if output_name_value not in st.session_state.layer_order:
            st.session_state.layer_order.append(output_name_value)
        st.session_state.filters.setdefault(
            output_name_value,
            {"field": "(No filter)", "text_mode": "Chosen values", "values": [],
             "contains": "", "range": (0.0, 1.0), "include_na": False}
        )
        parent_style = st.session_state.styles.get(source_name, {})
        st.session_state.styles[output_name_value] = {
            **parent_style, "class_colors": dict(parent_style.get("class_colors", {}))
        }
        created.append(output_name_value)
        reports.append(f"{source_name}: clipped {len(clipped)} feature(s) to {boundary_name}.")

    if created:
        # Spatial clip outputs are additive; never hide or delete source/other layers.
        for layer_name in created:
            st.session_state.visible[layer_name] = True
            st.session_state.layer_checks[layer_name] = True
        st.session_state.pending_visibility_sync = {n: True for n in created}
        st.session_state.selected_layer = created[0]
        st.session_state.messages.append("Spatial clip created; all source layers were retained: " + ", ".join(created))
    st.session_state.messages.extend(reports)




def raster_class_legend_entries(raster_record: dict, style: dict, max_sample_size: int = 512):
    """Return legend entries and a data range for the selected raster classification.

    Sampling is downscaled to avoid loading very large rasters into memory just to
    draw the dashboard legend. Class ranges are derived from valid pixel values.
    """
    import rasterio
    from rasterio.enums import Resampling
    from matplotlib.colors import LinearSegmentedColormap

    path = Path(raster_record.get("raster_path", ""))
    if not path.exists():
        return [], None, None
    band = int(raster_record.get("raster_band", 1))
    with rasterio.open(path) as src:
        out_h = min(max_sample_size, src.height)
        out_w = min(max_sample_size, src.width)
        sampled = src.read(
            band, out_shape=(out_h, out_w), masked=True,
            resampling=Resampling.nearest
        )
        vals = np.asarray(sampled.compressed(), dtype="float64")
        nodata = src.nodata
    vals = vals[np.isfinite(vals)]
    if nodata is not None:
        vals = vals[vals != nodata]
    if vals.size == 0:
        return [], None, None

    minimum, maximum = float(np.min(vals)), float(np.max(vals))
    mode = style.get("raster_classification", "Continuous Stretch")
    n_classes = max(2, min(12, int(style.get("raster_classes", 5))))
    palette = PALETTES.get(style.get("raster_ramp", "Terrain"), PALETTES["Terrain"])
    entries = []
    if mode == "Equal Interval":
        edges = np.linspace(minimum, maximum if maximum > minimum else minimum + 1e-9, n_classes + 1)
        for i in range(len(edges) - 1):
            entries.append({
                "label": f"{edges[i]:,.3f} – {edges[i + 1]:,.3f}",
                "color": palette[i % len(palette)]
            })
    elif mode == "Quantile":
        edges = np.unique(np.quantile(vals, np.linspace(0, 1, n_classes + 1)))
        if len(edges) < 2:
            edges = np.array([minimum, maximum if maximum > minimum else minimum + 1e-9])
        for i in range(len(edges) - 1):
            entries.append({
                "label": f"{edges[i]:,.3f} – {edges[i + 1]:,.3f}",
                "color": palette[i % len(palette)]
            })
    elif mode == "Unique Values":
        unique, counts = np.unique(vals, return_counts=True)
        if len(unique) > 12:
            # Show the 12 most common categories when a raster has many unique values.
            chosen = np.argsort(counts)[-12:]
            unique = np.sort(unique[chosen])
        for i, value in enumerate(unique):
            entries.append({
                "label": f"{value:,.3f}" if not float(value).is_integer() else f"{int(value):,}",
                "color": palette[i % len(palette)]
            })
    return entries, minimum, maximum


def make_print_layout(visible_names, filtered_layers, classifications, title, dpi, image_format,
                      show_north=True, show_scalebar=True, show_legend=True, show_frame=True):
    """Create a print-ready map with undistorted geography, perimeter coordinates and a side legend."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap, BoundaryNorm

    names = []
    plot_layers = {}
    for n in visible_names:
        if n not in st.session_state.layers:
            continue
        rec = st.session_state.layers[n]
        if rec.get("kind") == "raster":
            if Path(rec.get("raster_path", "")).exists():
                names.append(n)
        elif n in filtered_layers and filtered_layers[n] is not None and not filtered_layers[n].empty:
            gdf = filtered_layers[n]
            # Keep all layers in a common geographic CRS for the export. This prevents
            # mixing projected vector coordinates with WGS84 raster extents.
            try:
                if getattr(gdf, "crs", None) is not None and str(gdf.crs).upper() not in {
                    "EPSG:4326", "OGC:CRS84"
                }:
                    gdf = gdf.to_crs("EPSG:4326")
            except Exception as exc:
                raise ValueError(f"Vector layer '{n}' could not be transformed to WGS84 for export: {exc}") from exc
            plot_layers[n] = gdf
            if not gdf.empty:
                names.append(n)

    if not names:
        raise ValueError("No visible non-empty vector or raster layers are available. Turn on a layer and try again.")

    bounds_list = []
    for name in names:
        rec = st.session_state.layers[name]
        if rec.get("kind") == "raster":
            b = rec.get("raster_bounds")
            if b and len(b) == 4 and np.isfinite(np.asarray(b, dtype=float)).all():
                bounds_list.append(np.asarray(b, dtype=float))
        else:
            b = np.asarray(plot_layers[name].total_bounds, dtype=float)
            if np.isfinite(b).all() and b[0] < b[2] and b[1] < b[3]:
                bounds_list.append(b)
    if not bounds_list:
        raise ValueError("Visible layers do not have a valid map extent.")
    all_bounds = np.array(bounds_list, dtype=float)
    bounds = np.array([np.nanmin(all_bounds[:, 0]), np.nanmin(all_bounds[:, 1]),
                       np.nanmax(all_bounds[:, 2]), np.nanmax(all_bounds[:, 3])])
    if not np.isfinite(bounds).all() or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError("The visible layers do not have a valid map extent.")

    # Wide landscape page reserves a dedicated right-side legend panel, like a GIS print layout.
    fig = plt.figure(figsize=(14, 9), facecolor="white")
    ax = fig.add_axes([0.085, 0.135, 0.655, 0.735])
    dx = max(bounds[2] - bounds[0], 1e-6)
    dy = max(bounds[3] - bounds[1], 1e-6)
    pad_x, pad_y = dx * 0.06, dy * 0.06
    ax.set_xlim(bounds[0] - pad_x, bounds[2] + pad_x)
    ax.set_ylim(bounds[1] - pad_y, bounds[3] + pad_y)
    ax.set_facecolor("#F8FAFC")
    handles, labels = [], []

    # Draw raster layers first so vector boundaries remain visible.
    for layer_name in names:
        rec = st.session_state.layers[layer_name]
        if rec.get("kind") != "raster":
            continue
        style = st.session_state.styles.get(layer_name, {})
        try:
            with rasterio.open(rec["raster_path"]) as src:
                scale = min(1.0, 1800.0 / max(src.width, src.height))
                width, height = max(1, int(src.width * scale)), max(1, int(src.height * scale))
                dst_transform, dst_w, dst_h = calculate_default_transform(
                    src.crs, "EPSG:4326", src.width, src.height, *src.bounds,
                    dst_width=width, dst_height=height)
                arr = np.full((max(1, dst_h), max(1, dst_w)), np.nan, dtype="float32")
                reproject(source=rasterio.band(src, int(rec.get("raster_band", 1))), destination=arr,
                          src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                          dst_transform=dst_transform, dst_crs="EPSG:4326", dst_nodata=np.nan,
                          resampling=Resampling.nearest)
                west, south = dst_transform * (0, arr.shape[0])
                east, north = dst_transform * (arr.shape[1], 0)

            palette = PALETTES.get(style.get("raster_ramp", "Terrain"), PALETTES["Terrain"])
            cmap = LinearSegmentedColormap.from_list("pel_layout_" + safe_name(layer_name), palette)
            finite = arr[np.isfinite(arr)]
            norm = None
            mode = style.get("raster_classification", "Continuous Stretch")
            class_edges = None
            unique_values = None
            if finite.size:
                data_min, data_max = float(np.nanmin(finite)), float(np.nanmax(finite))
                lo, hi = np.nanpercentile(finite, [2, 98])
                if hi <= lo:
                    lo, hi = data_min, data_max if data_max > data_min else data_min + 1e-6

                if mode in {"Equal Interval", "Quantile"}:
                    nclass = max(2, min(12, int(style.get("raster_classes", 5))))
                    if mode == "Quantile":
                        class_edges = np.unique(np.quantile(finite, np.linspace(0, 1, nclass + 1)))
                    else:
                        class_edges = np.linspace(data_min, data_max if data_max > data_min else data_min + 1e-6,
                                                  nclass + 1)
                    if len(class_edges) >= 2:
                        class_colors = [palette[min(len(palette)-1, int(i * len(palette) / (len(class_edges)-1)))]
                                        for i in range(len(class_edges) - 1)]
                        cmap = ListedColormap(class_colors)
                        norm = BoundaryNorm(class_edges, cmap.N, clip=True)
                elif mode == "Unique Values":
                    unique_values = np.unique(finite)
                    if 1 < len(unique_values) <= 12:
                        class_colors = [palette[min(len(palette)-1, int(i * len(palette) / len(unique_values)))]
                                        for i in range(len(unique_values))]
                        cmap = ListedColormap(class_colors)
                        mid_edges = (unique_values[:-1] + unique_values[1:]) / 2
                        class_edges = np.concatenate((
                            [unique_values[0] - (mid_edges[0] - unique_values[0])],
                            mid_edges,
                            [unique_values[-1] + (unique_values[-1] - mid_edges[-1])]
                        ))
                        norm = BoundaryNorm(class_edges, cmap.N, clip=True)

                # Use geographic aspect correction so a degree of longitude is not treated
                # as the same ground distance as a degree of latitude.
                ax.imshow(arr, extent=[west, east, south, north], origin="upper", cmap=cmap,
                          norm=norm, vmin=None if norm is not None else lo,
                          vmax=None if norm is not None else hi,
                          alpha=float(style.get("raster_opacity", 0.75)),
                          interpolation="nearest", zorder=1)

                if mode in {"Equal Interval", "Quantile"} and class_edges is not None and len(class_edges) >= 2:
                    for i in range(len(class_edges) - 1):
                        color_hex = cmap.colors[i]
                        label = f"{class_edges[i]:,.3f} – {class_edges[i+1]:,.3f}"
                        handles.append(Patch(facecolor=color_hex, edgecolor=NAVY,
                                             label=f"{layer_name}: {label}"))
                        labels.append(f"{layer_name}: {label}")
                elif mode == "Unique Values" and unique_values is not None and len(unique_values) <= 12:
                    for i, value in enumerate(unique_values):
                        color_hex = cmap.colors[i] if hasattr(cmap, "colors") else palette[i % len(palette)]
                        label = f"{value:,.3f}" if not float(value).is_integer() else f"{int(value):,}"
                        handles.append(Patch(facecolor=color_hex, edgecolor=NAVY,
                                             label=f"{layer_name}: {label}"))
                        labels.append(f"{layer_name}: {label}")
                else:
                    handles.append(Patch(facecolor=palette[len(palette)//2], edgecolor=NAVY,
                                         label=f"{layer_name}: {data_min:,.3f} – {data_max:,.3f}"))
                    labels.append(f"{layer_name}: {data_min:,.3f} – {data_max:,.3f}")
        except Exception as exc:
            raise ValueError(f"Raster layer '{layer_name}' could not be added to the map layout: {exc}") from exc

    # Draw vectors in the same WGS84 coordinate space as the raster layers.
    for layer_name in names:
        rec = st.session_state.layers[layer_name]
        if rec.get("kind") == "raster":
            continue
        gdf = plot_layers[layer_name]
        style = st.session_state.styles.get(layer_name, {})
        info = classifications.get(layer_name, class_info(gdf, style))
        field = info.get("field", "")
        colours = [style_for_value(row.get(field), info)
                   if info.get("mode") != "Single Symbol" else info.get("color", style.get("fill_color", RED))
                   for _, row in gdf.iterrows()]
        edge = style.get("outline_color", NAVY)
        linewidth = max(0.35, float(style.get("size", 1.5)))
        alpha = min(1.0, max(0.05, float(style.get("fill_opacity", 0.45))))
        try:
            gdf.plot(ax=ax, color=colours, edgecolor=edge, linewidth=linewidth,
                     alpha=alpha, markersize=max(8, linewidth * 12), zorder=3)
        except Exception:
            for geom_type in gdf.geometry.geom_type.dropna().unique():
                idx = np.where(gdf.geometry.geom_type.to_numpy() == geom_type)[0]
                part = gdf.iloc[idx]
                part.plot(ax=ax, color=[colours[i] for i in idx], edgecolor=edge,
                          linewidth=linewidth, alpha=alpha, markersize=max(8, linewidth * 12), zorder=3)
        if info.get("mode") == "Single Symbol" or not info.get("classes"):
            handles.append(Patch(facecolor=style.get("fill_color", info.get("color", RED)),
                                 edgecolor=edge, label=layer_name))
            labels.append(layer_name)
        else:
            for entry in info.get("classes", []):
                handles.append(Patch(facecolor=entry["color"], edgecolor=edge,
                                     label=f"{layer_name}: {entry['label']}"))
                labels.append(f"{layer_name}: {entry['label']}")

    ax.grid(False)  # perimeter coordinates only; no internal grid lines
    ax.tick_params(axis="both", which="both", direction="out", top=show_frame, right=show_frame,
                   labeltop=show_frame, labelright=show_frame, labelsize=8, colors=NAVY,
                   length=4 if show_frame else 0, pad=5)
    ax.xaxis.set_major_locator(plt.MaxNLocator(6))
    ax.yaxis.set_major_locator(plt.MaxNLocator(6))
    ax.set_xlabel("Longitude" if show_frame else "", color=NAVY, labelpad=9, fontweight="bold")
    ax.set_ylabel("Latitude" if show_frame else "", color=NAVY, labelpad=9, fontweight="bold")
    for spine in ax.spines.values():
        spine.set_edgecolor(NAVY if show_frame else "#FFFFFF")
        spine.set_linewidth(1.4 if show_frame else 0.0)

    # Correct geographic aspect at the centre latitude. Matplotlib aspect is y-unit/x-unit.
    center_lat = float((bounds[1] + bounds[3]) / 2.0)
    lon_scale = max(0.15, abs(float(np.cos(np.deg2rad(center_lat)))))
    ax.set_aspect(1.0 / lon_scale, adjustable="box")

    # Clear title band: intentionally no horizontal gold divider, avoiding overlap with top ticks.
    fig.text(0.405, 0.965, title.strip() or "PEL ASSETS MAP", ha="center", va="top",
             fontsize=20, fontweight="bold", color=NAVY)
    fig.text(0.405, 0.927, "Petroleum Exploration (Pvt) Limited | Pakistan Asset Viewer",
             ha="center", va="top", fontsize=10, color=BLUE)

    if show_north:
        ax.annotate("N", xy=(0.94, 0.94), xytext=(0.94, 0.80), xycoords="axes fraction",
                    textcoords="axes fraction", ha="center", va="center", color=NAVY,
                    fontsize=13, fontweight="bold",
                    arrowprops=dict(arrowstyle="-|>", color=GOLD, lw=2.0))

    mid_lat = (ax.get_ylim()[0] + ax.get_ylim()[1]) / 2
    map_width_km = abs(ax.get_xlim()[1] - ax.get_xlim()[0]) * 111.32 * max(0.1, np.cos(np.deg2rad(mid_lat)))
    scale_km = 1 if map_width_km < 25 else 5 if map_width_km < 100 else 10 if map_width_km < 250 else 25 if map_width_km < 600 else 50 if map_width_km < 1200 else 100
    scale_deg = scale_km / (111.32 * max(0.1, np.cos(np.deg2rad(mid_lat))))
    x0 = ax.get_xlim()[0] + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.04
    y0 = ax.get_ylim()[0] + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.045
    if show_scalebar:
        ax.plot([x0, x0 + scale_deg], [y0, y0], color=NAVY, linewidth=4, solid_capstyle="butt", zorder=8)
        ax.plot([x0, x0], [y0 - dy * 0.006, y0 + dy * 0.006], color=NAVY, linewidth=1.4, zorder=8)
        ax.plot([x0 + scale_deg, x0 + scale_deg], [y0 - dy * 0.006, y0 + dy * 0.006], color=NAVY, linewidth=1.4, zorder=8)
        ax.text(x0, y0 + dy * 0.02, f"{scale_km} km", fontsize=8, color=NAVY,
                ha="left", va="bottom", bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=2))

    # Dedicated right-hand legend panel, matching the user's marked placement.
    if handles and show_legend:
        fig.legend(handles=handles, loc="center left", bbox_to_anchor=(0.765, 0.49),
                   ncol=1, fontsize=7.2, frameon=True, facecolor="white", edgecolor=GOLD,
                   labelspacing=0.7, borderpad=0.8, handlelength=1.6, handletextpad=0.6)

    fig.text(0.88, 0.035, "Prepared by\nNouman Saleem\nGIS Specialist / Exploration Dpt",
             ha="center", va="bottom", fontsize=8, color=NAVY,
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF7DF", edgecolor=GOLD))
    buffer = BytesIO()
    fmt = "jpeg" if image_format.upper() in {"JPG", "JPEG"} else "png"
    save_kwargs = {"quality": 95} if fmt == "jpeg" else {}
    fig.savefig(buffer, format=fmt, dpi=int(dpi), facecolor="white",
                bbox_inches="tight", pad_inches=0.15,
                **({"pil_kwargs": save_kwargs} if save_kwargs else {}))
    plt.close(fig)
    return buffer.getvalue()


# =====================================================================================
# PEL ASSETS DASHBOARD - new 11-section layout
# All processing functions above are unchanged; only the interface structure is new.
# Containers are created first (so every section sits in its designed position) and are
# filled afterwards in the order the application logic needs (symbology -> filtering ->
# legend -> map), exactly as in the previous version.
# =====================================================================================
def sec_tab(text: str, narrow: bool = False):
    st.markdown(f'<div class="sec-tab{" narrow" if narrow else ""}">{esc(text)}</div>', unsafe_allow_html=True)


def render_toc(kind: str):
    """Table of Content: layer list (visibility, select, zoom / rename / delete) for vector or raster layers."""
    want_raster = kind == "raster"
    names = [n for n in st.session_state.layer_order
             if (st.session_state.layers[n].get("kind") == "raster") == want_raster]
    if not names:
        st.caption("No raster layers loaded." if want_raster else "No layers loaded.")
    for name in names:
        row1, row2 = st.columns([0.2, 0.8], gap="small")
        with row1:
            current = st.session_state.visible.get(name, True)
            checked = st.checkbox(" ", value=current, key=f"vis_{safe_name(name)}", label_visibility="collapsed")
            st.session_state.visible[name] = checked
        with row2:
            selected = name == st.session_state.selected_layer
            st.button(("▶ " if selected else "") + name, key=f"select_{safe_name(name)}", use_container_width=True,
                      type="primary" if selected else "secondary", on_click=select_layer, args=(name,))
            if st.session_state.layers[name].get("kind") == "raster":
                st.caption("Raster · georeferenced")
            else:
                st.caption(f"{len(st.session_state.layers[name]['gdf']):,} features")
            action_col, go_col = st.columns([0.78, 0.22], gap="small")
            with action_col:
                action = st.selectbox("Layer actions", ["Actions…", "Zoom to layer", "Rename layer", "Delete layer"],
                                      key=f"layer_action_{safe_name(name)}", label_visibility="collapsed")
            with go_col:
                if st.button("⋮", key=f"apply_layer_action_{safe_name(name)}", help="Apply layer action"):
                    if action == "Zoom to layer":
                        st.session_state.zoom_to_layer = name
                        st.session_state.messages.append(f"Zooming to layer: {name}")
                        st.rerun()
                    elif action == "Rename layer":
                        st.session_state.rename_target = name
                        st.rerun()
                    elif action == "Delete layer":
                        delete_layer(name)
                        st.rerun()
                    else:
                        st.toast("Choose Zoom, Rename or Delete first.", icon="ℹ️")
    rename_target = st.session_state.get("rename_target")
    if rename_target in names:
        st.markdown('<div class="box-title">Rename Layer</div>', unsafe_allow_html=True)
        renamed_value = st.text_input("New layer name", value=rename_target,
                                      key=f"rename_input_{safe_name(rename_target)}")
        rename_col, cancel_col = st.columns(2, gap="small")
        with rename_col:
            if st.button("Apply rename", key=f"rename_apply_{safe_name(rename_target)}", type="primary", use_container_width=True):
                if rename_layer(rename_target, renamed_value):
                    st.session_state.rename_target = None
                st.rerun()
        with cancel_col:
            if st.button("Cancel", key=f"rename_cancel_{safe_name(rename_target)}", use_container_width=True):
                st.session_state.rename_target = None
                st.rerun()


# ------------------------------------------------------------------ layout skeleton
left_col, main_col = st.columns([1.32, 6.6], gap="small")
with left_col:
    left_panel = st.container(key="left_panel")          # sections 1-6 (yellow panel)
    layout_slot = st.container(key="layout_slot")        # section 11
with main_col:
    header_slot = st.container()
    center_col, right_col = st.columns([4.75, 1.75], gap="small")
    with center_col:
        map_slot = st.container()                        # BASEMAP
        profile_slot = st.container()                    # section 9
    with right_col:
        sec_tab("7 · SYMBOLOGY")
        sym_box = st.container(height=560, border=False, key="box_7")
        sec_tab("8 · LEGEND BOX")
        legend_box = st.container(height=250, border=False, key="box_8")
        open_slot = st.container()                       # OPEN ELEVATION PROFILE
    sec_tab("10 · Attribute Table", narrow=True)
    with st.container(key="box_10"):
        filter_slot = st.container()
        table_slot = st.container()

# ------------------------------------------------------------------ header
with header_slot:
    st.markdown(f"""
    <div class="pel-banner"><div class="pel-banner-in">
      <div>{logo_markup()}</div>
      <div><div class="pel-title">PEL ASSETS DASHBOARD</div>
      <div class="pel-subtitle">(Petroleum Exploration (Pvt) Limited)</div></div>
      <div class="pel-credit"><div class="pb">PREPARED BY:</div>NOUMAN SALEEM<b>(GIS Specialist/Exploration Dpt)</b></div>
    </div></div>
    """, unsafe_allow_html=True)

# ------------------------------------------------------------------ LEFT PANEL: sections 1-6
with left_panel:
    # 1 · Upload Vector Data
    sec_tab("1 · Upload Vector Data")
    with st.container(key="box_1"):
        st.markdown('<div class="helper">Kml, kmz, .shp, (.shx, .dbf and .prj together)</div>', unsafe_allow_html=True)
        st.markdown('<div class="toc-title">Table of Content</div>', unsafe_allow_html=True)
        with st.container(height=190, border=False, key="toc_vector"):
            render_toc("vector")
        upload_files = st.file_uploader(
            "Add vector data (.shp + .shx + .dbf + .prj, KML/KMZ, GeoJSON, GPKG)",
            type=["shp", "shx", "dbf", "prj", "cpg", "kml", "kmz", "geojson", "json", "gpkg"],
            accept_multiple_files=True, label_visibility="collapsed", key="vector_files")
        load_col, clear_col = st.columns([0.58, 0.42], gap="small")
        with load_col:
            if st.button("UPLOAD", key="upload_vector_btn", type="primary", use_container_width=True):
                if not upload_files:
                    st.toast("Choose the vector files first.", icon="⚠️")
                else:
                    new_layers, errors = upload_to_layers(upload_files)
                    if new_layers:
                        added_names = register_new_layers(new_layers)
                        st.session_state.messages.append(f"Added {len(added_names)} layer(s); existing layers were retained: " + ", ".join(added_names))
                        st.rerun()
                    for error in errors:
                        st.error(error)
        with clear_col:
            st.button("Clear Layers", key="clear_layers_btn", use_container_width=True, on_click=clear_layers)

    # 2 · Upload Raster Data
    sec_tab("2 · Upload Raster Data")
    with st.container(key="box_2"):
        st.markdown('<div class="helper">.tif / tiff, ((JPG, PNG (BUT SHOULD BE GEOREFFED)</div>', unsafe_allow_html=True)
        st.markdown('<div class="toc-title">Table of Content</div>', unsafe_allow_html=True)
        with st.container(height=150, border=False, key="toc_raster"):
            render_toc("raster")
        raster_files = st.file_uploader(
            "Add georeferenced raster (.tif / .tiff, georeferenced JPG / PNG)", type=["tif", "tiff", "jpg", "jpeg", "png"],
            accept_multiple_files=True, label_visibility="collapsed", key="raster_files",
            help="Raster must contain a valid CRS and georeferencing transform.")
        if st.button("UPLOAD", key="add_raster_layers", type="primary", use_container_width=True):
            if not raster_files:
                st.warning("Choose one or more raster files first.")
            else:
                new_rasters, raster_errors = load_raster_uploads(raster_files)
                if new_rasters:
                    added = register_new_layers(new_rasters)
                    st.session_state.messages.append("Added raster layer(s), retaining existing layers: " + ", ".join(added))
                    st.rerun()
                for err in raster_errors:
                    st.error(err)

    # 3 · GIS Analysis
    sec_tab("3 · GIS Analysis")
    raster_names = [n for n in st.session_state.layer_order if st.session_state.layers[n].get("kind") == "raster"]
    with st.container(key="box_3"):
        if not raster_names:
            st.caption("Add a georeferenced GeoTIFF raster to enable raster clipping.")
        else:
            analysis_raster = st.selectbox("Input raster / DEM", raster_names, key="analysis_raster_layer")
            analysis_type = st.selectbox("Analysis", ["Contours", "Slope", "Aspect", "Hillshade", "Gaussian smooth"], key="raster_analysis_type")
            contour_interval = st.number_input("Contour interval (raster units)", min_value=0.01, value=100.0, step=10.0, key="contour_interval")
            if st.button("Run GIS Analysis", key="run_raster_analysis", type="primary", use_container_width=True):
                try:
                    result_layer = run_raster_analysis(analysis_raster, analysis_type, float(contour_interval))
                    added = register_new_layers([result_layer])
                    st.session_state.messages.append(f"{analysis_type} completed; result added as {added[0]}. Source raster and all existing layers were retained.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"GIS analysis failed: {exc}")

    # 4 · Clip Raster by AOI
    sec_tab("4 · Clip Raster by AOI")
    with st.container(key="box_4"):
        raster_clip_names = [n for n in st.session_state.layer_order
                             if st.session_state.layers[n].get("kind") == "raster"]
        polygon_clip_names = []
        for n in st.session_state.layer_order:
            rec = st.session_state.layers[n]
            if rec.get("kind") != "raster":
                gg = rec.get("gdf")
                if gg is not None and not gg.empty and gg.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).any():
                    polygon_clip_names.append(n)
        if not polygon_clip_names:
            st.caption("Add a polygon vector layer to use as the area of interest (AOI).")
        elif not raster_clip_names:
            st.caption("Add a georeferenced GeoTIFF raster to enable raster clipping.")
        else:
            raster_clip_name = st.selectbox("Raster to clip", raster_clip_names, key="raster_clip_input")
            raster_boundary_name = st.selectbox("AOI polygon layer", polygon_clip_names, key="raster_clip_boundary")
            boundary_for_raster_clip = st.session_state.layers[raster_boundary_name]["gdf"]
            polygon_positions = [i for i, geom in enumerate(boundary_for_raster_clip.geometry)
                                 if geom is not None and not geom.is_empty and geom.geom_type in ("Polygon", "MultiPolygon")]
            use_all_aoi = st.checkbox("Use all polygon features in AOI layer", value=True, key="raster_clip_all_features")
            selected_aoi_indices = None
            if not use_all_aoi:
                attr_cols_aoi = [c for c in boundary_for_raster_clip.columns if c != boundary_for_raster_clip.geometry.name]
                label_field_aoi = st.selectbox("AOI feature label field", ["(Feature index)"] + attr_cols_aoi,
                                               key=f"raster_clip_label_field_{safe_name(raster_boundary_name)}")
                aoi_labels = []
                aoi_label_to_pos = {}
                for pos in polygon_positions:
                    if label_field_aoi == "(Feature index)":
                        lab = f"Feature {pos + 1} (row {pos})"
                    else:
                        val = boundary_for_raster_clip.iloc[pos][label_field_aoi]
                        lab = f"{val if pd.notna(val) else '(No value)'} [row {pos}]"
                    aoi_labels.append(lab)
                    aoi_label_to_pos[lab] = pos
                chosen_aoi_labels = st.multiselect("Select AOI feature(s)", aoi_labels, key=f"raster_clip_features_{safe_name(raster_boundary_name)}")
                selected_aoi_indices = [aoi_label_to_pos[x] for x in chosen_aoi_labels]
            if st.button("Clip Raster by AOI", type="primary", use_container_width=True, key="run_raster_clip"):
                try:
                    output_raster = clip_raster_by_boundary(raster_clip_name, raster_boundary_name, selected_aoi_indices)
                    added_raster = register_new_layers([output_raster])
                    st.session_state.messages.append(
                        f"Raster clip completed: {added_raster[0]}. Source raster and all other layers were retained.")
                    st.success(f"Created raster layer: {added_raster[0]}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Raster clipping failed: {exc}")


    # 5 · Clip Assets
    sec_tab("5 · Clip Assets")
    with st.container(key="box_5"):
        st.caption("Choose PEL extraction or ArcGIS-style spatial clipping.")
        st.radio("Clip operation", ["PEL-only extraction", "Clip by selected area"],
                 key="clip_operation", label_visibility="collapsed",
                 format_func=lambda v: "PEL only Extraction" if v == "PEL-only extraction" else "Clip by Selected Area")
        clip_vector_names = [n_ for n_ in st.session_state.layer_order
                             if st.session_state.layers[n_].get("kind") != "raster"]
        # drop stale selections (deleted/renamed layers) before the widget is drawn
        st.session_state["clip_input_layers"] = [n_ for n_ in st.session_state.get("clip_input_layers", [])
                                                 if n_ in clip_vector_names]
        st.multiselect("Input Layer", clip_vector_names, key="clip_input_layers",
                       placeholder="Choose layer(s)")
        if st.session_state.get("clip_operation", "PEL-only extraction") == "PEL-only extraction":
            all_text_fields = []
            for name in st.session_state.layer_order:
                if st.session_state.layers[name].get("kind") != "raster":
                    all_text_fields.extend(candidate_text_fields(st.session_state.layers[name]["gdf"]))
            field_options = ["(Auto-detect)"] + list(dict.fromkeys(all_text_fields))
            st.selectbox("Match Field", field_options, key="clip_field", index=0,
                         format_func=lambda v: "Auto-detected" if v == "(Auto-detect)" else v)
            st.text_input("KEYWORDS", value="PEL", key="clip_keyword")
            st.button("CLIP PEL ASSETS", type="primary", use_container_width=True,
                      on_click=clip_selected_sources, key="clip_pel_assets_btn")
        else:
            polygon_layers = []
            for name in st.session_state.layer_order:
                if st.session_state.layers[name].get("kind") == "raster":
                    continue
                gdf_boundary = st.session_state.layers[name]["gdf"]
                if not gdf_boundary.empty and gdf_boundary.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).any():
                    polygon_layers.append(name)
            if polygon_layers:
                boundary_name = st.selectbox("Clip boundary layer", polygon_layers, key="spatial_clip_boundary")
                boundary_gdf = st.session_state.layers[boundary_name]["gdf"]
                boundary_attrs = [c for c in boundary_gdf.columns if c != boundary_gdf.geometry.name]
                default_name_fields = [c for c in boundary_attrs if any(t in c.lower() for t in ("name", "id", "code", "block", "well"))]
                feature_field_options = boundary_attrs or ["(Feature index)"]
                default_feature_field = default_name_fields[0] if default_name_fields else (feature_field_options[0] if feature_field_options else "(Feature index)")
                feature_field = st.selectbox("Feature identification field", feature_field_options,
                                             index=feature_field_options.index(default_feature_field),
                                             key=f"clip_feature_field_{safe_name(boundary_name)}")
                feature_labels = []
                label_to_index = {}
                for row_position in range(len(boundary_gdf)):
                    if feature_field == "(Feature index)":
                        value = f"Feature {row_position + 1}"
                    else:
                        raw_value = boundary_gdf.iloc[row_position][feature_field]
                        value = "(No value)" if pd.isna(raw_value) else str(raw_value)
                    label = f"#{row_position + 1} | {value}"
                    feature_labels.append(label)
                    label_to_index[label] = row_position
                selected_feature_labels = st.multiselect(
                    "Select feature(s) to use as clip area", feature_labels,
                    key=f"clip_selected_features_{safe_name(boundary_name)}",
                    help="Select one or more polygon features, or click a polygon on the map using Select (arrow). Only the selected features define the clip area.")
                map_selection = st.session_state.get("map_selected_feature") or {}
                use_map_selection = st.checkbox(
                    "Use feature selected on map (when it belongs to this boundary layer)",
                    value=map_selection.get("layer") == boundary_name,
                    key=f"clip_use_map_selection_{safe_name(boundary_name)}",
                    help="Select a polygon on the map with the Select (arrow) tool, then use that exact feature as the clip boundary."
                )
                if use_map_selection and map_selection.get("layer") == boundary_name:
                    st.caption("Map-selected feature will be used as the clip boundary: " + map_selection.get("label", "selected feature"))
                elif selected_feature_labels:
                    st.caption(f"Selected {len(selected_feature_labels)} feature(s) from {boundary_name}.")
                else:
                    st.caption("Choose the polygon feature(s) first; the full layer will not be used unless features are selected.")
                if st.button("Clip Selected Layers by Selected Feature(s)", type="primary", use_container_width=True):
                    input_names = [n for n in st.session_state.layer_order
                                   if n in (st.session_state.get("clip_input_layers", []) or [])
                                   and st.session_state.layers[n].get("kind") != "raster"]
                    map_selection = st.session_state.get("map_selected_feature") or {}
                    if use_map_selection and map_selection.get("layer") == boundary_name:
                        selected_indices = [int(map_selection.get("source_position", map_selection.get("position", -1)))]
                    else:
                        selected_indices = [label_to_index[label] for label in selected_feature_labels if label in label_to_index]
                    clip_layers_by_boundary(input_names, boundary_name, selected_indices)
                    st.rerun()
            else:
                st.warning("Load a polygon layer to use as the clip boundary.")

    # 6 · Base Map Layers
    sec_tab("6 · Base Map Layers")
    with st.container(key="box_6"):
        if st.session_state.get("basemap") not in ("OpenStreetMap", "Satellite", "Terrain"):
            st.session_state.basemap = "OpenStreetMap"
        st.radio("Basemap", ["OpenStreetMap", "Satellite", "Terrain"], key="basemap", label_visibility="collapsed",
                 format_func=lambda v: "OpenStreetMap" if v == "OpenStreetMap" else v.upper())

# ------------------------------------------------------------------ 7 · SYMBOLOGY (runs before derived layers are computed)
with sym_box:
    sym_name = st.session_state.selected_layer
    style = None
    sym_is_raster = False
    raw_sym = None
    if sym_name and sym_name in st.session_state.layers:
        raw_sym = st.session_state.layers[sym_name]["gdf"]
        style = st.session_state.styles.setdefault(sym_name, {"mode": "Single Symbol", "field": "", "color": RED, "ramp": "PEL Navy–Gold", "palette": PALETTES["PEL Navy–Gold"][:]})
        sym_is_raster = st.session_state.layers[sym_name].get("kind") == "raster"
    if style is None:
        st.caption("Load or select a layer to configure its symbology.")

    # ---- Raster Symbology
    st.markdown('<div class="box-title">Raster Symbology</div>', unsafe_allow_html=True)
    if style is not None and sym_is_raster:
        raster_ramps = list(PALETTES)
        current_ramp = style.get("raster_ramp", "Terrain")
        style["raster_ramp"] = st.selectbox("Color Ramp", raster_ramps,
            index=raster_ramps.index(current_ramp) if current_ramp in raster_ramps else 0,
            key=f"raster_ramp_{safe_name(sym_name)}")
        st.markdown(f'<div style="height:12px;border:1px solid #172C51;border-radius:3px;background:linear-gradient(90deg,{",".join(PALETTES[style["raster_ramp"]])});margin:2px 0 8px"></div>', unsafe_allow_html=True)
        raster_class_modes = ["Continuous Stretch", "Equal Interval", "Quantile", "Unique Values"]
        current_raster_mode = style.get("raster_classification", "Continuous Stretch")
        style["raster_classification"] = st.selectbox(
            "Raster Classification", raster_class_modes,
            index=raster_class_modes.index(current_raster_mode) if current_raster_mode in raster_class_modes else 0,
            key=f"raster_classification_{safe_name(sym_name)}",
            help="Continuous Stretch displays a smooth gradient. Equal Interval and Quantile classify numeric raster values; Unique Values is for categorical rasters.")
        if style["raster_classification"] in {"Equal Interval", "Quantile"}:
            style["raster_classes"] = st.slider("Number of raster classes", 2, 12,
                int(style.get("raster_classes", 5)), key=f"raster_classes_{safe_name(sym_name)}")
        style["raster_opacity"] = st.slider("Raster opacity", 0.1, 1.0, float(style.get("raster_opacity", 0.75)), 0.05, key=f"raster_opacity_{safe_name(sym_name)}")
        st.caption(f"Band {st.session_state.layers[sym_name].get('raster_band', 1)} · min: {st.session_state.layers[sym_name].get('raster_min')} · max: {st.session_state.layers[sym_name].get('raster_max')}")
        st.session_state.styles[sym_name] = style
    elif style is not None:
        st.caption("Select a raster layer to edit raster symbology.")

    # ---- Vector Symbology
    st.markdown('<div class="box-title" style="margin-top:8px">Vector Symbology</div>', unsafe_allow_html=True)
    if style is not None and not sym_is_raster:
        style["fill_color"] = st.color_picker("Fill Color", value=style.get("fill_color", style.get("color", RED)), key=f"single_color_{safe_name(sym_name)}")
        style["color"] = style["fill_color"]
        style["outline_color"] = st.color_picker("Outline Color", value=style.get("outline_color", NAVY), key=f"outline_color_{safe_name(sym_name)}")
        style["size"] = st.slider("Size / outline width", 0.5, 6.0, float(style.get("size", 2.2)), 0.5, key=f"symbol_size_{safe_name(sym_name)}")
        style["fill_opacity"] = st.slider("Fill Opacity", 0.05, 0.9, float(style.get("fill_opacity", 0.30)), 0.05, key=f"fill_opacity_{safe_name(sym_name)}")
        geom_types = set(raw_sym.geometry.geom_type.dropna().tolist()) if raw_sym is not None and not raw_sym.empty else set()
        if any("Point" in gt for gt in geom_types):
            st.markdown('<div class="box-title" style="margin-top:8px">Point Symbol Gallery · 70+ icons</div>', unsafe_allow_html=True)
            point_symbol_names = list(POINT_SYMBOLS)
            current_point_symbol = style.get("point_symbol", "Oil well")
            style["point_symbol"] = st.selectbox(
                "Point icon (petroleum, survey and general GIS)", point_symbol_names,
                index=point_symbol_names.index(current_point_symbol) if current_point_symbol in point_symbol_names else 0,
                format_func=lambda label: f"{POINT_SYMBOLS[label]}  {label}",
                key=f"point_symbol_{safe_name(sym_name)}")
            point_cols = st.columns(2)
            with point_cols[0]:
                style["point_icon_color"] = st.color_picker("Icon color", style.get("point_icon_color", NAVY), key=f"point_icon_color_{safe_name(sym_name)}")
            with point_cols[1]:
                style["point_icon_size"] = st.slider("Icon size", 12, 48, int(style.get("point_icon_size", 24)), 2, key=f"point_icon_size_{safe_name(sym_name)}")
        if any("LineString" in gt or "LinearRing" in gt for gt in geom_types):
            line_names = list(LINE_SYMBOLS)
            current_line = style.get("line_symbol", "Solid")
            style["line_symbol"] = st.selectbox("Line symbol style", line_names,
                index=line_names.index(current_line) if current_line in line_names else 0,
                key=f"line_symbol_{safe_name(sym_name)}")
        if any("Polygon" in gt for gt in geom_types):
            polygon_names = list(POLYGON_SYMBOLS)
            current_polygon = style.get("polygon_symbol", "Solid fill")
            style["polygon_symbol"] = st.selectbox("Polygon fill style", polygon_names,
                index=polygon_names.index(current_polygon) if current_polygon in polygon_names else 0,
                key=f"polygon_symbol_{safe_name(sym_name)}")
        modes = ["Single Symbol", "Unique Values", "Equal Interval", "Quantile", "Natural Breaks"]
        current_mode = style.get("mode", "Single Symbol")
        style["mode"] = st.selectbox("Vector Classification", modes, index=modes.index(current_mode) if current_mode in modes else 0, key=f"sym_mode_{safe_name(sym_name)}")
        ramp_options = list(PALETTES)
        ramp_current = style.get("ramp", "PEL Navy–Gold")
        if ramp_current not in ramp_options:
            ramp_current = "PEL Navy–Gold"
        style["ramp"] = ramp_current
        if style["mode"] != "Single Symbol":
            style["ramp"] = st.selectbox("Class color ramp", ramp_options, index=ramp_options.index(ramp_current), key=f"ramp_{safe_name(sym_name)}")
        style["palette"] = PALETTES[style["ramp"]][:]
        if style["mode"] != "Single Symbol":
            st.markdown(f'<div style="height:12px;border:1px solid #172C51;border-radius:3px;background:linear-gradient(90deg,{",".join(style["palette"])});margin:2px 0 8px"></div>', unsafe_allow_html=True)
        attrs = [c for c in raw_sym.columns if c != raw_sym.geometry.name]
        numeric = [c for c in attrs if pd.api.types.is_numeric_dtype(raw_sym[c])]
        if style["mode"] != "Single Symbol":
            fields = numeric if style["mode"] in {"Equal Interval", "Quantile", "Natural Breaks"} else attrs
            if fields:
                current_field = style.get("field", "")
                idx = fields.index(current_field) if current_field in fields else 0
                style["field"] = st.selectbox("Classification field", fields, index=idx, key=f"sym_field_{safe_name(sym_name)}")
                if style["mode"] in {"Equal Interval", "Quantile", "Natural Breaks"}:
                    style["classes"] = st.slider("Number of classes", 2, 8, int(style.get("classes", 5)), key=f"sym_classes_{safe_name(sym_name)}")
            else:
                style["mode"] = "Single Symbol"
                style["field"] = ""
                st.info("No suitable fields; Single Symbol is used.")
            if style["mode"] != "Single Symbol" and fields:
                preview_info = class_info(raw_sym, style)
                entries = preview_info.get("classes", [])
                if entries:
                    st.markdown('<div class="box-title" style="margin-top:8px">Edit Class Colors</div>', unsafe_allow_html=True)
                    style.setdefault("class_colors", {})
                    for class_index, entry in enumerate(entries):
                        label = entry["label"]
                        current_color = style["class_colors"].get(label, entry["color"])
                        style["class_colors"][label] = st.color_picker(label, value=current_color,
                            key=f"class_color_{safe_name(sym_name)}_{class_index}_{safe_name(label)}")
        else:
            style["field"] = ""
        st.session_state.styles[sym_name] = style
    elif style is not None:
        st.caption("Select a vector layer to edit vector symbology.")

# ------------------------------------------------------------------ 10 · filter (selected layer) - must run before the data is derived
with filter_slot:
    with st.expander("PEL Asset Filter (selected layer)", expanded=False):
        selected_name = st.session_state.selected_layer
        if selected_name and selected_name in st.session_state.layers and st.session_state.layers[selected_name].get("kind") == "raster":
            st.caption(f"Selected raster: {selected_name}. Use Raster Symbology and GIS Analysis controls.")
        elif selected_name and selected_name in st.session_state.layers:
            raw = st.session_state.layers[selected_name]["gdf"]
            attrs = [c for c in raw.columns if c != raw.geometry.name]
            cfg = st.session_state.filters.setdefault(selected_name, {"field": "(No filter)", "text_mode": "Chosen values", "values": [], "contains": "", "range": (0.0, 1.0), "include_na": False})
            with st.container(height=190, border=True):
                st.caption(f"Selected: {selected_name}")
                field_options = ["(No filter)"] + attrs
                field_default = cfg.get("field", "(No filter)")
                field_idx = field_options.index(field_default) if field_default in field_options else 0
                field = st.selectbox("Attribute field", field_options, index=field_idx, key=f"filter_field_{safe_name(selected_name)}")
                if field != cfg.get("_range_field"):
                    cfg["_range_field"] = field
                    cfg["range"] = None
                    cfg["values"] = []
                cfg["field"] = field
                if field == "(No filter)":
                    st.warning("No filter is set. All records in this layer are shown.")
                else:
                    series = raw[field]
                    if pd.api.types.is_numeric_dtype(series):
                        nums = pd.to_numeric(series, errors="coerce").dropna()
                        if not nums.empty:
                            minv, maxv = float(nums.min()), float(nums.max())
                            old_range = cfg.get("range")
                            if not old_range or len(old_range) != 2:
                                old_range = (minv, maxv)
                            lo = min(max(float(old_range[0]), minv), maxv)
                            hi = min(max(float(old_range[1]), minv), maxv)
                            if lo > hi:
                                lo, hi = minv, maxv
                            cfg["range"] = st.slider("Value range", min_value=minv, max_value=maxv, value=(lo, hi), key=f"range_{safe_name(selected_name)}_{safe_name(field)}")
                        cfg["include_na"] = st.checkbox("Include empty values", value=cfg.get("include_na", False), key=f"filter_na_{safe_name(selected_name)}")
                    else:
                        cfg["text_mode"] = st.radio("Text filter", ["Chosen values", "Contains text"], index=["Chosen values", "Contains text"].index(cfg.get("text_mode", "Chosen values")), key=f"text_mode_{safe_name(selected_name)}")
                        text_values = sorted(series.astype("string").fillna("(No data)").unique().tolist())
                        if cfg["text_mode"] == "Chosen values":
                            previous = [v for v in cfg.get("values", []) if v in text_values]
                            cfg["values"] = st.multiselect("Values", text_values, default=previous, key=f"filter_values_{safe_name(selected_name)}_{safe_name(field)}")
                        else:
                            cfg["contains"] = st.text_input("Contains text", value=cfg.get("contains", ""), key=f"filter_contains_{safe_name(selected_name)}_{safe_name(field)}")
        else:
            with st.container(height=190, border=True):
                st.caption("Select a layer to configure its filter.")

# Compute all filtered/styled data once so map, legend and table share the same current result.
filtered_layers: dict[str, gpd.GeoDataFrame] = {}
classifications: dict[str, dict] = {}
for name in st.session_state.layer_order:
    layer = st.session_state.layers[name]["gdf"]
    cfg = st.session_state.filters.get(name, {})
    if st.session_state.layers[name].get("kind") == "raster":
        filtered = layer.copy()
        classifications[name] = {"mode": "Raster", "classes": [], "color": style_color if (style_color := st.session_state.styles.get(name, {}).get("color", RED)) else RED}
    else:
        try:
            filtered = filtered_gdf(layer, cfg)
        except Exception:
            filtered = layer.copy()
        style = st.session_state.styles.get(name, {})
        classifications[name] = class_info(filtered, style) if not filtered.empty else {"mode": style.get("mode", "Single Symbol"), "classes": [], "color": style.get("color", RED)}
    filtered_layers[name] = filtered

# ------------------------------------------------------------------ 8 · LEGEND BOX
with legend_box:
    shown = [n for n in st.session_state.layer_order if st.session_state.visible.get(n, False)]
    if not shown:
        st.caption("No active legends. Turn on a layer to display its legend.")
    for name in shown:
        if st.session_state.layers[name].get("kind") == "raster":
            raster_style = st.session_state.styles.get(name, {})
            ramp = raster_style.get("raster_ramp", "Terrain")
            colors = PALETTES.get(ramp, PALETTES["Terrain"])
            raster_record = st.session_state.layers[name]
            raster_mode = raster_style.get("raster_classification", "Continuous Stretch")
            st.markdown(f'<div class="box-title">{esc(name)}</div>', unsafe_allow_html=True)
            if raster_mode == "Continuous Stretch":
                st.markdown(f'<div class="legend-row"><span class="legend-swatch" style="width:100%;height:12px;background:linear-gradient(90deg,{",".join(colors)});border-color:#667085"></span></div>', unsafe_allow_html=True)
                st.caption(f"Continuous stretch · {raster_record.get('raster_min')} to {raster_record.get('raster_max')} · {ramp}")
            else:
                try:
                    raster_entries, raster_min, raster_max = raster_class_legend_entries(raster_record, raster_style)
                    if raster_entries:
                        for raster_entry in raster_entries:
                            col = raster_entry["color"]
                            st.markdown(
                                f'<div class="legend-row"><span class="legend-swatch" style="background:{col}40;border-color:{col}"></span>{esc(raster_entry["label"])}</div>',
                                unsafe_allow_html=True
                            )
                        st.caption(f"{raster_mode} · {len(raster_entries)} classes · {raster_min:,.3f} to {raster_max:,.3f}")
                    else:
                        st.caption("No valid raster pixels are available for the legend.")
                except Exception as legend_error:
                    st.caption(f"{raster_mode} · raster values: {raster_record.get('raster_min')} to {raster_record.get('raster_max')}")
            continue
        gdf = filtered_layers.get(name)
        if gdf is None or gdf.empty:
            st.markdown(f'<div class="legend-row"><span class="legend-swatch" style="border-color:{GREY};background:{GREY}30"></span><b>{esc(name)}</b> — no matching records</div>', unsafe_allow_html=True)
            continue
        info = classifications[name]
        st.markdown(f'<div class="box-title">{esc(name)}</div>', unsafe_allow_html=True)
        geom_types = set(gdf.geometry.geom_type.dropna().tolist())
        if info.get("mode") == "Single Symbol" and any("Point" in gt for gt in geom_types):
            point_style = st.session_state.styles.get(name, {})
            symbol_name = point_style.get("point_symbol", "Generic point")
            glyph = POINT_SYMBOLS.get(symbol_name, "●")
            icon_color = point_style.get("point_icon_color", info.get("color", RED))
            icon_size = int(point_style.get("point_icon_size", 24))
            st.markdown(f'<div class="legend-row"><span style="font-size:{icon_size}px;color:{icon_color};line-height:1">{html.escape(glyph)}</span> {esc(symbol_name)}</div>', unsafe_allow_html=True)
        elif info.get("mode") == "Single Symbol" and any("LineString" in gt for gt in geom_types):
            line_style = st.session_state.styles.get(name, {}).get("line_symbol", "Solid")
            dash = LINE_SYMBOLS.get(line_style)
            css_style = "dashed" if dash and " " in dash else ("dotted" if dash and dash.startswith("2") else "solid")
            color = st.session_state.styles.get(name, {}).get("outline_color", NAVY)
            st.markdown(f'<div class="legend-row"><span style="display:inline-block;width:30px;border-top:3px {css_style} {color};vertical-align:middle;margin-right:7px"></span>{esc(line_style)}</div>', unsafe_allow_html=True)
        elif info.get("mode") == "Unique Values":
            for entry in info.get("classes", []):
                st.markdown(f'<div class="legend-row"><span class="legend-swatch" style="background:{entry["color"]}40;border-color:{entry["color"]}"></span>{esc(entry["label"])}</div>', unsafe_allow_html=True)
        elif info.get("mode") in {"Equal Interval", "Quantile", "Natural Breaks"}:
            for entry in info.get("classes", []):
                st.markdown(f'<div class="legend-row"><span class="legend-swatch" style="background:{entry["color"]}40;border-color:{entry["color"]}"></span>{esc(entry["label"])}</div>', unsafe_allow_html=True)
        else:
            color = info.get("color", RED)
            st.markdown(f'<div class="legend-row"><span class="legend-swatch" style="background:{color}40;border-color:{color}"></span>All features</div>', unsafe_allow_html=True)

# Toast queued state messages after callbacks have updated session state.
for message in st.session_state.messages:
    st.toast(message)
st.session_state.messages = []
for error in st.session_state.get("startup_errors", []):
    st.warning(error)
if st.session_state.get("startup_sample"):
    st.session_state.startup_sample = False

# ------------------------------------------------------------------ BASEMAP (map viewer)
with map_slot:
    st.markdown('<div class="map-label">BASEMAP</div>', unsafe_allow_html=True)
    map_tool = st.radio(
        "Map tool", ["Pan", "Select (arrow)"], horizontal=True, key="map_tool",
        help="Pan: drag the map to move around. Select (arrow): click a polygon feature on the map to select it for clipping. Dragging remains available in both modes."
    )
    if map_tool == "Select (arrow)":
        st.caption("Select tool active: click inside a visible polygon feature. To clip it, choose the same layer under Clip Assets and enable the map-selected feature option.")
    else:
        st.caption("Pan tool active: drag to move the map; zoom with the map controls or mouse wheel. Use the polyline tool on the map to draw an elevation transect.")
    with st.container(key="map_frame"):
        tile_name, tile_url, attribution = BASEMAPS[st.session_state.basemap]
        m = folium.Map(
            location=[30.5, 69.3], zoom_start=5, tiles=None,
            control_scale=True, prefer_canvas=True,
            zoom_control=False,  # use Folium's explicit zoom/home controls below
        )
        # The selected base layer uses a direct, explicit tile URL.
        primary_tiles = folium.TileLayer(
            tiles=tile_url, attr=attribution, name=tile_name,
            overlay=False, control=True, show=True,
            min_zoom=2, max_zoom=19, max_native_zoom=19,
            detect_retina=False,
        ).add_to(m)

        # Prepare a second provider but keep it hidden unless the selected provider
        # returns repeated tile errors. This is a client-side fallback; it does not
        # make any external request from Python and does not block Streamlit startup.
        if st.session_state.basemap == "OpenStreetMap":
            fallback_name, fallback_url, fallback_attr = BASEMAPS["Satellite"]
        else:
            fallback_name, fallback_url, fallback_attr = BASEMAPS["OpenStreetMap"]
        fallback_tiles = folium.TileLayer(
            tiles=fallback_url, attr=fallback_attr,
            name=f"Fallback: {fallback_name}", overlay=False,
            control=False, show=False, min_zoom=2, max_zoom=19,
            max_native_zoom=19, detect_retina=False,
        ).add_to(m)

        from folium import MacroElement
        from jinja2 import Template
        tile_fallback = MacroElement()
        tile_fallback.primary_layer = primary_tiles
        tile_fallback.fallback_layer = fallback_tiles
        tile_fallback._template = Template("""
        {% macro script(this, kwargs) %}
        (function() {
          var map = {{ this._parent.get_name() }};
          var primary = {{ this.primary_layer.get_name() }};
          var fallback = {{ this.fallback_layer.get_name() }};
          var failedTiles = 0;
          var fallbackEnabled = false;
          primary.on('tileerror', function() {
            failedTiles += 1;
            if (!fallbackEnabled && failedTiles >= 8) {
              fallbackEnabled = true;
              if (map.hasLayer(primary)) { map.removeLayer(primary); }
              fallback.addTo(map);
              fallback.bringToBack();
              console.warn('PEL Assets Map: selected basemap tiles failed; using fallback tiles.');
            }
          });
        })();
        {% endmacro %}
        """)
        tile_fallback.add_to(m)
        # Home/full extent control: fit visible features; initial map stays centered on Pakistan.
        visible_gdfs = [filtered_layers[n] for n in st.session_state.layer_order
                        if st.session_state.visible.get(n, False) and not filtered_layers[n].empty
                        and st.session_state.layers[n].get("kind") != "raster"]
        visible_rasters = [st.session_state.layers[n] for n in st.session_state.layer_order
                           if st.session_state.visible.get(n, False) and st.session_state.layers[n].get("kind") == "raster"]
        zoom_target = st.session_state.get("zoom_to_layer")
        if zoom_target in filtered_layers:
            try:
                if st.session_state.layers[zoom_target].get("kind") == "raster":
                    z_bounds = st.session_state.layers[zoom_target]["raster_bounds"]
                elif not filtered_layers[zoom_target].empty:
                    z_bounds = filtered_layers[zoom_target].total_bounds
                else:
                    z_bounds = None
                if z_bounds is not None and np.isfinite(z_bounds).all():
                    m.fit_bounds([[z_bounds[1], z_bounds[0]], [z_bounds[3], z_bounds[2]]], padding=(35, 35))
                st.session_state.zoom_to_layer = None
            except Exception:
                pass
        elif visible_gdfs or visible_rasters:
            try:
                extent_items = [g.total_bounds for g in visible_gdfs]
                extent_items.extend([r["raster_bounds"] for r in visible_rasters])
                extent_array = np.asarray(extent_items, dtype=float)
                bounds = np.array([np.nanmin(extent_array[:, 0]), np.nanmin(extent_array[:, 1]),
                                   np.nanmax(extent_array[:, 2]), np.nanmax(extent_array[:, 3])])
                if np.isfinite(bounds).all() and bounds[0] < bounds[2] and bounds[1] < bounds[3]:
                    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], padding=(20, 20))
            except Exception:
                pass
        layer_render_errors = []
        for name in st.session_state.layer_order:
            if st.session_state.visible.get(name, False):
                try:
                    add_layer_to_map(m, name, filtered_layers[name], st.session_state.styles.get(name, {}), True)
                except Exception as exc:
                    layer_render_errors.append(f"{name}: {type(exc).__name__}: {exc}")

        # Draw the current map selection with an ArcGIS-like gold outline.
        selected_map_feature = st.session_state.get("map_selected_feature")
        if selected_map_feature:
            sel_layer = selected_map_feature.get("layer")
            sel_pos = selected_map_feature.get("position")
            if sel_layer in filtered_layers and sel_pos is not None:
                try:
                    selected_gdf = filtered_layers[sel_layer]
                    if 0 <= int(sel_pos) < len(selected_gdf):
                        selected_one = selected_gdf.iloc[[int(sel_pos)]].copy()
                        folium.GeoJson(
                            json_safe_geojson(selected_one),
                            name="Selected feature highlight",
                            style_function=lambda feature: {"color": "#FFD400", "weight": 6, "fillColor": "#FFD400", "fillOpacity": 0.12},
                            tooltip=f"Selected: {sel_layer} | feature #{int(sel_pos)+1}",
                        ).add_to(m)
                except Exception:
                    pass
        # Visible stacked tool controls: zoom, home, then distance/area measurement.
        from folium import MacroElement
        from jinja2 import Template
        home = MacroElement()
        home._template = Template("""
        {% macro script(this, kwargs) %}
        var homeControl = L.control({position:'topleft'});
        homeControl.onAdd = function(map) {
          var div = L.DomUtil.create('div','leaflet-bar leaflet-control');
          var a = L.DomUtil.create('a','',div);
          a.href='#'; a.title='Full extent / Home'; a.innerHTML='⌂';
          a.style.width='30px'; a.style.height='30px'; a.style.lineHeight='30px'; a.style.textAlign='center'; a.style.fontSize='22px';
          L.DomEvent.disableClickPropagation(div);
          L.DomEvent.on(a,'click',function(e){L.DomEvent.preventDefault(e); map.fitBounds(
            {% if this.bounds %}{{this.bounds}}{% else %}[[23.5,60.5],[37.5,77.5]]{% endif %},
            {padding:[20,20]});});
          return div;
        };
        homeControl.addTo({{this._parent.get_name()}});
        {% endmacro %}
        """)
        if visible_gdfs:
            try:
                home_bounds = [[float(bounds[1]), float(bounds[0])], [float(bounds[3]), float(bounds[2])]]
            except Exception:
                home_bounds = [[23.5, 60.5], [37.5, 77.5]]
        else:
            home_bounds = [[23.5, 60.5], [37.5, 77.5]]
        home.bounds = home_bounds
        home.add_to(m)
        MeasureControl(position="topleft", primary_length_unit="kilometers", secondary_length_unit="miles",
                       primary_area_unit="sqkilometers", secondary_area_unit="hectares", active_color=BLUE,
                       completed_color=GOLD).add_to(m)
        # Draw a polyline on the map to define the elevation-profile transect.
        Draw(export=False, position="topleft", draw_options={
            "polyline": {"shapeOptions": {"color": "#D946EF", "weight": 4}},
            "polygon": False, "rectangle": False, "circle": False, "circlemarker": False, "marker": False
        }, edit_options={"edit": True, "remove": True}).add_to(m)
        saved_profile_line = st.session_state.get("profile_line_geojson")
        if saved_profile_line:
            try:
                folium.GeoJson(saved_profile_line, name="Elevation profile transect",
                    style_function=lambda feature: {"color": "#D946EF", "weight": 4, "dashArray": "7 4"}).add_to(m)
            except Exception:
                pass

        # Add LayerControl only after all user-added vector/raster layers exist.
        folium.LayerControl(position="topright", collapsed=False).add_to(m)

        # Streamlit-Folium can retain an old iframe when the component key stays
        # constant. Build a stable signature from actual map inputs so adding,
        # removing, showing/hiding, or restyling a layer forces a fresh map render.
        map_signature_items = []
        for layer_name in st.session_state.layer_order:
            record = st.session_state.layers.get(layer_name, {})
            is_visible = bool(st.session_state.visible.get(layer_name, False))
            style_signature = st.session_state.styles.get(layer_name, {})
            if record.get("kind") == "raster":
                raster_path = Path(record.get("raster_path", ""))
                try:
                    stat = raster_path.stat()
                    data_signature = f"raster:{stat.st_size}:{stat.st_mtime_ns}"
                except OSError:
                    data_signature = "raster:missing"
            else:
                layer_gdf = filtered_layers.get(layer_name)
                data_signature = f"vector:{len(layer_gdf) if layer_gdf is not None else 0}"
            map_signature_items.append({
                "name": layer_name,
                "visible": is_visible,
                "data": data_signature,
                "style": style_signature,
            })
        map_signature = json.dumps({
            "basemap": st.session_state.basemap,
            "layers": map_signature_items,
            "profile_line": st.session_state.get("profile_line_geojson"),
            "zoom_to_layer": st.session_state.get("zoom_to_layer"),
        }, sort_keys=True, default=str, separators=(",", ":"))
        map_component_key = "pel_assets_map_" + hashlib.sha1(map_signature.encode("utf-8")).hexdigest()[:16]

        if layer_render_errors:
            st.warning("One or more layers could not be rendered. The basemap will remain available. Details: " + " | ".join(layer_render_errors[:5]))

        map_html = st_folium(
            m, height=640, use_container_width=True, key=map_component_key,
            returned_objects=["last_clicked", "all_drawings", "last_active_drawing"],
        )
        # Retain the most recently drawn LineString as the elevation-profile transect.
        if isinstance(map_html, dict):
            active_drawing = map_html.get("last_active_drawing")
            line_coords = _profile_line_coords(active_drawing)
            if line_coords:
                st.session_state.profile_line_geojson = active_drawing
                st.session_state.profile_line_coords = line_coords
        # st_folium reports the clicked map coordinate. In Select mode, find the
        # topmost visible polygon containing that point and retain its source row.
        clicked = map_html.get("last_clicked") if isinstance(map_html, dict) else None
        click_signature = None
        if clicked and clicked.get("lat") is not None and clicked.get("lng") is not None:
            click_signature = (round(float(clicked["lat"]), 7), round(float(clicked["lng"]), 7))
        is_new_map_click = click_signature is not None and click_signature != st.session_state.get("last_processed_map_click")
        if map_tool == "Select (arrow)" and is_new_map_click:
            st.session_state.last_processed_map_click = click_signature
            try:
                from shapely.geometry import Point
                click_point = Point(float(clicked["lng"]), float(clicked["lat"]))
                found = None
                for candidate_name in reversed(st.session_state.layer_order):
                    if not st.session_state.visible.get(candidate_name, False) or st.session_state.layers[candidate_name].get("kind") == "raster":
                        continue
                    candidate_gdf = filtered_layers.get(candidate_name)
                    if candidate_gdf is None or candidate_gdf.empty:
                        continue
                    # Polygon features are the clip-area selection targets.
                    for visible_pos in range(len(candidate_gdf) - 1, -1, -1):
                        geom = candidate_gdf.geometry.iloc[visible_pos]
                        if geom is None or geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
                            continue
                        if geom.covers(click_point):
                            row_index = candidate_gdf.index[visible_pos]
                            original_gdf = st.session_state.layers[candidate_name]["gdf"]
                            try:
                                original_pos = int(original_gdf.index.get_loc(row_index))
                            except Exception:
                                original_pos = int(visible_pos)
                            row = candidate_gdf.iloc[visible_pos]
                            attr_cols = [c for c in candidate_gdf.columns if c != candidate_gdf.geometry.name]
                            label_value = ""
                            for field_name in attr_cols:
                                if any(token in field_name.lower() for token in ("name", "block", "id", "code")):
                                    raw = row.get(field_name)
                                    if pd.notna(raw):
                                        label_value = f" | {field_name}: {raw}"
                                        break
                            found = {"layer": candidate_name, "position": int(visible_pos),
                                     "source_position": original_pos,
                                     "label": f"{candidate_name} — feature #{visible_pos+1}{label_value}"}
                            break
                    if found:
                        break
                if found and found != st.session_state.get("map_selected_feature"):
                    st.session_state.map_selected_feature = found
                    st.session_state.selected_layer = found["layer"]
                    st.session_state.messages.append("Map feature selected: " + found["label"])
                    st.rerun()
            except Exception as exc:
                st.warning(f"Could not select the clicked feature: {exc}")
    if st.session_state.get("map_selected_feature"):
        selected_info = st.session_state.map_selected_feature
        st.info(f"Selected map feature: {selected_info.get('label', selected_info.get('layer'))}")
        if st.button("Clear map selection", key="clear_map_selection"):
            st.session_state.map_selected_feature = None
            st.rerun()
    st.caption("Measurement Distances and Areas")

# ------------------------------------------------------------------ 9 · Interactive Elevation Profile
with profile_slot:
    sec_tab("9 · Interactive Elevation Profile", narrow=True)
    with st.container(key="box_9"):
        st.markdown('<div class="gray-help">Draw a transect with the purple polyline tool. Local DEMs are sampled at about 30 m spacing (up to 1,200 points); online SRTM 30 m profiles use up to 100 samples for speed. Online mode requires internet access.</div>', unsafe_allow_html=True)
        profile_rasters = [n for n in st.session_state.layer_order if st.session_state.layers[n].get("kind") == "raster"]
        profile_options = ["Open DEM (SRTM ~30 m online)"] + profile_rasters
        selected_profile_source = st.selectbox("Elevation source", profile_options, key="profile_elevation_source")
        local_vertical_unit = st.selectbox("Local DEM elevation units", ["Meters", "Feet"], key="profile_vertical_units",
                                           help="Choose the vertical units stored in the local DEM. Results and statistics are reported in metres.")
        profile_coords = st.session_state.get("profile_line_coords")
        if profile_coords:
            st.markdown(f'<div class="pel-note">Profile line ready: {len(profile_coords)} vertices. Draw another line to replace it.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="pel-note">Draw a line on the map using the polyline tool before generating the profile.</div>', unsafe_allow_html=True)
        profile_col1, profile_col2 = st.columns([1, 1], gap="large")
        with profile_col1:
            generate_profile = st.button("Generate Profile", type="primary", key="generate_elevation_profile", use_container_width=True, disabled=not bool(profile_coords))
        with profile_col2:
            if st.button("Clear Profile Line", key="clear_profile_line", use_container_width=True):
                st.session_state.profile_line_geojson = None
                st.session_state.profile_line_coords = None
                st.session_state.elevation_profile_df = None
                st.session_state.elevation_profile_stats = None
                st.session_state.elevation_profile_dialog_open = False
                st.rerun()
        if generate_profile:
            try:
                raster_source = None if selected_profile_source == "Open DEM (SRTM ~30 m online)" else selected_profile_source
                with st.spinner("Sampling elevations along the transect…"):
                    prof_df, prof_stats = calculate_elevation_profile(profile_coords, raster_source, local_vertical_unit)
                st.session_state.elevation_profile_df = prof_df
                st.session_state.elevation_profile_stats = prof_stats
                st.session_state.messages.append("Elevation profile generated. Press OPEN ELEVATION PROFILE to view the chart.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not generate elevation profile: {exc}")

with open_slot:
    with st.container(key="box_open"):
        if st.button("OPEN ELEVATION PROFILE", key="open_elevation_profile", type="primary", use_container_width=True):
            if st.session_state.get("elevation_profile_df") is None:
                st.toast("Generate a profile first (draw a line, then press Generate Profile).", icon="⚠️")
            else:
                st.session_state.elevation_profile_dialog_open = True
                st.rerun()

if st.session_state.get("elevation_profile_dialog_open") and st.session_state.get("elevation_profile_df") is not None:
    st.session_state.elevation_profile_dialog_open = False   # dialog stays open until closed; avoids re-opening on every rerun
    show_elevation_profile_dialog(st.session_state.elevation_profile_df, st.session_state.elevation_profile_stats)

# ------------------------------------------------------------------ 10 · Attribute Table
with table_slot:
    selected_name = st.session_state.selected_layer
    if not selected_name or selected_name not in st.session_state.layers:
        st.info("Select a layer in Vector Data to view its attribute table.")
    elif not st.session_state.visible.get(selected_name, False):
        st.info("The selected layer is switched off. Turn it on to view its attribute table.")
    elif st.session_state.layers[selected_name].get("kind") == "raster":
        st.info("Raster layers do not have a vector attribute table. Use GIS Analysis to derive contours or terrain rasters.")
    else:
        table_gdf = filtered_layers[selected_name]
        if table_gdf.empty:
            st.info("No records match the active filter.")
        else:
            attr_cols = [c for c in table_gdf.columns if c != table_gdf.geometry.name]
            table = pd.DataFrame(table_gdf[attr_cols]).copy()
            # Convert any remaining non-JSON display values to readable strings.
            for col in table.columns:
                if pd.api.types.is_datetime64_any_dtype(table[col]):
                    table[col] = table[col].astype("string")
            st.dataframe(table, use_container_width=True, height=320, hide_index=True)

# ------------------------------------------------------------------ 11 · Map Layout
with layout_slot:
    sec_tab("11 · Map Layout")
    with st.container(key="box_11"):
        st.markdown('<div class="gray-help">Create a print-ready static map from the currently visible, filtered layers. Coordinate labels are shown around the map frame; no internal grid lines are drawn.</div>', unsafe_allow_html=True)
        layout_title = st.text_input("Map Title", value="PEL ASSETS MAP", key="layout_title")
        chk1, chk2 = st.columns(2, gap="small")
        with chk1:
            st.checkbox("North Arrow", value=True, key="layout_north_arrow")
            st.checkbox("Legends", value=True, key="layout_legend")
        with chk2:
            st.checkbox("Scale-bar", value=True, key="layout_scalebar")
            st.checkbox("GRID FRAME", value=True, key="layout_coordinate_frame")
        export_dpi = st.slider("Export DPI", min_value=100, max_value=800, value=300, step=50, key="layout_dpi")
        fmt_col, create_col = st.columns([1, 1], gap="small")
        with fmt_col:
            export_format = st.selectbox("Image Format", ["JPG", "PNG"], key="layout_format")
        with create_col:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            create_layout = st.button("CREATE MAP", type="primary", use_container_width=True, key="create_map_layout")
        if create_layout:
            try:
                visible_for_export = [n for n in st.session_state.layer_order
                                      if st.session_state.visible.get(n, False)]
                image_bytes = make_print_layout(
                    visible_for_export, filtered_layers, classifications, layout_title, export_dpi, export_format,
                    st.session_state.get("layout_north_arrow", True),
                    st.session_state.get("layout_scalebar", True),
                    st.session_state.get("layout_legend", True),
                    st.session_state.get("layout_coordinate_frame", True)
                )
                st.session_state.layout_export_bytes = image_bytes
                st.session_state.layout_export_name = (
                    f"{safe_name(layout_title or 'PEL_ASSETS_MAP')}_{export_dpi}dpi."
                    f"{'png' if export_format == 'PNG' else 'jpg'}"
                )
                st.session_state.layout_export_format = export_format
                st.success(f"Map layout created at {export_dpi} DPI.")
            except Exception as exc:
                st.error(f"Could not create map layout: {exc}")
        if st.session_state.get("layout_export_bytes"):
            st.download_button(
                f"Download map ({st.session_state.get('layout_export_format', 'PNG')})",
                data=st.session_state.layout_export_bytes,
                file_name=st.session_state.get("layout_export_name", "PEL_ASSETS_MAP.png"),
                mime="image/png" if st.session_state.get("layout_export_format") == "PNG" else "image/jpeg",
                use_container_width=True,
                key="download_map_layout"
            )
