#!/usr/bin/env python3
"""
DanyaClient — Railway Database Sync & Backup Tool
Allows secure export, verification, and restore of SQLite database from live Railway domain.
Only authorized with the Master Sync Key.
"""

import sys
import os
import argparse
import urllib.request
import urllib.error
import json
from datetime import datetime

DEFAULT_SECRET_KEY = "DANYACLIENT_MASTER_BACKUP_KEY_77391028461947291048204918471928"
MASTER_KEY = os.environ.get("BACKUP_SECRET_KEY", DEFAULT_SECRET_KEY)

def format_url(domain: str, path: str) -> str:
    domain = domain.strip().rstrip("/")
    if not domain.startswith("http://") and not domain.startswith("https://"):
        domain = "https://" + domain
    return f"{domain}{path}"

def fetch_info(domain: str, secret_key: str = MASTER_KEY):
    url = format_url(domain, "/api/system/backup/info")
    req = urllib.request.Request(url, headers={"X-Backup-Key": secret_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
            print("\n[+] Состояние базы данных на сервере:")
            print(f"    Путь на сервере:    {data.get('db_path')}")
            print(f"    Размер файла:       {data.get('size_kb')} KB")
            print(f"    Пользователей:      {data.get('users_count')}")
            print(f"    Лицензионных ключей:{data.get('keys_count')}")
            print(f"    Последнее изменение:{data.get('last_modified')}")
            return data
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[-] Ошибка запроса ({e.code}): {err_msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[-] Ошибка подключения: {e}", file=sys.stderr)
        sys.exit(1)

def download_db(domain: str, output_path: str = None, secret_key: str = MASTER_KEY):
    url = format_url(domain, "/api/system/backup/export")
    req = urllib.request.Request(url, headers={"X-Backup-Key": secret_key})
    
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"danyaclient_backup_{timestamp}.db"
        
    print(f"[*] Подключение к {url}...")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw_bytes = res.read()
            if not raw_bytes.startswith(b"SQLite format 3\x00"):
                print("[-] Полученные данные не являются корректной базой SQLite!", file=sys.stderr)
                sys.exit(1)
                
            with open(output_path, "wb") as f:
                f.write(raw_bytes)
                
            size_kb = round(len(raw_bytes) / 1024, 1)
            print(f"[+] База данных успешно выкачана и сохранена: {output_path} ({size_kb} KB)")
            
            # Local quick check
            try:
                import sqlite3
                conn = sqlite3.connect(output_path)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM users")
                users = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM license_keys")
                keys = c.fetchone()[0]
                conn.close()
                print(f"[+] Проверка целостности пройдена: {users} пользователей, {keys} ключей.")
            except Exception:
                pass
            return output_path
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[-] Доступ запрещён или ошибка сервера ({e.code}): {err_msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[-] Сбой загрузки базы: {e}", file=sys.stderr)
        sys.exit(1)

def upload_db(domain: str, file_path: str, secret_key: str = MASTER_KEY):
    if not os.path.exists(file_path):
        print(f"[-] Файл {file_path} не найден!", file=sys.stderr)
        sys.exit(1)
        
    with open(file_path, "rb") as f:
        file_bytes = f.read()
        
    if not file_bytes.startswith(b"SQLite format 3\x00"):
        print(f"[-] Файл {file_path} не является валидной SQLite базой данных!", file=sys.stderr)
        sys.exit(1)
        
    url = format_url(domain, "/api/system/backup/restore")
    req = urllib.request.Request(
        url,
        data=file_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Backup-Key": secret_key
        },
        method="POST"
    )
    
    print(f"[*] Отправка {file_path} ({round(len(file_bytes)/1024, 1)} KB) на {url}...")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            resp_data = json.loads(res.read().decode("utf-8"))
            print(f"[+] {resp_data.get('message', 'База успешно восстановлена!')}")
            return resp_data
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[-] Ошибка применения базы ({e.code}): {err_msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[-] Сбой отправки базы: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="DanyaClient — Инструмент резервного копирования и синхронизации базы с Railway"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Info
    p_info = subparsers.add_parser("info", help="Получить информацию о базе данных на сервере")
    p_info.add_argument("domain", help="URL или домен (например, https://danyaclient.up.railway.app)")
    p_info.add_argument("--key", default=MASTER_KEY, help="Секретный Master Sync Key (опционально)")

    # Download
    p_down = subparsers.add_parser("download", help="Выкачать базу данных с удаленного сервера")
    p_down.add_argument("domain", help="URL или домен")
    p_down.add_argument("-o", "--output", default="danyaclient.db", help="Куда сохранить файл (по умолчанию danyaclient.db)")
    p_down.add_argument("--key", default=MASTER_KEY, help="Секретный Master Sync Key")

    # Upload
    p_up = subparsers.add_parser("upload", help="Загрузить локальную базу данных на сервер")
    p_up.add_argument("domain", help="URL или домен")
    p_up.add_argument("file", help="Путь к локальному файлу .db")
    p_up.add_argument("--key", default=MASTER_KEY, help="Секретный Master Sync Key")

    args = parser.parse_args()

    if args.command == "info":
        fetch_info(args.domain, args.key)
    elif args.command == "download":
        download_db(args.domain, args.output, args.key)
    elif args.command == "upload":
        upload_db(args.domain, args.file, args.key)

if __name__ == "__main__":
    main()
