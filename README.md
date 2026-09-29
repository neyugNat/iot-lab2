# 📡 IoT Lab 2 — Thu thập, Lưu trữ và Tiền xử lý Dữ liệu IoT

> **Học phần:** IoT và Ứng dụng (INT14149) — PTIT  
> **Bài thực hành số 2** · 04 tiết thực hành

---

## 📐 Kiến trúc hệ thống

```
 VS Code + Wokwi Extension                    Docker Desktop
┌─────────────────────────────┐          ┌──────────────────────┐
│  ESP32 (mô phỏng)          │          │  Mosquitto (MQTT)    │
│  ├── DHT22  (nhiệt độ/ẩm)  │──MQTT──▶│  port 1884           │
│  ├── HC-SR04 (khoảng cách)  │         └──────────┬───────────┘
│  └── LED xanh (heartbeat)   │                    │
└─────────────────────────────┘                    │ subscribe
                                                   ▼
                                         ┌──────────────────────┐
        Terminal 1                       │  mqtt_subscriber.py  │
       ┌─────────────┐                  │  validate + latency  │
       │ Python      │──────write──────▶│                      │
       └─────────────┘                  └──────────┬───────────┘
                                                   │ write
        Terminal 2                                  ▼
       ┌─────────────┐                  ┌──────────────────────┐
       │ preprocess   │◀────query───────│  InfluxDB 2.x        │
       │ .py          │────write───────▶│  port 8086           │
       └─────────────┘                  │  ┌────────────────┐  │
                                        │  │ sensor_data    │  │
        Terminal 3                      │  │ (raw)          │  │
       ┌─────────────┐                  │  ├────────────────┤  │
       │ Streamlit   │◀────query───────│  │ sensor_data_   │  │
       │ Dashboard   │                  │  │ processed      │  │
       │ :8501       │                  │  └────────────────┘  │
       └─────────────┘                  └──────────────────────┘
```

**Luồng dữ liệu:**  
ESP32 → *MQTT publish* → Mosquitto → *MQTT subscribe* → `mqtt_subscriber.py` → *Write API* → InfluxDB → *Query API* → Dashboard

---

## 📁 Cấu trúc thư mục

```
iot-lab2/
│
├── firmware/                        # 🔌 Firmware ESP32 (Arduino / PlatformIO)
│   ├── sketch.ino                   #   Code chính: đọc cảm biến, publish MQTT
│   ├── platformio.ini               #   Cấu hình PlatformIO (board, lib_deps)
│   ├── diagram.json                 #   Sơ đồ mạch Wokwi (ESP32 + DHT22 + HC-SR04 + LED)
│   ├── wokwi.toml                   #   Cấu hình Wokwi simulator
│   ├── src/main.cpp                 #   Entry point PlatformIO
│   ├── build.ps1                    #   Script build (PowerShell, xử lý Unicode path)
│   └── build.cmd                    #   Script build (CMD wrapper)
│
├── backend/                         # 🐍 Backend Python
│   ├── config.py                    #   ⚙️ Cấu hình chung (MQTT, InfluxDB, thông số)
│   ├── mqtt_subscriber.py           #   📡 Thu thập: MQTT subscribe → validate → ghi InfluxDB
│   ├── preprocessing.py             #   🔬 Tiền xử lý: clean → outlier → resample → normalize
│   ├── dashboard.py                 #   📊 Dashboard giám sát Streamlit (4 tab)
│   └── requirements.txt             #   📦 Thư viện Python
│
├── mosquitto/
│   └── mosquitto.conf               #   ⚙️ Cấu hình MQTT Broker
│
├── docker-compose.yml               #   🐳 Docker: Mosquitto + InfluxDB
├── .gitignore
└── README.md                        #   📝 File này
```

---

## ⚙️ Yêu cầu phần mềm

| Phần mềm | Phiên bản | Ghi chú |
|-----------|-----------|---------|
| **Docker Desktop** | ≥ 20.x | Chạy Mosquitto + InfluxDB |
| **VS Code** | Mới nhất | IDE chính |
| **PlatformIO IDE** (extension) | Mới nhất | Build firmware ESP32 |
| **Wokwi Simulator** (extension) | Mới nhất | Mô phỏng phần cứng |
| **Python** | ≥ 3.10 | Backend scripts |

---

## 🚀 Hướng dẫn chạy

### Bước 1 · Cài đặt ban đầu (chỉ 1 lần)

```bash
# Cài Wokwi license trong VS Code
# Nhấn F1 → "Wokwi: Request a New License" → đăng nhập → dán token

# Cài thư viện Python
cd backend
pip install -r requirements.txt
```

### Bước 2 · Khởi động Mosquitto + InfluxDB

```bash
docker-compose up -d
```

Kiểm tra: `docker ps` — phải thấy 2 container `iot_lab2_mosquitto` và `iot_lab2_influxdb`.

- **InfluxDB UI:** http://localhost:8086 (user: `admin` / pass: `iotlab2password`)

### Bước 3 · Chạy MQTT Subscriber (Terminal 1)

```bash
cd backend
python mqtt_subscriber.py
```

Khi thành công sẽ hiện: `Subscribed to 'iot/lab2/+/telemetry'`

### Bước 4 · Chạy Firmware ESP32 trên Wokwi (VS Code)

1. **Mở folder** `firmware/` trong VS Code (chứa `platformio.ini`)
2. **Build:** Click ✓ trên status bar (hoặc `pio run` hoặc `.\build.cmd`)
3. **Simulate:** Nhấn `F1` → `Wokwi: Start Simulator`

Mạch mô phỏng hiện ra gồm:
- **ESP32 DevKit V1** — vi điều khiển chính
- **DHT22** — cảm biến nhiệt độ / độ ẩm (click để kéo thanh trượt)
- **HC-SR04** — cảm biến khoảng cách siêu âm (click để kéo thanh trượt)
- **LED xanh** — nhấp nháy mỗi 5s khi publish MQTT thành công

Serial Monitor hiện: `topic=iot/lab2/esp32-01/telemetry publish=OK payload={...}`

### Bước 5 · Chạy tiền xử lý (Terminal 2)

```bash
cd backend

# Xử lý 1 lần
python preprocessing.py

# Hoặc chạy liên tục mỗi 60 giây
python preprocessing.py --continuous
```

### Bước 6 · Mở Dashboard (Terminal 3)

```bash
cd backend
streamlit run dashboard.py
```

Mở trình duyệt → **http://localhost:8501**

| Tab | Nội dung |
|-----|----------|
| 📊 Tổng quan | KPI cards + biểu đồ 3 cảm biến real-time |
| 📈 Dữ liệu thô | Biểu đồ riêng từng sensor + bảng dữ liệu |
| 🔬 Dữ liệu đã xử lý | So sánh trước/sau, rolling mean, chuẩn hóa Min-Max |
| ⏱ Phân tích độ trễ | Histogram, box-plot, P50/P95/Max |

---

## 📊 Schema Database (InfluxDB 2.x)

### Bucket `sensor_data` — Dữ liệu thô

| Loại | Tên | Kiểu | Mô tả |
|------|-----|------|-------|
| Measurement | `telemetry` | — | Điểm dữ liệu từ ESP32 |
| Tag | `device_id` | string | Mã thiết bị (`esp32-01`) |
| Tag | `boot_id` | string | ID phiên khởi động |
| Field | `temperature_c` | float | Nhiệt độ (°C) |
| Field | `humidity_pct` | float | Độ ẩm (%) |
| Field | `distance_cm` | float | Khoảng cách (cm) |
| Field | `rssi_dbm` | int | Cường độ WiFi (dBm) |
| Field | `latency_ms` | int | Độ trễ end-to-end (ms) |
| Field | `sequence` | int | Số thứ tự message |
| Field | `uptime_s` | int | Thời gian hoạt động (s) |
| Field | `led_on` | bool | Trạng thái LED |
| Field | `sent_at_ms` | int | Timestamp gửi (epoch ms) |

**Retention Policy:** 7 ngày

### Bucket `sensor_data_processed` — Dữ liệu đã xử lý

| Loại | Tên | Mô tả |
|------|-----|-------|
| Measurement | `telemetry_processed` | Sau tiền xử lý |
| Field | `*_outlier` | Cờ outlier (IQR + Z-score) |
| Field | `*_rolling_mean` | Trung bình trượt (window=6) |
| Field | `*_rolling_std` | Độ lệch chuẩn trượt |
| Field | `*_delta` | Sai phân bậc 1 |
| Field | `*_rate` | Tốc độ thay đổi |
| Field | `*_norm_minmax` | Chuẩn hóa Min-Max [0,1] |
| Field | `*_norm_zscore` | Chuẩn hóa Z-score |

---

## 🔬 Pipeline tiền xử lý

```
Dữ liệu thô (InfluxDB sensor_data)
    │
    ▼
1. Xử lý giá trị thiếu (Linear Interpolation)
    │
    ▼
2. Phát hiện Outlier (IQR × 1.5 + Z-score > 3σ) → thay bằng interpolation
    │
    ▼
3. Resampling (10s intervals, mean aggregation)
    │
    ▼
4. Feature Engineering
   ├── Rolling Mean (window=6 ≈ 30s)
   ├── Rolling Std
   ├── Delta (first difference)
   └── Rate of change
    │
    ▼
5. Chuẩn hóa (Min-Max [0,1] + Z-score)
    │
    ▼
Dữ liệu đã xử lý (InfluxDB sensor_data_processed)
```

---

## 📦 JSON Payload (ESP32 → MQTT)

```json
{
  "schema_version": 1,
  "device_id": "esp32-01",
  "boot_id": "A1B2C3D4E5F6G7H8",
  "sequence": 42,
  "sent_at_ms": 1704067200000,
  "temperature_c": 25.30,
  "humidity_pct": 60.10,
  "distance_cm": 47.52,
  "rssi_dbm": -45,
  "uptime_s": 210,
  "led_on": true
}
```

---

## 🛑 Dừng hệ thống

```bash
# Ctrl+C trong mỗi terminal (subscriber, preprocessing, dashboard)

# Dừng Docker
docker-compose down

# Xóa hoàn toàn dữ liệu
docker-compose down -v
```

---

## 🐛 Xử lý sự cố

| Vấn đề | Giải pháp |
|--------|-----------|
| Wokwi: MQTT `failed (state=-2)` | `docker-compose up -d` — đảm bảo Mosquitto chạy |
| Subscriber: `Connection refused` | `docker-compose up -d mosquitto` → đợi 5s |
| Dashboard: `InfluxDB Offline` | `docker-compose up -d influxdb` → đợi 10s |
| Dashboard: tab "Đã xử lý" trống | Chạy `python preprocessing.py` trước |
| Build lỗi Unicode path | Dùng `.\build.cmd` thay vì `pio run` |
| Streamlit hỏi email | Nhấn Enter bỏ qua |

---

## 📝 Công nghệ sử dụng

| Thành phần | Công nghệ |
|-----------|-----------|
| Vi điều khiển | ESP32 DevKit V1 (Wokwi simulator) |
| Cảm biến | DHT22 (nhiệt độ/ẩm), HC-SR04 (khoảng cách) |
| MQTT Broker | Eclipse Mosquitto 2 (Docker) |
| Database | InfluxDB 2.x — time-series (Docker) |
| Thu thập dữ liệu | Python 3 + paho-mqtt |
| Tiền xử lý | pandas, numpy, scikit-learn |
| Dashboard | Streamlit + Plotly |
| Build hệ thống | PlatformIO, Docker Compose |
