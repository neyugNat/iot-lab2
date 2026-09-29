#!/usr/bin/env python3
"""MQTT → InfluxDB subscriber.

Subscribes to the telemetry topic, validates incoming JSON, and writes
each message as a point in InfluxDB.  Latency (receive_time − sent_at)
is stored alongside the sensor data so it can be analysed later.

Usage:
    python mqtt_subscriber.py
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, BucketRetentionRules
from influxdb_client.client.write_api import SYNCHRONOUS

import config

# ──────────────────────────── Logging ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("mqtt_subscriber")

# ──────────────────────────── Counters ────────────────────────
stats = {
    "received": 0,
    "valid": 0,
    "invalid": 0,
    "written": 0,
    "errors": 0,
}


# ──────────────────────────── InfluxDB setup ──────────────────
def ensure_bucket(client: InfluxDBClient, bucket_name: str) -> None:
    """Create *bucket_name* if it does not already exist."""
    buckets_api = client.buckets_api()
    existing = buckets_api.find_bucket_by_name(bucket_name)
    if existing is None:
        org_id = client.organizations_api().find_organizations(
            org=config.INFLUXDB_ORG
        )[0].id
        retention = BucketRetentionRules(
            type="expire",
            every_seconds=config.INFLUXDB_RETENTION_HOURS * 3600,
        )
        buckets_api.create_bucket(
            bucket_name=bucket_name,
            retention_rules=retention,
            org_id=org_id,
        )
        log.info("Created InfluxDB bucket '%s'", bucket_name)
    else:
        log.info("InfluxDB bucket '%s' already exists", bucket_name)


influx_client = InfluxDBClient(
    url=config.INFLUXDB_URL,
    token=config.INFLUXDB_TOKEN,
    org=config.INFLUXDB_ORG,
)
ensure_bucket(influx_client, config.INFLUXDB_BUCKET_RAW)
ensure_bucket(influx_client, config.INFLUXDB_BUCKET_PROCESSED)

write_api = influx_client.write_api(write_options=SYNCHRONOUS)


# ──────────────────────────── Validation ──────────────────────
REQUIRED_FIELDS = {
    "device_id", "boot_id", "sequence", "sent_at_ms",
    "temperature_c", "humidity_pct", "distance_cm",
    "rssi_dbm", "uptime_s",
}


def validate_payload(data: dict) -> list[str]:
    """Return a list of human-readable validation errors (empty = OK)."""
    errors: list[str] = []

    # Check required keys
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        errors.append(f"Missing fields: {missing}")
        return errors          # can't validate values without keys

    # Range checks
    t = data["temperature_c"]
    if not isinstance(t, (int, float)) or t < config.MIN_TEMPERATURE_C or t > config.MAX_TEMPERATURE_C:
        errors.append(f"temperature_c out of range: {t}")

    h = data["humidity_pct"]
    if not isinstance(h, (int, float)) or h < config.MIN_HUMIDITY_PCT or h > config.MAX_HUMIDITY_PCT:
        errors.append(f"humidity_pct out of range: {h}")

    d = data["distance_cm"]
    if not isinstance(d, (int, float)) or d < config.MIN_DISTANCE_CM or d > config.MAX_DISTANCE_CM:
        errors.append(f"distance_cm out of range: {d}")

    seq = data["sequence"]
    if not isinstance(seq, int) or seq < 0:
        errors.append(f"sequence invalid: {seq}")

    return errors


# ──────────────────────────── MQTT callbacks ──────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to MQTT broker at %s:%d", config.MQTT_BROKER, config.MQTT_PORT)
        client.subscribe(config.MQTT_TOPIC_SUBSCRIBE, qos=1)
        log.info("Subscribed to '%s'", config.MQTT_TOPIC_SUBSCRIBE)
    else:
        log.error("MQTT connection failed with code %d", rc)


def on_message(client, userdata, msg):
    receive_ms = int(time.time() * 1000)
    stats["received"] += 1

    # ── Parse JSON ────────────────────────────────────────────
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        stats["invalid"] += 1
        log.warning("Malformed payload on %s: %s", msg.topic, exc)
        return

    # ── Validate ──────────────────────────────────────────────
    errors = validate_payload(data)
    if errors:
        stats["invalid"] += 1
        log.warning("Validation failed for %s: %s", msg.topic, "; ".join(errors))
        return
    stats["valid"] += 1

    # ── Compute latency ──────────────────────────────────────
    sent_at_ms = int(data["sent_at_ms"])
    latency_ms = receive_ms - sent_at_ms

    device_id = str(data["device_id"])
    log.info(
        "seq=%d device=%s  T=%.1f°C  H=%.1f%%  D=%.1fcm  latency=%dms",
        data["sequence"], device_id,
        data["temperature_c"], data["humidity_pct"],
        data["distance_cm"], latency_ms,
    )

    # ── Write to InfluxDB ─────────────────────────────────────
    point = {
        "measurement": "telemetry",
        "tags": {
            "device_id": device_id,
            "boot_id": str(data.get("boot_id", "")),
        },
        "fields": {
            "temperature_c": float(data["temperature_c"]),
            "humidity_pct": float(data["humidity_pct"]),
            "distance_cm": float(data["distance_cm"]),
            "rssi_dbm": int(data["rssi_dbm"]),
            "uptime_s": int(data["uptime_s"]),
            "sequence": int(data["sequence"]),
            "led_on": bool(data.get("led_on", False)),
            "latency_ms": latency_ms,
            "sent_at_ms": sent_at_ms,
        },
        "time": datetime.now(tz=timezone.utc),
    }

    try:
        write_api.write(bucket=config.INFLUXDB_BUCKET_RAW, record=point)
        stats["written"] += 1
    except Exception as exc:
        stats["errors"] += 1
        log.error("InfluxDB write error: %s", exc)


def on_disconnect(client, userdata, rc):
    if rc != 0:
        log.warning("Unexpected MQTT disconnect (rc=%d), will auto-reconnect", rc)


# ──────────────────────────── Main ────────────────────────────
def main() -> None:
    mqtt_client = mqtt.Client(client_id=config.MQTT_CLIENT_ID, clean_session=True)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)

    log.info("Connecting to MQTT broker %s:%d …", config.MQTT_BROKER, config.MQTT_PORT)
    mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)

    try:
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        log.info("Shutting down … stats=%s", stats)
    finally:
        mqtt_client.disconnect()
        write_api.close()
        influx_client.close()


if __name__ == "__main__":
    main()
