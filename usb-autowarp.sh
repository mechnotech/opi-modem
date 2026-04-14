#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# --- 0. ПОДГОТОВКА ПЕРЕМЕННЫХ ---
ENV_FILE="/tmp/wan_env"
> $ENV_FILE
unset WAN_IFACE

# Индикация: включаем красный (процесс пошел)
LED_PATH="/sys/class/leds/red_led"
[ -d "$LED_PATH" ] && echo none > "$LED_PATH/trigger" && echo 1 > "$LED_PATH/brightness"

# --- 1. ADB: АКТИВАЦИЯ ТЕЛЕФОНА ---
sleep 5
/usr/bin/adb start-server
sleep 2
/usr/bin/adb shell svc usb setFunctions rndis
sleep 5

# --- 1.5. УЛЬТРАЭКОНОМИЯ БАТАРЕИ ---
sleep 3
echo "Активация ультраэкономии..."
/usr/bin/adb shell "input keyevent KEYCODE_WAKEUP && wm dismiss-keyguard && am start -n com.miui.securitycenter/com.miui.powercenter.PowerMainActivity && sleep 1.5 && input tap 929 1234"
sleep 2
/usr/bin/adb shell input keyevent KEYCODE_HOME

SUPERSAVE=$(/usr/bin/adb shell settings get system power_supersave_mode_open 2>/dev/null | tr -d '[:space:]')
if [ "$SUPERSAVE" = "1" ]; then
    echo "OK: Ультраэкономия активна"
else
    echo "ВНИМАНИЕ: Ультраэкономия не активировалась (power_supersave_mode_open=$SUPERSAVE)"
fi

# --- 2. ДИНАМИЧЕСКИЙ ПОИСК ИНТЕРФЕЙСА ---
# Ищем любой USB-интерфейс, кроме lo и end0
CURRENT_WAN=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(enx|usb|wwan|eth[1-9])' | head -n 1)

if [ -z "$CURRENT_WAN" ]; then
    echo "ОШИБКА: Модем не найден."
    exit 1
fi

# Экспортируем переменную и сохраняем в файл для всей системы
export WAN_IFACE=$CURRENT_WAN
echo "WAN_IFACE=$WAN_IFACE" > $ENV_FILE
echo "Используем интерфейс: $WAN_IFACE"

# --- 3. НАСТРОЙКА СЕТИ (DHCP) ---
/usr/bin/killall dhclient 2>/dev/null
/usr/sbin/dhclient -v $WAN_IFACE
echo 1 > /proc/sys/net/ipv4/ip_forward

# --- 4. FIREWALL: NAT И ОПТИМИЗАЦИЯ ---
/usr/sbin/iptables -F FORWARD
/usr/sbin/iptables -t nat -F
/usr/sbin/iptables -t nat -A POSTROUTING -o $WAN_IFACE -j MASQUERADE
/usr/sbin/iptables -t mangle -A POSTROUTING -o $WAN_IFACE -j TTL --ttl-set 64
/usr/sbin/iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
/usr/sbin/iptables -A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
/usr/sbin/iptables -A FORWARD -i end0 -o $WAN_IFACE -j ACCEPT

# --- 5. МОНИТОРИНГ ТРАФИКА И СТАТУС ---
RX_MB=$(cat /sys/class/net/$WAN_IFACE/statistics/rx_bytes | awk '{printf "%.2f", $1/1024/1024}')
TX_MB=$(cat /sys/class/net/$WAN_IFACE/statistics/tx_bytes | awk '{printf "%.2f", $1/1024/1024}')

if ping -c 1 -W 5 8.8.8.8 > /dev/null; then
    echo "OK: Интернет активен. Трафик за сессию: RX: ${RX_MB}MB | TX: ${TX_MB}MB"
    [ -d "$LED_PATH" ] && echo 0 > "$LED_PATH/brightness"
else
    echo "ВНИМАНИЕ: Настройка завершена, но пинга нет."
    [ -d "$LED_PATH" ] && echo 1 > "$LED_PATH/brightness"
fi

# --- 6. ПРОВЕРКА ЧЕРЕЗ ЛОКАЛЬНЫЙ РЕСУРС (YA.RU) ---
if ping -c 1 -W 5 ya.ru > /dev/null; then
    RX_MB=$(awk '{printf "%.2f", $1/1024/1024}' /sys/class/net/$WAN_IFACE/statistics/rx_bytes)
    echo "OK: Интернет активен (ya.ru). Трафик сессии: ${RX_MB} MB"
    [ -d "$LED_PATH" ] && echo 0 > "$LED_PATH/brightness"
else
    echo "ВНИМАНИЕ: ya.ru не отвечает. Пробуем резерв 77.88.8.8..."
    if ping -c 1 -W 5 77.88.8.8 > /dev/null; then
        echo "OK: DNS Яндекса доступен. Проблемы с именами?"
        [ -d "$LED_PATH" ] && echo 0 > "$LED_PATH/brightness"
    else
        echo "КРИТИЧНО: Связи нет."
        [ -d "$LED_PATH" ] && echo 1 > "$LED_PATH/brightness"
    fi
fi

# --- 7. КЛИМАТ-КОНТРОЛЬ (УЛИТКА) ---
FAN_WPIN=7  # 13-я ножка

gpio mode $FAN_WPIN out
gpio write $FAN_WPIN 0

(
while true; do
    CPU_TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
    CPU_TEMP=$((CPU_TEMP / 1000))

    BAT_TEMP=$(/usr/bin/adb shell dumpsys battery 2>/dev/null | grep temperature | awk '{print $2}')
    BAT_TEMP=$(( ${BAT_TEMP:-0} / 10 ))

    if [ "$CPU_TEMP" -gt 55 ] || [ "$BAT_TEMP" -gt 38 ]; then
        gpio write $FAN_WPIN 1
        sleep 120
    elif [ "$CPU_TEMP" -lt 45 ] && [ "$BAT_TEMP" -lt 35 ]; then
        gpio write $FAN_WPIN 0
        sleep 60
    else
        sleep 60
    fi
done
) &
