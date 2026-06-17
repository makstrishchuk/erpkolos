import csv
import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def parse_weekly_report(file_path):
    """
    Парсит недельный отчет WISO (CSV/Text)
    Возвращает: year, week_number, {article_nr: quantity}
    """
    data = {}
    year = None
    week = None
    
    with open(file_path, 'r', encoding='latin-1') as f: # Или utf-8, зависит от файла
        lines = f.readlines()
        
    for line in lines:
        # Ищем период: Zeitraum: 30.12.2024 - 05.01.2025
        if "Zeitraum:" in line:
            match = re.search(r'(\d{2}\.\d{2}\.\d{4})', line)
            if match:
                date_str = match.group(1)
                dt = datetime.strptime(date_str, '%d.%m.%Y')
                # Получаем ISO год и номер недели
                year, week, _ = dt.isocalendar()
        
        # Ищем строки с товарами (начинаются с 5 цифр)
        # Пример: 05501	"Medowik" ... 22,00
        parts = line.split('\t')
        # Фильтруем пустые элементы
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 5:
            art_nr = parts[0]
            # Количество обычно предпоследнее или пред-предпоследнее
            # Ищем число с запятой
            for p in parts[-2:]: 
                if ',' in p and any(c.isdigit() for c in p):
                    try:
                        qty = float(p.replace('.', '').replace(',', '.'))
                        data[art_nr] = qty
                        break
                    except: pass
                    
    return year, week, data

def import_history_to_db(db, file_path):
    year, week, data = parse_weekly_report(file_path)
    if not year or not week:
        logger.error(f"Не удалось определить дату в файле {file_path}")
        return False
        
    conn = db.get_connection()
    try:
        # Создаем таблицу для недельной истории, если нет
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_sales_history (
                year INTEGER,
                week INTEGER,
                article_nr TEXT,
                quantity REAL,
                PRIMARY KEY (year, week, article_nr)
            )
        """)
        
        for art, qty in data.items():
            conn.execute("""
                INSERT OR REPLACE INTO weekly_sales_history (year, week, article_nr, quantity)
                VALUES (?, ?, ?, ?)
            """, (year, week, art, qty))
            
        conn.commit()
        logger.info(f"Импортировано {len(data)} записей за {year}-W{week}")
        return True
    except Exception as e:
        logger.error(f"Ошибка импорта: {e}")
        return False
    finally:
        conn.close()