# Fern

A prototype crop-planning dashboard for Nevada fields. Enter a latitude/longitude and planting history to view nearby land and climate data and three crop plans: profit-oriented, land-health-oriented, and balanced.

## Run locally

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

The prepared files in `data/` and the model in `model/` are included. Without the model, the app still runs with a neutral ML score. To regenerate the data files from the original merged CSV:

```powershell
python scripts\prepare_nevada.py --csv "D:\path\to\merged_data_2016_2025_filtered.csv" --out data
```

The original merged CSV is not included.

## Notes and limitations

- The dataset currently covers only 26 cells. Pins far from a cell receive a regional-estimate warning.
- Crop prices and costs in `crops.csv` are placeholders. Replace them with verified local figures before relying on profit rankings.
- Scores are prototype comparisons, not agronomic, financial, or operational advice.
- `model/crop_model.json` is about 69 MB. GitHub allows files below 100 MB but warns for files larger than 50 MB; Git LFS is an option if the model grows.

## Configuration

- `MODEL_WEIGHT` controls the ML model share of crop suitability (default: `0.3`).
- `DATA_DIR` and `MODEL_DIR` override the default `data/` and `model/` directories.

## License

No license is provided. All rights are reserved; public visibility does not grant permission to reuse the code or assets.
