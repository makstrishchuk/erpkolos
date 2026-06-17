"""
Установщик клиента WISO GoLabel
Автоматически устанавливает все зависимости и создает ярлык
"""
import subprocess
import sys
import os
from pathlib import Path

def print_header(text):
    """Красивый заголовок"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")

def check_python():
    """Проверить версию Python"""
    print_header("Проверка Python")
    version = sys.version_info
    print(f"Python версия: {version.major}.{version.minor}.{version.micro}")

    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("Ошибка: Требуется Python 3.9 или выше!")
        print("   Скачайте с https://www.python.org/downloads/")
        return False

    print("OK: Версия Python подходит")
    return True

def find_python_exe():
    """Найти исполняемый файл Python"""
    import shutil

    # Список возможных команд Python
    python_commands = ['python', 'python3', 'py']

    for cmd in python_commands:
        python_path = shutil.which(cmd)
        if python_path:
            # Проверить что команда реально работает
            try:
                result = subprocess.run([python_path, '--version'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    print(f"Найден Python: {python_path}")
                    print(f"Версия: {result.stdout.strip()}")
                    return python_path
            except:
                continue

    # Если не найден в PATH, проверить стандартные расположения
    possible_paths = [
        r"C:\Python39\python.exe",
        r"C:\Python310\python.exe",
        r"C:\Python311\python.exe",
        r"C:\Python312\python.exe",
        r"C:\Python313\python.exe",
        r"C:\Python314\python.exe",
        r"C:\Program Files\Python39\python.exe",
        r"C:\Program Files\Python310\python.exe",
        r"C:\Program Files\Python311\python.exe",
        r"C:\Program Files\Python312\python.exe",
        r"C:\Program Files\Python313\python.exe",
        r"C:\Program Files\Python314\python.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                result = subprocess.run([path, '--version'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    print(f"Найден Python: {path}")
                    print(f"Версия: {result.stdout.strip()}")
                    return path
            except:
                continue

    return None

def install_python():
    """Установить Python с сервера"""
    print_header("Установка Python")

    # Путь к установщику Python на сервере
    server_python_installer = Path(r"\\server01\DATA\Maks\wiso_golabel\python_installer\python-3.13.11-amd64.exe")

    if not server_python_installer.exists():
        print(f"ОШИБКА: Установщик Python не найден на сервере: {server_python_installer}")
        return None

    print(f"Найден установщик Python: {server_python_installer}")
    print("Запуск установки Python...")
    print("ВНИМАНИЕ: Установка может занять 1-2 минуты")
    print()

    try:
        # Запустить установщик Python с параметрами тихой установки
        install_params = [
            str(server_python_installer),
            "/quiet",                    # Тихая установка
            "InstallAllUsers=0",         # Только для текущего пользователя
            "PrependPath=1",             # Добавить в PATH
            "Include_test=0",            # Не устанавливать тесты
            "Include_launcher=1",        # Установить launcher
            "InstallLauncherAllUsers=0"  # Launcher для текущего пользователя
        ]

        print("Запуск установки Python (может потребоваться разрешение UAC)...")
        result = subprocess.run(install_params, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            print("OK: Python установлен")
        else:
            print(f"Код возврата: {result.returncode}")
            if result.stdout:
                print(f"Stdout: {result.stdout}")
            if result.stderr:
                print(f"Stderr: {result.stderr}")

        # Подождать немного чтобы установка завершилась
        import time
        time.sleep(3)

        # Попробовать найти установленный Python
        print("\nПоиск установленного Python...")
        python_exe = find_python_exe()

        if python_exe:
            print(f"OK: Python найден: {python_exe}")
            return python_exe
        else:
            print("Предупреждение: Python установлен, но не найден в PATH")
            print("Попробуем найти в стандартных расположениях...")

            # Проверить AppData\Local\Programs\Python
            local_python = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python313" / "python.exe"
            if local_python.exists():
                print(f"OK: Найден Python: {local_python}")
                return str(local_python)

            # Проверить другие варианты
            for version in ["Python313", "Python312", "Python311"]:
                local_python = Path.home() / "AppData" / "Local" / "Programs" / "Python" / version / "python.exe"
                if local_python.exists():
                    print(f"OK: Найден Python: {local_python}")
                    return str(local_python)

            print("ОШИБКА: Python установлен, но не может быть найден")
            return None

    except subprocess.TimeoutExpired:
        print("ОШИБКА: Установка Python заняла слишком много времени (>5 минут)")
        return None
    except Exception as e:
        print(f"ОШИБКА при установке Python: {e}")
        import traceback
        traceback.print_exc()
        return None

def install_dependencies():
    """Установить зависимости"""
    print_header("Установка зависимостей")

    dependencies = [
        "websockets==12.0",
        "tkcalendar==1.6.1"
    ]

    # Найти Python (если запущен из EXE, sys.executable указывает на EXE)
    python_exe = sys.executable
    if python_exe.endswith('.exe') and ('WISO_GoLabel' in python_exe or 'Setup' in python_exe):
        # Запущен из EXE, ищем python
        print("Поиск Python...")
        python_exe = find_python_exe()
        if not python_exe:
            # Python не найден - установим
            print("\nPython не найден на этом компьютере.")
            print("Установщик автоматически установит Python.")
            print()
            python_exe = install_python()
            if not python_exe:
                print("\n" + "=" * 70)
                print("ОШИБКА: Не удалось установить Python!")
                print("=" * 70)
                print("\nПожалуйста, свяжитесь с администратором.")
                print("\n" + "=" * 70)
                return False
        print()

    print("Обновление pip...")
    try:
        result = subprocess.run([python_exe, "-m", "pip", "install", "--upgrade", "pip"],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("OK: pip обновлен\n")
        else:
            print(f"Предупреждение: не удалось обновить pip")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}\n")
    except subprocess.TimeoutExpired:
        print("Предупреждение: обновление pip заняло слишком много времени\n")
    except Exception as e:
        print(f"Предупреждение: ошибка при обновлении pip: {e}\n")

    print("Установка библиотек:")
    for dep in dependencies:
        print(f"  - {dep}...", end=" ", flush=True)
        try:
            result = subprocess.run([python_exe, "-m", "pip", "install", dep],
                                  capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                print("OK")
            else:
                print(f"\nОШИБКА при установке {dep}:")
                print(f"Stdout: {result.stdout}")
                print(f"Stderr: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            print(f"\nОШИБКА: Установка {dep} заняла слишком много времени")
            return False
        except Exception as e:
            print(f"\nОШИБКА: {e}")
            return False

    print("\nOK: Все зависимости установлены")
    return True

def check_server_access():
    """Проверить доступ к серверу"""
    print_header("Проверка доступа к серверу")

    server_path = Path(r"\\server01\DATA\Maks\wiso_golabel")

    if not server_path.exists():
        print(f"ОШИБКА: Нет доступа к {server_path}")
        print("   Проверьте:")
        print("   1. Подключены ли вы к сети?")
        print("   2. Есть ли доступ к \\server01?")
        return False

    print(f"OK: Доступ к серверу есть: {server_path}")

    # Проверить наличие клиента
    client_file = server_path / "clients" / "unified_client.py"
    if not client_file.exists():
        print(f"ОШИБКА: Файл клиента не найден: {client_file}")
        return False

    print(f"OK: Файл клиента найден")
    return True

def create_desktop_shortcut():
    """Создать ярлык на рабочем столе"""
    print_header("Создание ярлыка на рабочем столе")

    try:
        # Получить путь к рабочему столу
        desktop = Path.home() / "Desktop"
        local_app_dir = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "WISO_GoLabel"
        local_app_dir.mkdir(parents=True, exist_ok=True)

        # Локальный launcher, чтобы на рабочем столе была только 1 ссылка
        launcher_vbs = local_app_dir / "launcher.vbs"
        vbs_content = '''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "\\\\server01\\DATA\\Maks\\wiso_golabel"
WshShell.Run "python clients\\unified_client.py", 0, False
Set WshShell = Nothing
'''
        with open(launcher_vbs, 'w', encoding='utf-8') as f:
            f.write(vbs_content)

        # Создать .lnk с фирменной иконкой (основной ярлык)
        icon_file = Path(r"\\server01\DATA\Maks\wiso_golabel\logo.ico")
        lnk_file = desktop / "WISO GoLabel.lnk"
        try:
            local_icon_file = local_app_dir / "logo.ico"
            if icon_file.exists():
                try:
                    if (not local_icon_file.exists()) or (local_icon_file.stat().st_size != icon_file.stat().st_size):
                        import shutil
                        shutil.copyfile(icon_file, local_icon_file)
                except Exception:
                    local_icon_file = icon_file
            else:
                local_icon_file = icon_file

            lnk_path_ps = str(lnk_file).replace("'", "''")
            launcher_path_ps = str(launcher_vbs).replace("'", "''")
            icon_path_ps = str(local_icon_file).replace("'", "''")
            workdir_ps = str(local_app_dir).replace("'", "''")
            ps_cmd = (
                "$WshShell = New-Object -ComObject WScript.Shell; "
                f"$Shortcut = $WshShell.CreateShortcut('{lnk_path_ps}'); "
                f"$Shortcut.TargetPath = '{launcher_path_ps}'; "
                f"$Shortcut.WorkingDirectory = '{workdir_ps}'; "
                f"$Shortcut.IconLocation = '{icon_path_ps},0'; "
                "$Shortcut.Description = 'WISO GoLabel - основной запуск'; "
                "$Shortcut.Save()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                check=False,
                capture_output=True,
                text=True,
                timeout=15
            )
            print(f"OK: Desktop icon shortcut created: {lnk_file.name}")
        except Exception as e:
            print(f"Предупреждение: не удалось создать .lnk с иконкой: {e}")

        # Удалить старые ярлыки, чтобы не было лишних файлов
        for old_name in ("WISO GoLabel.vbs", "WISO GoLabel (debug).bat"):
            old_file = desktop / old_name
            try:
                if old_file.exists():
                    old_file.unlink()
            except Exception:
                pass

        print("\nCreated 1 shortcut:")
        print("  - WISO GoLabel.lnk (главный запуск, с фирменной иконкой)")

        return True

    except Exception as e:
        print(f"ОШИБКА при создании ярлыка: {e}")
        return False

def main():
    """Основная функция установки"""
    print("\n")
    print("=" * 70)
    print("       USTANOVSHIK KLIENTA WISO GOLABEL - Versiya 1.0")
    print("=" * 70)

    # Шаг 1: Проверка Python
    if not check_python():
        input("\nNazhmite Enter dlya vykhoda...")
        return 1

    # Шаг 2: Проверка доступа к серверу
    if not check_server_access():
        input("\nNazhmite Enter dlya vykhoda...")
        return 1

    # Шаг 3: Установка зависимостей
    if not install_dependencies():
        input("\nNazhmite Enter dlya vykhoda...")
        return 1

    # Шаг 4: Создание ярлыка
    create_desktop_shortcut()

    # Финал
    print_header("OK: USTANOVKA ZAVERSHENA!")
    print("Klient WISO GoLabel uspeshno ustanovlen!")
    print("\nNa rabochem stole sozdan 1 yarlyk:")
    print("  1. 'WISO GoLabel.lnk' - osnovnoy (s logotipom)")
    print("\nDlya ezhednevnoy raboty ispolzuyte:")
    print("  -> WISO GoLabel.lnk")
    print("\nDannye dlya vkhoda:")
    print("  Login: admin")
    print("  Parol: admin123")
    print("\n" + "=" * 70)

    input("\nNazhmite Enter dlya zaversheniya...")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nUstanovka otmenena polzovatelem")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nKRITICHESKAYA OSHIBKA: {e}")
        import traceback
        traceback.print_exc()
        input("\nNazhmite Enter dlya vykhoda...")
        sys.exit(1)
