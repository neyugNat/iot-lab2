#!/usr/bin/env python3
"""Data preprocessing pipeline for IoT Lab 2.

Reads raw telemetry from InfluxDB, applies a full preprocessing chain
(cleaning → outlier detection → resampling → feature engineering →
normalisation), and writes the result into a separate processed bucket.

Usage:
    python preprocessing.py                   # process last 1 hour
    python preprocessing.py --hours 6         # process last 6 hours
    python preprocessing.py --continuous      # run every 60 s forever
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from sklearn.preprocessing import MinMaxScaler, StandardScaler

import config

# ──────────────────────────── Logging ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("preprocessing")

NUMERIC_COLS = ["temperature_c", "humidity_pct", "distance_cm"]


# ──────────────────────────── 1. Read raw data ────────────────
def read_raw_data(client: InfluxDBClient, hours: int) -> pd.DataFrame:
    """Query the raw bucket and return a DataFrame indexed by time."""
    query = f'''
    from(bucket: "{config.INFLUXDB_BUCKET_RAW}")
      |> range(start: -{hours}h)
      |> filter(fn: (r) => r._measurement == "telemetry")
      |> filter(fn: (r) =>
            r._field == "temperature_c" or
            r._field == "humidity_pct"   or
            r._field == "distance_cm"    or
            r._field == "rssi_dbm"       or
            r._field == "latency_ms"     or
            r._field == "sequence"
         )
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''

    query_api = client.query_api()
    tables = query_api.query_data_frame(query)

    if isinstance(tables, list):
        if len(tables) == 0:
            return pd.DataFrame()
        tables = pd.concat(tables, ignore_index=True)

    if tables.empty:
        return pd.DataFrame()

    df = tables.copy()

    # Normalise the time column
    if "_time" in df.columns:
        df["time"] = pd.to_datetime(df["_time"], utc=True)
    elif "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)

    df = df.set_index("time").sort_index()

    # Keep only the columns we care about
    keep = [c for c in NUMERIC_COLS + ["rssi_dbm", "latency_ms", "sequence", "device_id"]
            if c in df.columns]
    df = df[keep]

    # Coerce numerics
    for col in NUMERIC_COLS + ["rssi_dbm", "latency_ms", "sequence"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    log.info("Read %d raw records (last %d h)", len(df), hours)
    return df


# ──────────────────────────── 2. Handle missing values ────────
def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Detect gaps and interpolate missing values."""
    before = df.isnull().sum().sum()

    for col in NUMERIC_COLS:
        if col in df.columns:
            # Forward-fill + backward-fill for edge NaNs, then linear interp
            df[col] = df[col].interpolate(method="linear", limit_direction="both")

    after = df.isnull().sum().sum()
    log.info("Missing values: %d → %d (filled %d)", before, after, before - after)
    return df


# ──────────────────────────── 3. Outlier detection ────────────
def detect_outliers_iqr(series: pd.Series, multiplier: float) -> pd.Series:
    """Return boolean mask where True = outlier (IQR method)."""
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return (series < lower) | (series > upper)


def detect_outliers_zscore(series: pd.Series, threshold: float) -> pd.Series:
    """Return boolean mask where True = outlier (Z-score method)."""
    mean = series.mean()
    std = series.std()
    if std == 0 or pd.isna(std):
        return pd.Series(False, index=series.index)
    z_scores = ((series - mean) / std).abs()
    return z_scores > threshold


def handle_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Flag and replace outliers using both IQR and Z-score."""
    total_outliers = 0

    for col in NUMERIC_COLS:
        if col not in df.columns:
            continue

        iqr_mask = detect_outliers_iqr(df[col], config.OUTLIER_IQR_MULTIPLIER)
        z_mask = detect_outliers_zscore(df[col], config.OUTLIER_Z_THRESHOLD)

        # A point is an outlier if EITHER method flags it
        combined = iqr_mask | z_mask
        n_outliers = combined.sum()
        total_outliers += n_outliers

        # Store a flag column before replacing
        df[f"{col}_outlier"] = combined

        if n_outliers > 0:
            # Replace outliers with interpolated values
            df.loc[combined, col] = np.nan
            df[col] = df[col].interpolate(method="linear", limit_direction="both")
            log.info("  %s: %d outliers replaced", col, n_outliers)

    log.info("Total outliers detected and fixed: %d", total_outliers)
    return df


# ──────────────────────────── 4. Resampling ───────────────────
def resample_data(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Resample to a fixed time grid using mean aggregation."""
    numeric_cols_present = [c for c in NUMERIC_COLS + ["rssi_dbm", "latency_ms"]
                            if c in df.columns]
    outlier_cols = [c for c in df.columns if c.endswith("_outlier")]

    agg_dict = {col: "mean" for col in numeric_cols_present}
    for col in outlier_cols:
        agg_dict[col] = "max"          # keep True if any sample was an outlier

    resampled = df.resample(interval).agg(agg_dict)
    resampled = resampled.dropna(how="all")

    log.info("Resampled %d → %d records (interval=%s)", len(df), len(resampled), interval)
    return resampled


# ──────────────────────────── 5. Feature engineering ──────────
def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add rolling statistics and delta features."""
    window = config.ROLLING_WINDOW

    for col in NUMERIC_COLS:
        if col not in df.columns:
            continue

        # Rolling mean & std
        df[f"{col}_rolling_mean"] = df[col].rolling(window=window, min_periods=1).mean()
        df[f"{col}_rolling_std"] = df[col].rolling(window=window, min_periods=1).std().fillna(0)

        # Delta (first difference)
        df[f"{col}_delta"] = df[col].diff().fillna(0)

        # Rate of change (per-sample)
        prev = df[col].shift(1)
        df[f"{col}_rate"] = ((df[col] - prev) / prev.replace(0, np.nan)).fillna(0)

    log.info("Created rolling/delta/rate features (window=%d)", window)
    return df


# ──────────────────────────── 6. Normalisation ────────────────
def normalise_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply Min-Max and Standard scaling to numeric sensor columns."""
    for col in NUMERIC_COLS:
        if col not in df.columns:
            continue

        values = df[col].values.reshape(-1, 1)

        # Min-Max → [0, 1]
        mm = MinMaxScaler()
        df[f"{col}_norm_minmax"] = mm.fit_transform(values).flatten()

        # Standard (Z-score)
        ss = StandardScaler()
        df[f"{col}_norm_zscore"] = ss.fit_transform(values).flatten()

    log.info("Applied MinMax and Z-score normalisation")
    return df


# ──────────────────────────── 7. Write processed data ─────────
def write_processed(client: InfluxDBClient, df: pd.DataFrame) -> int:
    """Write the processed DataFrame to the processed bucket."""
    if df.empty:
        log.warning("No data to write")
        return 0

    write_api = client.write_api(write_options=SYNCHRONOUS)
    points_written = 0

    for ts, row in df.iterrows():
        fields = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                continue
            if isinstance(val, (bool, np.bool_)):
                fields[col] = bool(val)
            elif isinstance(val, (int, np.integer)):
                fields[col] = int(val)
            else:
                fields[col] = float(val)

        if not fields:
            continue

        device_id = row.get("device_id", "esp32-01") if "device_id" in df.columns else "esp32-01"

        point = {
            "measurement": "telemetry_processed",
            "tags": {"device_id": str(device_id)},
            "fields": fields,
            "time": ts.isoformat(),
        }
        write_api.write(bucket=config.INFLUXDB_BUCKET_PROCESSED, record=point)
        points_written += 1

    write_api.close()
    log.info("Wrote %d processed records to '%s'", points_written, config.INFLUXDB_BUCKET_PROCESSED)
    return points_written


# ──────────────────────────── Pipeline orchestrator ───────────
def run_pipeline(client: InfluxDBClient, hours: int) -> dict:
    """Execute the full preprocessing pipeline and return a summary."""
    log.info("=" * 60)
    log.info("Starting preprocessing pipeline (last %d h)", hours)
    log.info("=" * 60)

    df = read_raw_data(client, hours)
    if df.empty:
        log.warning("No raw data found — nothing to process")
        return {"status": "no_data", "rows": 0}

    raw_count = len(df)

    # Pipeline steps
    df = handle_missing_values(df)
    df = handle_outliers(df)
    df = resample_data(df, config.RESAMPLE_INTERVAL)
    df = create_features(df)
    df = normalise_data(df)

    written = write_processed(client, df)

    summary = {
        "status": "ok",
        "raw_rows": raw_count,
        "processed_rows": len(df),
        "written": written,
    }
    log.info("Pipeline complete: %s", summary)
    return summary


# ──────────────────────────── CLI ─────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="IoT data preprocessing pipeline")
    parser.add_argument("--hours", type=int, default=config.DASHBOARD_DEFAULT_HOURS,
                        help="Number of hours of history to process (default: 1)")
    parser.add_argument("--continuous", action="store_true",
                        help="Run the pipeline in a loop every 60 s")
    args = parser.parse_args()

    client = InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
    )

    try:
        if args.continuous:
            log.info("Running in continuous mode (Ctrl+C to stop)")
            while True:
                run_pipeline(client, args.hours)
                time.sleep(60)
        else:
            run_pipeline(client, args.hours)
    except KeyboardInterrupt:
        log.info("Interrupted — shutting down")
    finally:
        client.close()


if __name__ == "__main__":
    main()
