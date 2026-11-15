"""Scoring engine: land lookup + 3 plans (profit / land health / balanced)."""
import json, math, os
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("DATA_DIR", ROOT / "data"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", ROOT / "model"))
MODEL_WEIGHT = float(os.getenv("MODEL_WEIGHT", "0.3"))  # 0 = ignore the ML model, 1 = ML model only
FAR_KM = 40
DYN = ["precipitation_mm", "T2M", "T2M_MAX", "RH2M", "ALLSKY_SFC_SW_DWN", "ET_mm", "soil_moisture", "NDVI"]
EXTRA = {"Fallow/Idle Cropland": "fallow", "Grassland/Pasture": "pasture"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def num(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def trap(x, a0, o0, o1, a1):
    if x <= a0 or x >= a1: return 0.0
    if x < o0: return (x - a0) / (o0 - a0)
    if x <= o1: return 1.0
    return (a1 - x) / (a1 - o1)


def mm(d):  # min-max normalise a dict to 0..1
    lo, hi = min(d.values()), max(d.values())
    return {k: ((v - lo) / (hi - lo) if hi > lo else 1.0) for k, v in d.items()}


def cap(s): return s[:1].upper() + s[1:]


def texture(sand, silt, clay):
    if clay >= 40: return "Clay"
    if clay >= 27: return "Clay loam" if sand <= 45 else "Sandy clay loam"
    if sand >= 70: return "Sandy loam"
    if silt >= 50: return "Silt loam"
    return "Loam"


class Engine:
    def __init__(self):
        self.ok, self.error, self.model, self.model_error = False, None, None, None
        self.crops = pd.read_csv(ROOT / "crops.csv", comment="#").set_index("crop")
        try:
            self.cells = pd.read_parquet(DATA / "cells.parquet").set_index("cell_id", drop=False)
            self.series = pd.read_parquet(DATA / "cell_month_series.parquet")
            self.hist = pd.read_parquet(DATA / "crop_history.parquet")
            self.clim = self.series.groupby(["cell_id", "MONTH"])[DYN].mean()
            self.last_year = int(self.series.Year.max())
            self.ok = True
        except Exception as e:
            self.error = f"No data in {DATA}. Run scripts/prepare_nevada.py first ({e})"
        try:
            import xgboost as xgb
            self.xgb = xgb
            self.meta = json.load(open(MODEL_DIR / "meta.json"))
            self.model = xgb.Booster(); self.model.load_model(str(MODEL_DIR / "crop_model.json"))
        except Exception as e:
            self.model, self.model_error = None, str(e)

    # ---- lookups -------------------------------------------------------
    def nearest(self, lat, lon):
        c = self.cells
        la1, lo1, la2, lo2 = map(np.radians, (lat, lon, c.Latitude.values, c.Longitude.values))
        a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
        d = 6371 * 2 * np.arcsin(np.sqrt(a)); i = int(d.argmin())
        return c.iloc[i], float(d[i])

    def model_scores(self, cell, cands):
        if self.model is None: return {k: 0.5 for k in cands}, False
        F, C = self.meta["features"], self.meta["classes"]
        cl = self.clim.loc[cell.cell_id]
        X = pd.DataFrame(index=cl.index)
        for f in F:
            if f == "Year": X[f] = self.last_year
            elif f == "MONTH": X[f] = cl.index.values
            elif f in cl.columns: X[f] = cl[f].values
            else: X[f] = float(cell[f])
        p = self.model.predict(self.xgb.DMatrix(X[F].astype("float32"), feature_names=F)).mean(axis=0)
        raw = np.array([p[C.index(k)] for k in cands]) + 1e-9
        raw = raw / raw.sum()
        return dict(zip(cands, raw / raw.max())), True

    def agro(self, cell, cl, crop):
        """Temperature fit of the best planting window x soil pH fit (trapezoid membership)."""
        r = self.crops.loc[crop]
        t = cl["T2M"].reindex(range(1, 13)).interpolate().bfill().ffill().values
        k, best, start = int(r.months), -1.0, 1
        for s in range(12):
            f = trap(np.mean([t[(s + j) % 12] for j in range(k)]), r.t_abs_lo, r.t_opt_lo, r.t_opt_hi, r.t_abs_hi)
            if f > best: best, start = f, s + 1
        ph = num(cell.ph)
        pf = 0.5 if ph is None else trap(ph, r.ph_abs_lo, r.ph_opt_lo, r.ph_opt_hi, r.ph_abs_hi)
        return math.sqrt(best * pf), best, pf, start

    def rotation(self, c, hist):
        fam = lambda k: self.crops.family.get(k) if k in self.crops.index else EXTRA.get(k)
        leg = lambda k: bool(self.crops.legume.get(k, 0)) if k in self.crops.index else False
        ys = [h["crop"] for h in sorted(hist, key=lambda h: h["year"]) if h.get("crop")]
        s, note = 0.6, "no history entered, neutral"
        if ys:
            last = ys[-1]
            if c == last: s -= .4; note = f"same crop as {last}: pest/disease carry-over"
            elif fam(last) == fam(c): s -= .25; note = f"same family as {last}: carry-over risk"
            elif leg(last): s += .2; note = f"follows legume {last}: nitrogen credit"
            elif leg(c): s += .15; note = f"legume after {last}: adds nitrogen"
            else: s += .1; note = f"different family from {last}: breaks pest cycle"
            if len(ys) > 1 and fam(ys[-2]) == fam(last) == fam(c): s -= .15; note += "; third year of one family"
        return max(0., min(1., s)), note

    # ---- main ----------------------------------------------------------
    def analyze(self, lat, lon, history, plan_year):
        cell, dist = self.nearest(lat, lon)
        cl = self.clim.loc[cell.cell_id]
        cands = list(self.crops.index)
        msc, used = self.model_scores(cell, cands)
        rows = {}
        for c in cands:
            agr, tf, pf, st = self.agro(cell, cl, c)
            suit = (1 - MODEL_WEIGHT) * agr + MODEL_WEIGHT * msc[c]
            cr = self.crops.loc[c]
            rows[c] = dict(agro=agr, suit=suit, plant_month=MONTHS[st - 1],
                           net=float(cr.revenue_ac) * (0.5 + 0.5 * suit) - float(cr.cost_ac))
        feas = [c for c in cands if rows[c]["agro"] >= 0.10]
        if len(feas) < 3: feas = sorted(cands, key=lambda c: -rows[c]["agro"])[:3]

        low_om = (num(cell.om) or 9) < 1.5
        wr, ws, ww, wu = (.25, .40, .15, .20) if low_om else (.30, .30, .20, .20)
        P = mm({c: rows[c]["net"] for c in feas})                       # profit, 0..1
        W = mm({c: float(self.crops.loc[c].water_mm) for c in feas})    # water use, 0..1
        H = {}
        for c in feas:
            rows[c]["rot"], rows[c]["note"] = self.rotation(c, history)
            H[c] = wr * rows[c]["rot"] + ws * (float(self.crops.loc[c].soil_effect) + 1) / 2 + ww * (1 - W[c]) + wu * rows[c]["suit"]
        Hn = mm(H)                                                      # land health, 0..1
        B = {c: min(P[c], Hn[c]) for c in feas}  # balanced = smallest regret vs the best on both sides (maximin)

        def build(key, score):
            order = sorted(feas, key=lambda c: (-score[c], -(P[c] + Hn[c])))[:3]
            out = []
            for c in order:
                r, cr = rows[c], self.crops.loc[c]
                soil = "Builds soil" if cr.soil_effect > .3 else "Draws down soil" if cr.soil_effect < -.2 else "Neutral on soil"
                why = {"profit": [f"Est. net ${r['net']:,.0f}/acre (placeholder prices)", f"Climate + soil fit {r['suit']:.0%}", f"Best planting window starts ~{r['plant_month']}"],
                       "health": [cap(r["note"]), f"{soil}, water need ~{int(cr.water_mm)} mm", f"Climate + soil fit {r['suit']:.0%}"],
                       "balanced": [f"Profit {P[c]:.0%} / soil health {Hn[c]:.0%} of the best option", cap(r["note"]), f"Plant ~{r['plant_month']}"]}[key]
                out.append(dict(crop=c, score=float(score[c]), net=float(r["net"]), legume=bool(cr.legume), why=why))
            return {"picks": out}

        s = self.series[self.series.cell_id == cell.cell_id].sort_values(["Year", "MONTH"])
        hd = []
        for y, g in self.hist[self.hist.cell_id == cell.cell_id].groupby("Year"):
            g = g.sort_values("share", ascending=False).head(3)
            hd.append({"year": int(y), "top": [{"crop": r.CLASS_NAME, "share": float(r.share)} for r in g.itertuples()]})
        return {
            "plan_year": plan_year,
            "cell": {"id": cell.cell_id, "lat": float(cell.Latitude), "lon": float(cell.Longitude), "distance_km": dist},
            "land": {"elevation_m": num(cell.elevation_m), "slope_deg": num(cell.slope_deg), "clay": num(cell.clay), "sand": num(cell.sand),
                     "silt": num(cell.silt), "ph": num(cell.ph), "om": num(cell.om), "ksat": num(cell.ksat),
                     "texture": texture(num(cell.sand) or 0, num(cell.silt) or 0, num(cell.clay) or 0),
                     "soil_moisture": num(cl.soil_moisture.mean()), "et": num(cl.ET_mm.mean())},
            "climate": [{"month": int(m), "T2M": num(r.T2M), "T2M_MAX": num(r.T2M_MAX)} for m, r in cl.iterrows()],
            "ndvi": {"labels": [f"{int(y)}-{int(m):02d}" for y, m in zip(s.Year, s.MONTH)], "values": [num(v) for v in s.NDVI]},
            "history_db": hd, "history_user": history,
            "plans": {"profit": build("profit", P), "health": build("health", Hn), "balanced": build("balanced", B)},
            "flags": {"far": dist > FAR_KM, "low_om": bool(low_om), "model_used": used, "model_weight": MODEL_WEIGHT},
        }
