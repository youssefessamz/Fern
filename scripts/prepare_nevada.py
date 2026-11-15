"""Step 1: shrink the huge merged CSV into 3 small Nevada tables the website can query fast.

  python prepare_nevada.py --csv merged_2016_2025.csv --out data/

Outputs (parquet):
  cells.parquet             one row per grid cell: location + static soil/terrain
  cell_month_series.parquet cell x year x month means of climate / ET / soil moisture / NDVI
  crop_history.parquet      cell x year x CLASS_NAME: row count + share of that cell-year
"""
import argparse, os
import numpy as np, pandas as pd

NEVADA = dict(lat_min=35.0, lat_max=42.0, lon_min=-120.0, lon_max=-114.04)  # bounding box (approx.)
STATIC = ["elevation_m", "slope_deg", "clay", "sand", "silt", "ph", "om", "ksat"]
DYNAMIC = ["precipitation_mm", "T2M", "T2M_MAX", "RH2M", "ALLSKY_SFC_SW_DWN", "ET_mm", "soil_moisture", "NDVI"]
KEYS = ["Longitude", "Latitude", "Year", "MONTH", "CLASS_NAME"]
FEATS = STATIC + DYNAMIC

ap = argparse.ArgumentParser()
ap.add_argument("--csv", required=True)
ap.add_argument("--out", default="data")
ap.add_argument("--chunk", type=int, default=5_000_000)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

dtypes = {c: "float32" for c in FEATS + ["Longitude", "Latitude", "Year", "MONTH"]}
parts, total_in, total_kept = [], 0, 0

def compact(frames):
    return pd.concat(frames).groupby(KEYS, sort=False).sum()

for i, ch in enumerate(pd.read_csv(a.csv, usecols=KEYS + FEATS, dtype=dtypes, chunksize=a.chunk)):
    total_in += len(ch)
    ch = ch[ch.Latitude.between(NEVADA["lat_min"], NEVADA["lat_max"]) &
            ch.Longitude.between(NEVADA["lon_min"], NEVADA["lon_max"])]
    total_kept += len(ch)
    if ch.empty:
        continue
    ch = ch.copy(); ch["n"] = 1
    parts.append(ch.groupby(KEYS, sort=False)[FEATS + ["n"]].sum())   # sums -> exact means later
    if len(parts) >= 4:
        parts = [compact(parts)]
    print(f"chunk {i}: read {total_in:,} rows, kept {total_kept:,}", flush=True)

g = compact(parts).reset_index()
g["Year"] = g.Year.astype(int); g["MONTH"] = g.MONTH.astype(int)
g["cell_id"] = g.Latitude.round(4).astype(str) + "_" + g.Longitude.round(4).astype(str)

def wmean(df, by, cols):
    s = df.groupby(by)[cols + ["n"]].sum()
    return s[cols].div(s["n"], axis=0).join(s["n"]).reset_index()

# 1) static per cell
cells = wmean(g, ["cell_id", "Latitude", "Longitude"], STATIC)
# 2) monthly series per cell
series = wmean(g, ["cell_id", "Year", "MONTH"], DYNAMIC)
# 3) crop history per cell-year
ch = g.groupby(["cell_id", "Year", "CLASS_NAME"])["n"].sum().reset_index()
ch["share"] = ch.n / ch.groupby(["cell_id", "Year"]).n.transform("sum")

cells.to_parquet(f"{a.out}/cells.parquet"); series.to_parquet(f"{a.out}/cell_month_series.parquet")
ch.to_parquet(f"{a.out}/crop_history.parquet")

# diagnostics (paste these back to me)
lon, lat = np.sort(cells.Longitude.unique()), np.sort(cells.Latitude.unique())
print("\n=== DIAGNOSTICS ===")
print(f"rows read {total_in:,} | rows inside Nevada box {total_kept:,}")
print(f"cells: {len(cells):,} | years {sorted(g.Year.unique())}")
print("grid step lon/lat:", np.diff(lon).min() if len(lon) > 1 else None, np.diff(lat).min() if len(lat) > 1 else None)
print("lat range", lat.min(), lat.max(), "| lon range", lon.min(), lon.max())
print("classes per cell-year (mean):", round(ch.groupby(["cell_id", "Year"]).size().mean(), 2))
print("rows per cell-year-month (mean):", round(g.groupby(["cell_id", "Year", "MONTH"]).n.sum().mean(), 1))
print(ch.groupby("CLASS_NAME").n.sum().sort_values(ascending=False).head(15))
