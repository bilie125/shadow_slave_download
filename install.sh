#!/bin/bash

set -e

APP_NAME="shadow_slave_download"
APP_DIR="/opt/$APP_NAME"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"
PYTHON_BIN="python3"

echo "=========================================="
echo " Установка Shadow Slave Download"
echo "=========================================="

# Проверка root
if [ "$EUID" -ne 0 ]; then
    echo "Ошибка: запусти скрипт через sudo:"
    echo "sudo ./install.sh"
    exit 1
fi

# Определяем пользователя, который запускал sudo
REAL_USER="${SUDO_USER:-root}"

echo
echo "[1/8] Обновление пакетов..."
apt update

echo
echo "[2/8] Установка системных зависимостей..."

apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    libffi-dev \
    curl

# Проверяем Python
echo
echo "Python:"
$PYTHON_BIN --version

# Создание директории
echo
echo "[3/8] Создание директории приложения..."

mkdir -p "$APP_DIR"

# Если скрипт запускается из папки проекта,
# копируем проект в /opt/shadow_slave_download
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Исходная папка:"
echo "$SCRIPT_DIR"

echo "Копирование файлов в:"
echo "$APP_DIR"

cp -r "$SCRIPT_DIR"/* "$APP_DIR"/

# Также копируем скрытые файлы, кроме . и ..
shopt -s dotglob
for item in "$SCRIPT_DIR"/*; do
    name="$(basename "$item")"

    # Не копируем виртуальное окружение
    if [ "$name" != "venv" ]; then
        cp -r "$item" "$APP_DIR"/
    fi
done
shopt -u dotglob

# Создание необходимых папок
echo
echo "[4/8] Создание каталогов..."

mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/books"
mkdir -p "$APP_DIR/output"
mkdir -p "$APP_DIR/temp"
mkdir -p "$APP_DIR/logs"

# Создание venv
echo
echo "[5/8] Создание Python virtual environment..."

if [ ! -d "$APP_DIR/venv" ]; then
    $PYTHON_BIN -m venv "$APP_DIR/venv"
fi

PYTHON="$APP_DIR/venv/bin/python"
PIP="$APP_DIR/venv/bin/pip"

echo "Python:"
"$PYTHON" --version

echo
echo "Обновление pip..."

"$PIP" install --upgrade pip setuptools wheel

# Установка зависимостей
echo
echo "[6/8] Установка Python-зависимостей..."

if [ -f "$APP_DIR/requirements.txt" ]; then
    echo "Найден requirements.txt"
    "$PIP" install -r "$APP_DIR/requirements.txt"
else
    echo "requirements.txt не найден."

    echo "Устанавливаю основные зависимости..."

    "$PIP" install \
        aiogram \
        requests \
        beautifulsoup4 \
        python-docx \
        ebooklib \
        lxml \
        python-dotenv

    echo
    echo "Создаю requirements.txt..."

    "$PIP" freeze > "$APP_DIR/requirements.txt"
fi

# Проверяем bot.py
if [ ! -f "$APP_DIR/bot.py" ]; then
    echo
    echo "ОШИБКА: $APP_DIR/bot.py не найден!"
    exit 1
fi

# Права
echo
echo "Настройка прав..."

chown -R "$REAL_USER":"$REAL_USER" "$APP_DIR"

# systemd
echo
echo "[7/8] Создание systemd-сервиса..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Shadow Slave Download
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

WorkingDirectory=$APP_DIR

ExecStart=$APP_DIR/venv/bin/python $APP_DIR/bot.py

Restart=always
RestartSec=5

Environment=PYTHONUNBUFFERED=1

# Ограничения
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

# Перечитываем systemd
systemctl daemon-reload

# Включаем автозапуск
systemctl enable "$APP_NAME"

# Останавливаем старую версию, если была
systemctl stop "$APP_NAME" 2>/dev/null || true

# Запускаем
echo
echo "[8/8] Запуск бота..."

systemctl start "$APP_NAME"

sleep 3

echo
echo "=========================================="
echo " Проверка состояния"
echo "=========================================="

systemctl --no-pager status "$APP_NAME"

echo
echo "=========================================="
echo " Установка завершена"
echo "=========================================="

echo
echo "Полезные команды:"
echo
echo "Статус:"
echo "  sudo systemctl status $APP_NAME"
echo
echo "Логи:"
echo "  sudo journalctl -u $APP_NAME -f"
echo
echo "Перезапуск:"
echo "  sudo systemctl restart $APP_NAME"
echo
echo "Остановка:"
echo "  sudo systemctl stop $APP_NAME"
echo
echo "Запуск:"
echo "  sudo systemctl start $APP_NAME"
echo
echo "Путь приложения:"
echo "  $APP_DIR"
echo
echo "=========================================="