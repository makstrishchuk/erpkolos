#!/bin/bash

# Цвета для терминала
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

clear
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              WISO GOLABEL - КЛИЕНТ ОПЕРАТОРА                  ║"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo ""

# Переходим в директорию скрипта
cd "$(dirname "$0")"

# Проверяем наличие Python3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ ОШИБКА: Python3 не найден!${NC}"
    echo ""
    echo "Установите Python3 с https://www.python.org/downloads/"
    echo ""
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

echo -e "${GREEN}✅ Python найден${NC}"
PYTHON_VERSION=$(python3 --version 2>&1)
echo "   Версия: $PYTHON_VERSION"
echo ""

# Проверяем файл
if [ ! -f "operator_client.py" ]; then
    echo -e "${RED}❌ ОШИБКА: operator_client.py не найден!${NC}"
    echo ""
    echo "Убедитесь, что вы в правильной папке."
    echo ""
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

echo -e "${GREEN}✅ Файл найден${NC}"
echo ""

echo -e "${CYAN}🚀 Запуск клиента оператора...${NC}"
echo ""
echo "Окно программы должно открыться через 2-3 секунды..."
echo ""
echo -e "${YELLOW}⚠️  НЕ ЗАКРЫВАЙТЕ ЭТО ОКНО!${NC}"
echo "   Если закроете - программа завершится."
echo ""

# Запускаем Python
python3 operator_client.py
EXIT_CODE=$?

# Если программа завершилась
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""
if [ $EXIT_CODE -ne 0 ]; then
    echo -e "${RED}❌ Программа завершилась с ошибкой!${NC}"
    echo ""
    echo "Код ошибки: $EXIT_CODE"
    echo ""
else
    echo -e "${GREEN}✅ Программа закрыта нормально${NC}"
    echo ""
fi

read -p "Нажмите Enter для выхода..."
