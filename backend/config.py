"""Centralized configuration for the IoT Lab 2 backend services."""

# ──────────────────────────── MQTT ────────────────────────────
MQTT_BROKER = "localhost"
MQTT_PORT = 1884
MQTT_TOPIC_SUBSCRIBE = "iot/lab2/+/telemetry"   # wildcard for all devices
MQTT_CLIENT_ID = "iot-lab2-subscriber"

# ──────────────────────────── InfluxDB ────────────────────────
INFLUXDB_URL = "http://localhost:8086"
INFLUXDB_TOKEN = "iot-lab2-super-secret-token"
INFLUXDB_ORG = "iot_lab2"
INFLUXDB_BUCKET_RAW = "sensor_data"
INFLUXDB_BUCKET_PROCESSED = "sensor_data_processed"
INFLUXDB_RETENTION_HOURS = 168          # 7 days

# ──────────────────────────── Sensor ranges (validation) ─────
MIN_TEMPERATURE_C = -40.0
MAX_TEMPERATURE_C = 80.0
MIN_HUMIDITY_PCT = 0.0
MAX_HUMIDITY_PCT = 100.0
MIN_DISTANCE_CM = 2.0
MAX_DISTANCE_CM = 400.0

# ──────────────────────────── Preprocessing ───────────────────
RESAMPLE_INTERVAL = "10s"
ROLLING_WINDOW = 6                      # 6 samples ≈ 30 s at 5 s rate
OUTLIER_Z_THRESHOLD = 3.0
OUTLIER_IQR_MULTIPLIER = 1.5

# ──────────────────────────── Dashboard ───────────────────────
DASHBOARD_REFRESH_SECONDS = 5
DASHBOARD_DEFAULT_HOURS = 1
