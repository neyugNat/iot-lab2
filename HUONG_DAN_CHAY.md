# 📘 HƯỚNG DẪN CHẠY DỰ ÁN — Bài Thực hành số 2 IoT

> **Mục tiêu:** Chạy toàn bộ hệ thống từ firmware ESP32 (mô phỏng Wokwi trên VS Code)
> đến backend thu thập dữ liệu, tiền xử lý, và dashboard giám sát real-time.

---

## 📐 Tổng quan luồng hoạt động

```
 VS Code + Wokwi Extension                    Docker Desktop
┌─────────────────────────────┐          ┌──────────────────────┐
│  ESP32 (mô phỏng)          │          │  Mosquitto (MQTT)    │
│  ├── DHT22  (nhiệt độ/ẩm)  │──MQTT──▶│  port 1884           │
│  ├── HC-SR04 (khoảng cách)  │         └──────────┬───────────┘
│  └── LED xanh               │                    │
└─────────────────────────────┘                    │
                                                   ▼
                                         ┌──────────────────────┐
        Terminal 1                       │  mqtt_subscriber.py  │
       ┌─────────────┐                  │  (subscribe + ghi DB)│
       │ python      │◀────subscribe────┤                      │
       │ mqtt_sub... │──────write──────▶│  InfluxDB 2.x        │
       └─────────────┘                  │  port 8086           │
                                         └──────────┬───────────┘
        Terminal 2                                  │
       ┌─────────────┐                              │
       │ python      │◀─────────query───────────────┘
       │ preprocess..│───────write processed────────▶ InfluxDB
       └─────────────┘
                                         
        Terminal 3                       
       ┌─────────────┐                  
       │ streamlit   │◀─────query───── InfluxDB
       │ dashboard   │                  
       │ :8501       │ ◀── Mở trình duyệt
       └─────────────┘                  
```

---

## 🔧 Phần 1 — Cài đặt phần mềm (chỉ làm 1 lần)

### 1.1. Docker Desktop

1. Tải tại: https://www.docker.com/products/docker-desktop/
2. Cài đặt → khởi động lại máy nếu được yêu cầu
3. Mở **Docker Desktop** → đợi đến khi icon ở taskbar hiện **xanh lá** (Engine running)

> ⚠️ Nếu Windows yêu cầu bật **WSL 2**, làm theo hướng dẫn trên màn hình.

### 1.2. Visual Studio Code

1. Tải tại: https://code.visualstudio.com/
2. Cài đặt bình thường

### 1.3. Extensions cần thiết trên VS Code

Mở VS Code → nhấn `Ctrl+Shift+X` (Extensions) → tìm và cài các extension sau:

| Extension | Tên trên Marketplace | Bắt buộc |
|-----------|----------------------|----------|
| **PlatformIO IDE** | `platformio.platformio-ide` | ✅ |
| **Wokwi Simulator** | `wokwi.wokwi-vscode` | ✅ |

> Sau khi cài **PlatformIO**, VS Code sẽ tự tải thêm toolchain. Đợi cho thanh tiến trình ở
> góc dưới bên phải hoàn tất (có thể mất 2-5 phút lần đầu).

### 1.4. Kích hoạt Wokwi License (miễn phí)

1. Nhấn `F1` trong VS Code → gõ `Wokwi: Request a New License`
2. Trình duyệt sẽ mở trang đăng nhập Wokwi → đăng nhập (GitHub/Google)
3. Sao chép token → dán vào VS Code khi được hỏi
4. VS Code hiện thông báo **"License activated successfully"** → hoàn tất

### 1.5. Python 3.10+

1. Tải tại: https://www.python.org/downloads/
2. Khi cài, **☑️ tick "Add Python to PATH"**
3. Kiểm tra bằng PowerShell:
   ```powershell
   python --version
   # Kết quả: Python 3.1x.x
   ```

---

## 🐳 Phần 2 — Khởi động Mosquitto + InfluxDB (Docker)

### 2.1. Mở PowerShell tại thư mục dự án

```powershell
cd C:\Users\Admin\Downloads\firmware
```

### 2.2. Khởi động Docker containers

```powershell
docker-compose up -d
```

Kết quả thành công:
```
Creating iot_lab2_mosquitto ... done
Creating iot_lab2_influxdb  ... done
```

### 2.3. Kiểm tra containers đang chạy

```powershell
docker ps
```

Phải thấy 2 container:
```
CONTAINER ID   IMAGE                 STATUS    PORTS
xxxxxxxxxxxx   eclipse-mosquitto:2   Up        0.0.0.0:1884->1883/tcp
xxxxxxxxxxxx   influxdb:2            Up        0.0.0.0:8086->8086/tcp
```

### 2.4. (Tùy chọn) Kiểm tra InfluxDB UI

- Mở trình duyệt → vào **http://localhost:8086**
- Đăng nhập: `admin` / `iotlab2password`
- Vào **Explore** → chọn bucket `sensor_data` → sẽ thấy dữ liệu sau khi firmware chạy

---

## 🐍 Phần 3 — Cài thư viện Python

```powershell
cd C:\Users\Admin\Downloads\firmware\backend
pip install -r requirements.txt
```

Kết quả: cài xong `paho-mqtt`, `influxdb-client`, `pandas`, `numpy`, `scikit-learn`,
`streamlit`, `plotly`.

---

## 📡 Phần 4 — Chạy MQTT Subscriber (Terminal 1)

> **Giữ terminal này mở suốt quá trình demo.**

```powershell
cd C:\Users\Admin\Downloads\firmware\backend
python mqtt_subscriber.py
```

Khi khởi động thành công sẽ hiện:
```
2026-09-29 17:20:00 [INFO] Created InfluxDB bucket 'sensor_data'
2026-09-29 17:20:00 [INFO] InfluxDB bucket 'sensor_data_processed' already exists
2026-09-29 17:20:00 [INFO] Connecting to MQTT broker localhost:1884 …
2026-09-29 17:20:00 [INFO] Connected to MQTT broker at localhost:1884
2026-09-29 17:20:00 [INFO] Subscribed to 'iot/lab2/+/telemetry'
```

> Script đang chờ nhận dữ liệu từ ESP32. Sang bước tiếp để chạy firmware.

---

## 🔌 Phần 5 — Chạy Firmware ESP32 trên Wokwi (VS Code)

Đây là phần quan trọng nhất — mô phỏng phần cứng ESP32 với cảm biến ngay trong VS Code.

### 5.1. Mở thư mục firmware trong VS Code

```
File → Open Folder → chọn C:\Users\Admin\Downloads\firmware\firmware
```

> ⚠️ Mở đúng thư mục `firmware\firmware` (thư mục con chứa `platformio.ini`),
> **KHÔNG** mở thư mục gốc `firmware\`.

### 5.2. Build firmware bằng PlatformIO

**Cách 1 — Dùng nút trên thanh status bar:**
- Ở thanh dưới cùng VS Code, click biểu tượng **✓** (PlatformIO: Build)

**Cách 2 — Dùng Terminal:**
```powershell
# Trong VS Code terminal (Ctrl+`)
pio run
```

**Cách 3 — Dùng script đi kèm:**
```powershell
.\build.cmd
```

Đợi cho đến khi hiện:
```
========================= [SUCCESS] ========================
Environment    Status    Duration
-------------  --------  ------------
esp32dev       SUCCESS   xx.xxs
```

> Lần build đầu tiên sẽ lâu hơn (tải toolchain + thư viện). Các lần sau nhanh hơn.

### 5.3. Khởi động Wokwi Simulator

1. Nhấn **`F1`** → gõ **`Wokwi: Start Simulator`** → Enter

2. VS Code sẽ mở một panel mới hiển thị mạch điện gồm:

   ```
   ┌─────────────────────────────────────────────────┐
   │              Wokwi Simulator                     │
   │                                                  │
   │    ┌──────────┐        ┌──────────────┐          │
   │    │ HC-SR04  │        │   DHT22      │          │
   │    │(siêu âm) │        │(nhiệt độ/ẩm) │          │
   │    └────┬─────┘        └──────┬───────┘          │
   │         │                     │                   │
   │    ┌────┴─────────────────────┴───────┐          │
   │    │        ESP32 DevKit V1           │          │
   │    │                                  │          │
   │    └────────────────┬─────────────────┘          │
   │                     │                             │
   │               ┌─────┴─────┐                      │
   │               │  LED (xanh)│                      │
   │               │  + 220Ω   │                      │
   │               └───────────┘                      │
   │                                                  │
   │  [Serial Monitor]                                │
   │  > Lab 2 device ready: device_id=esp32-01 ...    │
   │  > Connecting WiFi to Wokwi-GUEST ...            │
   │  > WiFi connected, IP=...                        │
   │  > NTP synchronization requested (UTC)           │
   │  > topic=iot/lab2/esp32-01/telemetry publish=OK  │
   └─────────────────────────────────────────────────┘
   ```

3. **Tương tác với cảm biến mô phỏng:**
   - Click vào **DHT22** → kéo thanh trượt để thay đổi nhiệt độ / độ ẩm
   - Click vào **HC-SR04** → kéo thanh trượt để thay đổi khoảng cách
   - Quan sát LED xanh nhấp nháy

4. **Quan sát Serial Monitor** (panel phía dưới): mỗi 5 giây ESP32 gửi 1 message MQTT

### 5.4. Xác nhận dữ liệu đang chảy

Quay lại **Terminal 1** (mqtt_subscriber), phải thấy log liên tục:
```
2026-09-29 17:21:05 [INFO] seq=1 device=esp32-01  T=25.0°C  H=50.0%  D=100.0cm  latency=45ms
2026-09-29 17:21:10 [INFO] seq=2 device=esp32-01  T=25.0°C  H=50.0%  D=100.0cm  latency=42ms
2026-09-29 17:21:15 [INFO] seq=3 device=esp32-01  T=25.0°C  H=50.0%  D=100.0cm  latency=38ms
...
```

> ✅ Nếu thấy log như trên → pipeline thu thập dữ liệu đã hoạt động!

---

## 🔬 Phần 6 — Chạy Tiền xử lý dữ liệu (Terminal 2)

> Mở **terminal PowerShell mới** (giữ Terminal 1 chạy nền).

```powershell
cd C:\Users\Admin\Downloads\firmware\backend

# Chạy 1 lần — xử lý dữ liệu 1 giờ gần nhất
python preprocessing.py

# HOẶC chạy liên tục — tự động xử lý mỗi 60 giây
python preprocessing.py --continuous
```

Kết quả:
```
2026-09-29 17:25:00 [INFO] ============================================================
2026-09-29 17:25:00 [INFO] Starting preprocessing pipeline (last 1 h)
2026-09-29 17:25:00 [INFO] ============================================================
2026-09-29 17:25:00 [INFO] Read 120 raw records (last 1 h)
2026-09-29 17:25:00 [INFO] Missing values: 0 → 0 (filled 0)
2026-09-29 17:25:00 [INFO]   temperature_c: 2 outliers replaced
2026-09-29 17:25:00 [INFO]   humidity_pct: 0 outliers replaced
2026-09-29 17:25:00 [INFO]   distance_cm: 1 outliers replaced
2026-09-29 17:25:00 [INFO] Total outliers detected and fixed: 3
2026-09-29 17:25:00 [INFO] Resampled 120 → 60 records (interval=10s)
2026-09-29 17:25:00 [INFO] Created rolling/delta/rate features (window=6)
2026-09-29 17:25:00 [INFO] Applied MinMax and Z-score normalisation
2026-09-29 17:25:00 [INFO] Wrote 60 processed records to 'sensor_data_processed'
2026-09-29 17:25:00 [INFO] Pipeline complete: {'status': 'ok', ...}
```

> 💡 **Mẹo demo:** Kéo thanh trượt DHT22 trên Wokwi thay đổi nhiệt độ đột ngột (ví dụ
> từ 25°C lên 75°C) để tạo outlier → chạy lại preprocessing → thấy outlier bị phát hiện.

---

## 📊 Phần 7 — Mở Dashboard giám sát (Terminal 3)

> Mở **terminal PowerShell mới** (giữ Terminal 1 + 2 chạy nền).

```powershell
cd C:\Users\Admin\Downloads\firmware\backend
streamlit run dashboard.py
```

Kết quả:
```
  You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
```

**Mở trình duyệt** → vào **http://localhost:8501**

### Các tab trên Dashboard:

| Tab | Nội dung |
|-----|----------|
| **📊 Tổng quan** | 5 KPI cards (nhiệt độ, độ ẩm, khoảng cách, latency, RSSI) + biểu đồ real-time |
| **📈 Dữ liệu thô** | Biểu đồ riêng từng cảm biến + bảng 50 bản ghi gần nhất |
| **🔬 Dữ liệu đã xử lý** | So sánh trước/sau xử lý, rolling mean, dữ liệu chuẩn hóa |
| **⏱ Phân tích độ trễ** | Histogram, box-plot, P50/P95/Max latency |

> Dashboard tự động làm mới mỗi 5 giây. Có thể tắt/chỉnh trong sidebar bên trái.

---

## 🎬 Phần 8 — Quy trình demo đầy đủ

Khi demo bài thực hành, mở các cửa sổ cạnh nhau theo thứ tự:

```
┌─────────────────────────┬─────────────────────────┐
│  VS Code (Wokwi)        │  Trình duyệt            │
│  ┌───────────────────┐  │  ┌───────────────────┐  │
│  │ Mạch ESP32 +      │  │  │ Dashboard         │  │
│  │ DHT22 + HC-SR04   │  │  │ (localhost:8501)  │  │
│  │ + LED             │  │  │                   │  │
│  │                   │  │  │ Biểu đồ real-time │  │
│  │ [Serial Monitor]  │  │  │ đang cập nhật     │  │
│  └───────────────────┘  │  └───────────────────┘  │
├─────────────────────────┤                         │
│  Terminal 1: subscriber │                         │
│  > seq=42 T=26.3°C ...  │                         │
├─────────────────────────┤                         │
│  Terminal 2: preprocess │                         │
│  > Wrote 60 records ... │                         │
└─────────────────────────┴─────────────────────────┘
```

**Kịch bản demo gợi ý:**

1. Cho firmware chạy bình thường ~30 giây → dữ liệu ổn định
2. Kéo thanh trượt **DHT22** thay đổi nhiệt độ từ 25°C → 60°C → quay lại 25°C
3. Kéo thanh trượt **HC-SR04** thay đổi khoảng cách
4. Chạy `python preprocessing.py` → xem outlier được phát hiện
5. Chuyển qua tab **"Dữ liệu đã xử lý"** trên Dashboard → xem so sánh trước/sau
6. Chuyển tab **"Phân tích độ trễ"** → xem histogram latency

---

## 🛑 Dừng hệ thống

```powershell
# Dừng Dashboard:     Ctrl+C trong Terminal 3
# Dừng Preprocessing: Ctrl+C trong Terminal 2
# Dừng Subscriber:    Ctrl+C trong Terminal 1

# Dừng Docker containers:
cd C:\Users\Admin\Downloads\firmware
docker-compose down

# Nếu muốn XÓA hoàn toàn dữ liệu (volumes):
docker-compose down -v
```

---

## ❗ Xử lý lỗi thường gặp

### Wokwi không kết nối được MQTT

```
Connecting MQTT to host.wokwi.internal:1884... failed (state=-2)
```

**Nguyên nhân:** Docker Mosquitto chưa chạy hoặc port 1884 bị chặn.

**Giải pháp:**
```powershell
# Kiểm tra Mosquitto đang chạy
docker ps | findstr mosquitto

# Nếu không thấy → khởi động lại
cd C:\Users\Admin\Downloads\firmware
docker-compose up -d
```

---

### PlatformIO build lỗi "command not found"

**Giải pháp:** Đợi PlatformIO IDE extension cài đặt xong (xem thanh tiến trình góc dưới
phải VS Code). Hoặc chạy build bằng script:
```powershell
.\build.cmd
```

---

### Subscriber báo "Connection refused"

```
ConnectionRefusedError: [Errno 10061]
```

**Nguyên nhân:** Mosquitto chưa chạy.

**Giải pháp:**
```powershell
docker-compose up -d mosquitto
# Đợi 5 giây rồi chạy lại subscriber
python mqtt_subscriber.py
```

---

### Dashboard hiện "InfluxDB Offline"

**Giải pháp:**
```powershell
docker-compose up -d influxdb
# Đợi 10 giây → refresh trang dashboard
```

---

### Build lỗi do đường dẫn có tiếng Việt / Unicode

**Giải pháp:** Script `build.ps1` tự động xử lý bằng cách tạo junction ASCII tạm thời.
Dùng `.\build.cmd` hoặc `.\build.ps1` thay vì `pio run` trực tiếp.

---

### Dashboard trắng / không có dữ liệu

**Nguyên nhân:** Chưa có dữ liệu trong InfluxDB.

**Giải pháp:** Đảm bảo thứ tự chạy đúng:
1. ✅ Docker đang chạy (`docker ps`)
2. ✅ `mqtt_subscriber.py` đang chạy và hiện log "Subscribed"
3. ✅ Wokwi simulator đang chạy và Serial Monitor hiện "publish=OK"
4. Đợi ít nhất 10-15 giây → refresh Dashboard

---

## 📋 Tóm tắt nhanh — Checklist trước khi demo

- [ ] Docker Desktop đang chạy (icon xanh ở taskbar)
- [ ] `docker-compose up -d` thành công (2 container)
- [ ] `pip install -r requirements.txt` đã cài xong
- [ ] Terminal 1: `python mqtt_subscriber.py` → hiện "Subscribed"
- [ ] VS Code: mở folder `firmware\firmware` → build thành công
- [ ] VS Code: `F1` → `Wokwi: Start Simulator` → thấy mạch điện + Serial Monitor
- [ ] Terminal 1: thấy log `seq=1 device=esp32-01 T=... latency=...`
- [ ] Terminal 2: `python preprocessing.py` → "Pipeline complete"
- [ ] Terminal 3: `streamlit run dashboard.py` → mở http://localhost:8501
- [ ] Dashboard hiện dữ liệu real-time ở cả 4 tab
