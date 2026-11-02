# PEL ASSETS MAP — Pakistan Asset Viewer

A Streamlit-based GIS dashboard for viewing, managing, styling and analyzing vector and raster geospatial data.

> **Publication notice:** Confirm that you have permission before publishing or distributing PEL branding, company-owned code, asset datasets, well locations, pipeline information, or other confidential material. This repository package excludes operational GIS datasets.

## Main capabilities

- Upload vector data: Shapefile, KML, KMZ, GeoJSON and GeoPackage
- Upload georeferenced raster data (GeoTIFF)
- Interactive Folium map with selectable basemaps
- Vector and raster symbology and classification
- Attribute table and PEL asset filtering/extraction
- Raster clipping by polygon area of interest
- Terrain/GIS analysis including contours, slope, aspect and hillshade
- Interactive elevation profile
- Map layout export with title, legend and map elements

Feature availability depends on the input data, its coordinate reference system, and installed geospatial libraries.

## Repository structure

```text
PEL-Assets-Dashboard/
├── pel_assets_dashboard.py
├── requirements.txt
├── Run_PEL_Dashboard.bat
├── README.md
├── .gitignore
├── assets/
│   └── .gitkeep
├── uploads/
│   └── .gitkeep
├── processed/
│   └── .gitkeep
├── screenshots/
│   └── .gitkeep
└── .streamlit/
    └── .gitkeep
```

## Requirements

- Windows 10/11 (for the supplied `.bat` launcher)
- Python 3.11 or 3.12
- Internet connection for installing Python packages and using online basemap tiles

## Run on Windows

1. Install Python 3.11 or 3.12 and ensure the Python Launcher (`py`) is available.
2. Download or clone this repository.
3. Open the project folder.
4. Double-click `Run_PEL_Dashboard.bat`.
5. When Streamlit starts, open the local address shown in the terminal (normally http://localhost:8501).

The launcher creates a local `.venv` environment and installs dependencies on the first run.

## Run manually

Open Command Prompt in the repository folder and run:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run pel_assets_dashboard.py
```

## Data folders

- `assets/`: optional images and approved branding files used by the application.
- `uploads/`: runtime location for user-uploaded GIS datasets.
- `processed/`: runtime location for generated GIS outputs.
- `screenshots/`: optional screenshots for project documentation.

The `.gitkeep` files preserve empty folders in Git. Runtime data in `uploads/` and `processed/` is excluded by `.gitignore`.

## Adding a logo or screenshots

Only add images that you own or are authorized to publish. Place approved application assets in `assets/` and public-facing screenshots in `screenshots/`. Review screenshots for confidential coordinates, attributes, file paths, and company information before committing them.

## Dependencies

Python dependencies are listed in `requirements.txt`. Geospatial packages such as GeoPandas, Fiona, Rasterio, Shapely and PyProj may require compatible binary wheels for your Python version and operating system.

## Author

Nouman Saleem  
GIS Specialist

## Disclaimer

This repository is provided as a software project. It is not an official PEL publication or endorsement unless separately authorized. Users are responsible for verifying data rights, data quality, coordinate reference systems, and analysis results.
