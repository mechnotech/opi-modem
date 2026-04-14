# OPI LTE Modem Project
## Документация по настройке и конфигурации

**Дата:** Апрель 2026  
**Устройства:** Xiaomi Redmi Note 9 Pro (joyeuse) + Orange Pi Zero 3  
**Цель:** LTE модем с управлением зарядом батареи, мониторингом и WiFi точкой доступа

---

## Оглавление

1. [Архитектура системы](#архитектура)
2. [Подготовка телефона](#телефон)
3. [OPI Monitor — веб-дашборд](#dashboard)
4. [usb-autowarp.sh — скрипт инициализации](#autowarp)
5. [WiFi точка доступа](#wifi)
6. [Управление зарядом батареи (ACC)](#acc)
7. [Файловая карта](#файлы)
8. [Команды для диагностики](#диагностика)

---

## Архитектура системы {#архитектура}

```
Интернет (LTE МегаФон)
        ↓
Xiaomi Redmi Note 9 Pro
  - USB RNDIS модем (rndis0)
  - MIUI EU v14.0.3.0
  - Root (Magisk)
  - ACC — контроль заряда 40-70%
        ↓ USB кабель (ADB + RNDIS)
Orange Pi Zero 3
  - IP LAN:  192.168.10.1  (end0  → UB-X58A и др.)
  - IP WiFi: 192.168.20.1  (wlan0 → WiFi клиенты)
  - NAT/маршрутизация
  - OPI Monitor (порт 80)
  - hostapd + dnsmasq
        ↓ Ethernet
UB-X58A (основной ПК, 192.168.10.71)
```

---

## Подготовка телефона {#телефон}

### Прошивка
- **Модель:** Redmi Note 9 Pro Global (кодовое имя: **joyeuse**)
- **Прошивка:** `HMNote9ProEU_V14.0.3.0.SJZMIXM_v14-12.zip` (MIUI EU, Android 12)
- **Источник:** [xiaomi.eu](https://xiaomi.eu)
- **Метод:** Fastboot ROM, скрипт `linux_fastboot_first_install_with_data_format.sh`

### Разблокировка загрузчика
1. Привязать Mi Account к телефону
2. Включить режим разработчика → Статус разблокировки
3. Mi Unlock Tool (Windows) — ждать 168 часов
4. Подключить в Fastboot: **Power + Vol−**
5. Запустить Mi Unlock Tool → Unlock
6. Для проблем с USB: `adb reboot bootloader` надёжнее чем кнопки

### Root (Magisk)
```bash
# Установить Magisk APK
adb install Magisk.apk

# Скопировать boot.img на телефон
adb push images/boot.img /sdcard/

# В Magisk на телефоне: Установить → Выбрать файл → boot.img
# Magisk создаст magisk_patched_xxxx.img в Downloads

# Прошить патченный boot
adb pull /sdcard/Download/magisk_patched_*.img .
adb reboot bootloader
./fastboot flash boot magisk_patched_*.img
./fastboot reboot
```

### Настройки Magisk
- **Magisk → Настройки → Доступ по умолчанию для оболочки (su)** → Root
- Уведомления суперпользователя → выключить

### USB RNDIS режим
```bash
adb shell svc usb setFunctions rndis
```

---

## OPI Monitor — веб-дашборд {#dashboard}

### Расположение файлов
```
/opt/
├── opi_dashboard.py       # FastAPI бэкенд
├── static/
│   ├── index.html         # HTML интерфейс
│   ├── style.css          # Стили
│   └── app.js             # JavaScript
└── opi-dashboard-venv/    # Python venv
    └── bin/python
```

### Установка
```bash
python3 -m venv /opt/opi-dashboard-venv
/opt/opi-dashboard-venv/bin/pip install fastapi "uvicorn[standard]"
mkdir -p /opt/static
cp opi_dashboard.py /opt/
cp static/* /opt/static/
```

### Systemd сервис
**Файл:** `/etc/systemd/system/opi-dashboard.service`
```ini
[Unit]
Description=OPI Network Monitor Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt
ExecStart=/opt/opi-dashboard-venv/bin/python /opt/opi_dashboard.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now opi-dashboard
```

### Возможности дашборда
- **Батарея:** уровень, температура, ток, напряжение, статус зарядки
- **LTE сигнал:** оператор, Band (EARFCN→B1/B3/B7/B8/B20), RSRP/RSRQ/RSSI
- **Трафик:** rx/tx MB через rndis0
- **OPI:** uptime, CPU температура, load average
- **USSD:** быстрые кнопки *100#, *100*3#, *558# + произвольный код
- **SMS:** чтение inbox, отправка, очистка
- **Управление:** reboot/poweroff телефона и OPI

### API endpoints
```
GET  /api/stats          — все метрики
GET  /api/sms            — входящие SMS
POST /api/sms/send       — отправить SMS {to, body}
POST /api/sms/clear      — удалить все SMS
POST /api/ussd           — USSD запрос {code}
POST /api/phone/reboot   — перезагрузить телефон
POST /api/phone/poweroff — выключить телефон
POST /api/opi/reboot     — перезагрузить OPI
POST /api/opi/poweroff   — выключить OPI
```

### Отправка SMS
```bash
# Рабочий формат для MIUI EU / Android 12:
adb shell service call isms 5 i32 0 s16 "com.android.mms.service" \
  s16 "null" s16 "+79001234567" s16 "null" s16 '"текст сообщения"' \
  s16 "null" s16 "null"
```

### Чтение SMS через ADB
```bash
adb shell su -c "content query --uri content://sms/inbox --projection address:body:date:read"
```

### Управление зарядкой через sysfs
```bash
# Статус
adb shell su -c "cat /sys/class/power_supply/battery/charging_enabled"
adb shell su -c "cat /sys/class/power_supply/battery/capacity"
adb shell su -c "cat /sys/class/power_supply/battery/temp"  # делить на 10 = °C

# Управление
adb shell su -c "echo 0 > /sys/class/power_supply/battery/charging_enabled"  # стоп
adb shell su -c "echo 1 > /sys/class/power_supply/battery/charging_enabled"  # старт
```

---

## usb-autowarp.sh — скрипт инициализации {#autowarp}

**Файл:** `/usr/local/bin/usb-autowarp.sh`

### Systemd сервис запуска
**Файл:** `/etc/systemd/system/usb-router.service`
```ini
[Unit]
Description=Auto USB Modem Router Setup
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/usb-autowarp.sh
RemainAfterExit=yes
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

> `Type=oneshot` + `RemainAfterExit=yes` — сервис считается активным после завершения скрипта,  
> фоновые процессы (dhclient, термоцикл) остаются в его cgroup.


1. Включает красный LED — индикация процесса
2. Запускает ADB сервер
3. Переводит телефон в RNDIS режим
4. **Активирует ультраэкономию батареи** через UI автоматизацию
5. Ищет WAN интерфейс (enx..., usb..., wwan...)
6. Настраивает DHCP клиент на WAN
7. Включает IP forwarding
8. Настраивает iptables: NAT, TTL, MSS, FORWARD
9. Проверяет связь (8.8.8.8, ya.ru, 77.88.8.8)
10. Запускает фоновый цикл термоконтроля вентилятора

### Ультраэкономия батареи
```bash
# Координаты кнопки могут измениться при обновлении MIUI
adb shell "input keyevent KEYCODE_WAKEUP && wm dismiss-keyguard && \
  am start -n com.miui.securitycenter/com.miui.powercenter.PowerMainActivity && \
  sleep 1.5 && input tap 929 1234"

# Проверка результата:
adb shell settings get system power_supersave_mode_open
# должно вернуть 1
```

### Термоконтроль вентилятора
- **GPIO пин:** wPi=7 (физический 13, PC5)
- Вентилятор ВКЛ: CPU > 55°C **или** батарея > 38°C
- Вентилятор ВЫКЛ: CPU < 45°C **и** батарея < 35°C

---

## WiFi точка доступа {#wifi}

### Параметры
- **SSID:** TestAP
- **Диапазон:** 2.4GHz (hw_mode=g, channel=6)
- **IP шлюза:** 192.168.20.1
- **DHCP диапазон:** 192.168.20.10 — 192.168.20.50

### Конфиг hostapd
**Файл:** `/etc/hostapd/hostapd.conf`
```ini
interface=wlan0
driver=nl80211
ssid=TestAP
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=ПАРОЛЬ
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

### Конфиг dnsmasq (фрагмент)
**Файл:** `/etc/dnsmasq.conf`
```ini
interface=end0
dhcp-range=192.168.10.10,192.168.10.100,255.255.255.0,24h
dhcp-option=option:router,192.168.10.1
dhcp-option=option:dns-server,8.8.8.8,1.1.1.1

interface=wlan0
dhcp-range=192.168.20.10,192.168.20.50,255.255.255.0,24h
dhcp-option=3,192.168.20.1
dhcp-option=6,8.8.8.8,8.8.4.4
```

### Статический IP wlan0
**Файл:** `/etc/network/interfaces` (добавлено)
```
auto wlan0
iface wlan0 inet static
    address 192.168.20.1
    netmask 255.255.255.0
```

### NetworkManager — игнорировать wlan0
**Файл:** `/etc/NetworkManager/conf.d/unmanaged.conf`
```ini
[keyfile]
unmanaged-devices=interface-name:wlan0
```

### wpa_supplicant замаскирован
```bash
systemctl mask wpa_supplicant
```
_(конфликтовал с hostapd за wlan0)_

---

## Управление зарядом батареи (ACC) {#acc}

**Приложение:** ACCA (AccA) — установлено через APK  
**Демон:** ACC — установлен через ACCA при первом запуске

### Настройки
- Pause charging at: **70%**
- Resume charging at: **40%**
- Температурный контроль — настроен через интерфейс ACCA

### Через ADB (альтернатива)
```bash
adb shell su -c "acc -s pc=70 rc=40"
adb shell su -c "acc -i"  # статус
```

---

## Файловая карта {#файлы}

### На Orange Pi Zero 3

| Путь | Описание |
|------|----------|
| `/opt/opi_dashboard.py` | FastAPI бэкенд дашборда |
| `/opt/static/index.html` | HTML интерфейс |
| `/opt/static/style.css` | CSS стили |
| `/opt/static/app.js` | JavaScript |
| `/opt/opi-dashboard-venv/` | Python venv |
| `/etc/systemd/system/usb-router.service` | Systemd юнит запуска autowarp при загрузке |
| `/etc/systemd/system/opi-dashboard.service` | Systemd юнит дашборда |
| `/usr/local/bin/usb-autowarp.sh` | Скрипт инициализации модема |
| `/etc/hostapd/hostapd.conf` | Конфиг WiFi AP |
| `/etc/dnsmasq.conf` | DHCP/DNS конфиг |
| `/etc/network/interfaces` | Статический IP wlan0 |
| `/etc/NetworkManager/conf.d/unmanaged.conf` | NM игнорирует wlan0 |

### На телефоне (через ADB)

| Путь | Описание |
|------|----------|
| `/sys/class/power_supply/battery/charging_enabled` | Управление зарядкой |
| `/sys/class/power_supply/battery/capacity` | Уровень заряда % |
| `/sys/class/power_supply/battery/temp` | Температура (÷10 = °C) |
| `/sys/class/power_supply/battery/current_now` | Ток мкА |
| `/sys/class/power_supply/battery/voltage_now` | Напряжение мкВ |
| `/data/user/0/com.android.providers.telephony/databases/mmssms.db` | База SMS |

---

## Команды для диагностики {#диагностика}

### ADB — статус телефона
```bash
adb devices
adb shell su -c "id"                          # проверка root
adb shell getprop ro.miui.ui.version.code     # версия MIUI
adb shell settings get system power_supersave_mode_open  # режим питания
```

### LTE сигнал
```bash
adb shell su -c "dumpsys telephony.registry | grep -i band"
# mChannelNumber: 2850=B7(2600MHz), 200=B1(2100MHz), 3750=B8(900MHz)
```

### Трафик
```bash
adb shell cat /proc/net/dev | grep rndis0
```

### OPI — сеть
```bash
ip addr show wlan0
ip addr show end0
iw dev wlan0 info          # тип интерфейса (должен быть AP)
journalctl -u hostapd -f   # логи WiFi
journalctl -u dnsmasq -f   # логи DHCP
```

### OPI — сервисы
```bash
systemctl status opi-dashboard
systemctl status hostapd
systemctl status dnsmasq
journalctl -u opi-dashboard -n 50 --no-pager
```

### Резервное копирование SD карты
```bash
# Снять образ (телефон выключен, карта в UB-X58A)
sudo dd if=/dev/sdb bs=4M status=progress of=~/opi_backup_$(date +%Y%m%d).img
pishrink.sh -Z ~/opi_backup_$(date +%Y%m%d).img
# Результат: opi_backup_YYYYMMDD.img.gz (~2-4 GB)

# Восстановить
gunzip -c opi_backup_20260413.img.gz | sudo dd of=/dev/sdb bs=4M status=progress
```

---

## Известные особенности

- **Координаты тапа** `929 1234` для ультраэкономии могут измениться при обновлении MIUI
- **WAN интерфейс** `enx...` меняет имя — определяется динамически в autowarp.sh
- **`charging_enabled` устойчив** к переподключению USB — флаг не сбрасывается
- **wpa_supplicant замаскирован** — без этого hostapd не может захватить wlan0
- **SMS** удаляются только через удаление БД `mmssms.db*` + killall com.android.phone
