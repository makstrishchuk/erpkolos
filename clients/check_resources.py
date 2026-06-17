import sqlite3
import os
from pathlib import Path

def check():
    db_path = Path(__file__).parent / "wiso_golabel.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== ДИАГНОСТИКА РЕСУРСОВ ===")

    # 1. Проверяем наличие ресурсов
    print("\n1. Список ресурсов (Оборудования):")
    cur.execute("SELECT * FROM factory_resources")
    resources = cur.fetchall()
    if not resources:
        print("❌ НЕТ РЕСУРСОВ! Зайдите в Админ -> Ресурсы и создайте 'Печь'.")
    else:
        for r in resources:
            print(f"   [ID {r['resource_id']}] {r['resource_name']} (Мощность: {r['quantity']*r['shifts_count']*r['shift_duration_min']} мин)")

    # 2. Проверяем типы теста и их связь
    print("\n2. Проверка компонентов (Теста):")
    cur.execute("SELECT dough_id, name, resource_id, production_time_min FROM dough_types")
    doughs = cur.fetchall()
    
    for d in doughs:
        res_id = d['resource_id']
        time_min = d['production_time_min']
        
        # Ищем ресурс
        res_exists = False
        res_name = "НЕ НАЙДЕН"
        for r in resources:
            if r['resource_id'] == res_id:
                res_exists = True
                res_name = r['resource_name']
                break
        
        status = "✅ ОК"
        if not res_exists: status = "❌ ОШИБКА: Ресурс не привязан!"
        if time_min <= 0: status = "⚠️ ПРЕДУПРЕЖДЕНИЕ: Время производства 0 мин!"
        
        print(f"   - {d['name']} -> Ресурс ID: {res_id} ({res_name}) | Время: {time_min} мин. -> {status}")

    conn.close()
    input("\nНажмите Enter...")

if __name__ == "__main__":
    check()