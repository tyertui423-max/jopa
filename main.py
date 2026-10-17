import os
import re
import time
import shutil
import sqlite3
import hashlib
import secrets
from typing import Optional
from datetime import datetime
from collections import defaultdict

from fastapi import FastAPI, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.environ.get("DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
if not DATA_DIR:
    # Check if /data exists and is actually writable
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        DATA_DIR = "/data"
    else:
        DATA_DIR = BASE_DIR

if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "danyaclient.db")

# Seed initial database from repository if volume is freshly mounted
default_db = os.path.join(BASE_DIR, "danyaclient.db")
if DATA_DIR != BASE_DIR and not os.path.exists(DB_PATH) and os.path.exists(default_db):
    try:
        shutil.copy2(default_db, DB_PATH)
    except Exception:
        pass

BACKUP_SECRET_KEY = os.environ.get(
    "BACKUP_SECRET_KEY", 
    "DANYACLIENT_MASTER_BACKUP_KEY_77391028461947291048204918471928"
)

def verify_backup_auth(request: Request):
    hdr_key = request.headers.get("x-backup-key") or request.headers.get("authorization")
    if hdr_key:
        if hdr_key.startswith("Bearer "):
            hdr_key = hdr_key[7:]
        if secrets.compare_digest(hdr_key.strip(), BACKUP_SECRET_KEY):
            return True
            
    query_secret = request.query_params.get("secret")
    if query_secret and secrets.compare_digest(query_secret.strip(), BACKUP_SECRET_KEY):
        return True

    user = get_current_user(request)
    if user and user.get("role") == "admin":
        return True

    raise HTTPException(
        status_code=403, 
        detail="Доступ запрещён: неверный секретный ключ синхронизации или отсутствуют права администратора."
    )

def is_subscription_active(user_dict: Optional[dict]) -> bool:
    if not user_dict:
        return False
    sub = user_dict.get("subscription")
    until = user_dict.get("subscription_until")
    if not sub or str(sub).strip().lower() in ["free", "none", "unavailable", ""]:
        return False
    if not until or str(until).strip().lower() in ["unavailable", "none", "expired", ""]:
        return False
    if str(until).strip().lower() in ["forever", "lifetime", "навсегда"]:
        return True
    try:
        exp_dt = datetime.strptime(str(until).strip(), "%d.%m.%Y")
        if exp_dt.date() >= datetime.utcnow().date():
            return True
        return False
    except Exception:
        return True

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            subscription TEXT DEFAULT 'Free',
            subscription_until TEXT DEFAULT 'Unavailable',
            hwid TEXT DEFAULT NULL,
            banner_url TEXT DEFAULT '/static/images/reg_bg.jpg',
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS license_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE NOT NULL,
            key_type TEXT NOT NULL,
            is_used INTEGER DEFAULT 0,
            used_by_user_id INTEGER DEFAULT NULL,
            used_by_username TEXT DEFAULT NULL,
            used_at TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Ensure migration columns exist on users
    for col, col_def in [
        ("subscription_until", "TEXT DEFAULT 'Unavailable'"),
        ("hwid", "TEXT DEFAULT NULL"),
        ("banner_url", "TEXT DEFAULT '/static/images/reg_bg.jpg'"),
        ("is_banned", "INTEGER DEFAULT 0"),
        ("ban_reason", "TEXT DEFAULT NULL"),
        ("uid", "INTEGER DEFAULT NULL")
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
        except Exception:
            pass

    # Ensure admin user INOAGENT is always seeded with role='admin'
    admin_user = "INOAGENT"
    admin_pass = "SVITIK0000000001232323290392"
    cursor.execute("SELECT id, salt FROM users WHERE username = ?", (admin_user,))
    row = cursor.fetchone()
    if not row:
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.sha256((admin_pass + salt).encode('utf-8')).hexdigest()
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, salt, role, subscription, subscription_until, is_banned, uid)
            VALUES (?, 'admin@danyaclient.fun', ?, ?, 'admin', 'Lifetime', 'Forever', 0, 1000)
        """, (admin_user, pwd_hash, salt))
    else:
        # Guarantee role is admin and password is up to date
        salt = row[1]
        pwd_hash = hashlib.sha256((admin_pass + salt).encode('utf-8')).hexdigest()
        cursor.execute("UPDATE users SET role = 'admin', password_hash = ?, is_banned = 0 WHERE username = ?", (pwd_hash, admin_user))

    # Ensure INOAGENT has UID 1000
    cursor.execute("UPDATE users SET uid = 1000 WHERE username = 'INOAGENT' AND (uid IS NULL OR uid != 1000)")
    # Backfill any existing users without a uid starting sequentially from 1001
    cursor.execute("SELECT id FROM users WHERE uid IS NULL ORDER BY id ASC")
    for r in cursor.fetchall():
        cursor.execute("SELECT COALESCE(MAX(uid), 999) + 1 FROM users")
        next_u = cursor.fetchone()[0]
        cursor.execute("UPDATE users SET uid = ? WHERE id = ?", (next_u, r[0]))
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("SELECT value FROM site_settings WHERE key = 'launcher_url'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO site_settings (key, value) VALUES ('launcher_url', '/static/downloads/DanyaClient-Launcher.exe')")

    conn.commit()
    conn.close()

init_db()

def get_launcher_url() -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM site_settings WHERE key = 'launcher_url'")
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0].strip()
    except Exception:
        pass
    return "/static/downloads/DanyaClient-Launcher.exe"

def set_launcher_url(url: str) -> str:
    cleaned = url.strip()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO site_settings (key, value, updated_at)
        VALUES ('launcher_url', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
    """, (cleaned,))
    conn.commit()
    conn.close()
    return cleaned

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return hashed, salt

class SecurityManager:
    """Enterprise rate limiting and exploit prevention."""
    def __init__(self):
        self.failed_logins = defaultdict(list)
        self.login_lockouts = {}
        self.register_attempts = defaultdict(list)
        self.failed_keys = defaultdict(list)
        self.key_lockouts = {}

    def get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else "127.0.0.1"

    def check_login_allowed(self, ip: str):
        now = time.time()
        if ip in self.login_lockouts:
            remaining = int(self.login_lockouts[ip] - now)
            if remaining > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"Слишком много неудачных попыток входа. Доступ с вашего IP заблокирован на {remaining} сек."
                )
            del self.login_lockouts[ip]
            self.failed_logins[ip] = []

    def record_failed_login(self, ip: str):
        now = time.time()
        self.failed_logins[ip] = [t for t in self.failed_logins[ip] if now - t < 300]
        self.failed_logins[ip].append(now)
        if len(self.failed_logins[ip]) >= 5:
            self.login_lockouts[ip] = now + 900  # 15 minutes
            raise HTTPException(
                status_code=429,
                detail="Превышен лимит попыток входа (5 ошибок подряд). Доступ временно заблокирован на 15 минут для защиты аккаунта."
            )

    def record_successful_login(self, ip: str):
        self.failed_logins.pop(ip, None)
        self.login_lockouts.pop(ip, None)

    def check_register_allowed(self, ip: str):
        now = time.time()
        self.register_attempts[ip] = [t for t in self.register_attempts[ip] if now - t < 3600]
        if len(self.register_attempts[ip]) >= 5:
            raise HTTPException(
                status_code=429,
                detail="Превышен лимит регистраций с одного IP (максимум 5 в час). Защита от спама."
            )
        self.register_attempts[ip].append(now)

    def check_key_allowed(self, ip: str):
        now = time.time()
        if ip in self.key_lockouts:
            remaining = int(self.key_lockouts[ip] - now)
            if remaining > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"Слишком много неверных попыток ввода ключа. Функция заблокирована на {remaining} сек."
                )
            del self.key_lockouts[ip]
            self.failed_keys[ip] = []

    def record_failed_key(self, ip: str):
        now = time.time()
        self.failed_keys[ip] = [t for t in self.failed_keys[ip] if now - t < 300]
        self.failed_keys[ip].append(now)
        if len(self.failed_keys[ip]) >= 5:
            self.key_lockouts[ip] = now + 600  # 10 minutes
            raise HTTPException(
                status_code=429,
                detail="Превышен лимит ошибок ввода ключа. Активация ключей заблокирована на 10 минут."
            )

    def record_successful_key(self, ip: str):
        self.failed_keys.pop(ip, None)
        self.key_lockouts.pop(ip, None)

security = SecurityManager()

app = FastAPI(title="DanyaClient Gaming Client Portal", version="1.0.0")

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/admin") or request.url.path.startswith("/account"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
    return response

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def get_current_user(request: Request) -> Optional[dict]:
    session_token = request.cookies.get("danyaclient_session") or request.cookies.get("recoin_session")
    if not session_token:
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.role, u.subscription,
                   u.subscription_until, u.hwid, u.banner_url, u.is_banned, u.ban_reason, u.created_at, u.uid
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ?
        """, (session_token,))
        user = cursor.fetchone()
        if user:
            u_dict = dict(user)
            # If user was banned while having an active session, kick them out immediately
            if u_dict.get("is_banned") == 1:
                cursor.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
                conn.commit()
                conn.close()
                return None
            conn.close()
            user_uid = u_dict.get("uid") or (999 + u_dict['id'])
            u_dict["uid"] = f"#{user_uid}"
            try:
                dt = datetime.fromisoformat(str(u_dict["created_at"]))
                u_dict["registered_date"] = dt.strftime("%d.%m.%Y")
            except Exception:
                u_dict["registered_date"] = "16.10.2026"
            if not u_dict.get("subscription_until") or u_dict.get("subscription_until") == "None":
                u_dict["subscription_until"] = "Unavailable"
            if not u_dict.get("banner_url"):
                u_dict["banner_url"] = "/static/images/reg_bg.jpg"
            u_dict["has_active_sub"] = is_subscription_active(u_dict)
            return u_dict
        conn.close()
    except Exception:
        pass
    return None

def require_admin(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация в системе")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещен. Требуются права Администратора.")
    return user

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user, "active_page": "home"})

@app.get("/functions", response_class=HTMLResponse)
async def functions_view(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user, "active_page": "functions"})

@app.get("/faq", response_class=HTMLResponse)
async def faq_view(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user, "active_page": "faq"})

@app.get("/products", response_class=HTMLResponse)
async def products_view(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(request=request, name="products.html", context={"user": user, "active_page": "products"})

@app.get("/catalog", response_class=HTMLResponse)
async def catalog_redirect():
    return RedirectResponse(url="/products")

@app.get("/registration", response_class=HTMLResponse)
async def registration_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="register.html", context={"user": None, "active_page": "registration"})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/account")
    return templates.TemplateResponse(request=request, name="login.html", context={"user": None, "active_page": "login"})

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="account.html", context={"user": user, "active_page": "account"})

class RegisterPayload(BaseModel):
    username: str
    email: str
    password: str
    confirm_password: str

@app.post("/api/register")
async def api_register(payload: RegisterPayload, request: Request, response: Response):
    client_ip = security.get_client_ip(request)
    security.check_register_allowed(client_ip)

    username = payload.username.strip()
    email = payload.email.strip().lower()
    password = payload.password

    if not re.match(r"^[a-zA-Z0-9_]{3,24}$", username):
        raise HTTPException(
            status_code=400, 
            detail="Имя пользователя должно содержать от 3 до 24 символов (только латиница, цифры и символ _)"
        )
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Укажите корректный email адрес")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не менее 8 символов")
    if password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Пароли не совпадают")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Пользователь с таким никнеймом или email уже зарегистрирован")

    pwd_hash, salt = hash_password(password)

    # Assign sequential UID starting from 1000
    cursor.execute("SELECT COALESCE(MAX(uid), 999) + 1 FROM users")
    assigned_uid = cursor.fetchone()[0]
    if assigned_uid < 1000:
        assigned_uid = 1000

    cursor.execute(
        "INSERT INTO users (username, email, password_hash, salt, uid) VALUES (?, ?, ?, ?, ?)",
        (username, email, pwd_hash, salt, assigned_uid)
    )
    user_id = cursor.lastrowid
    session_token = secrets.token_urlsafe(32)
    cursor.execute(
        "INSERT INTO sessions (session_token, user_id) VALUES (?, ?)",
        (session_token, user_id)
    )
    conn.commit()
    conn.close()

    response.set_cookie(
        key="danyaclient_session",
        value=session_token,
        httponly=True,
        max_age=86400 * 30,
        samesite="lax"
    )
    return {"status": "ok", "message": "Account created successfully", "username": username}

class LoginPayload(BaseModel):
    login: str
    password: str

@app.post("/api/login")
async def api_login(payload: LoginPayload, request: Request, response: Response):
    client_ip = security.get_client_ip(request)
    security.check_login_allowed(client_ip)

    login_id = payload.login.strip()
    password = payload.password

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (login_id, login_id.lower()))
    user = cursor.fetchone()

    if not user:
        conn.close()
        security.record_failed_login(client_ip)
        raise HTTPException(status_code=400, detail="Неверный логин/email или пароль")

    # Enforce site ban
    if user["is_banned"] == 1:
        conn.close()
        reason = user["ban_reason"] or "Нарушение правил проекта"
        raise HTTPException(status_code=403, detail=f"Ваш аккаунт заблокирован на сайте: {reason}")

    check_hash, _ = hash_password(password, user["salt"])
    if check_hash != user["password_hash"]:
        conn.close()
        security.record_failed_login(client_ip)
        raise HTTPException(status_code=400, detail="Неверный логин/email или пароль")

    security.record_successful_login(client_ip)
    session_token = secrets.token_urlsafe(32)
    cursor.execute("INSERT INTO sessions (session_token, user_id) VALUES (?, ?)", (session_token, user["id"]))
    conn.commit()
    conn.close()

    response.set_cookie(
        key="danyaclient_session",
        value=session_token,
        httponly=True,
        max_age=86400 * 30,
        samesite="lax"
    )
    return {"status": "ok", "message": "Logged in successfully", "username": user["username"]}

@app.post("/api/logout")
async def api_logout(request: Request, response: Response):
    session_token = request.cookies.get("danyaclient_session") or request.cookies.get("recoin_session")
    if session_token:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
        conn.commit()
        conn.close()
    response.delete_cookie(key="danyaclient_session")
    response.delete_cookie(key="recoin_session")
    return {"status": "ok", "message": "Logged out successfully"}

class ActivateKeyPayload(BaseModel):
    key: str
    key_type: str = "subscription"

@app.post("/api/activate-key")
async def api_activate_key(payload: ActivateKeyPayload, request: Request):
    client_ip = security.get_client_ip(request)
    security.check_key_allowed(client_ip)

    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    
    key = payload.key.strip().upper()
    if not key or len(key) < 5:
        raise HTTPException(status_code=400, detail="Неверный формат ключа. Проверьте правильность ввода.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check database license_keys table
    cursor.execute("SELECT * FROM license_keys WHERE UPPER(key_code) = ?", (key,))
    db_key = cursor.fetchone()

    if not db_key:
        conn.close()
        security.record_failed_key(client_ip)
        raise HTTPException(status_code=400, detail="Лицензионный ключ не найден. Проверьте правильность символов.")

    if db_key["is_used"] == 1:
        conn.close()
        security.record_failed_key(client_ip)
        raise HTTPException(status_code=400, detail=f"Этот лицензионный ключ уже был активирован ранее.")
    
    security.record_successful_key(client_ip)
    k_type = db_key["key_type"]
    cursor.execute("""
        UPDATE license_keys
        SET is_used = 1, used_by_user_id = ?, used_by_username = ?, used_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (user["id"], user["username"], db_key["id"]))

    if k_type == "HWID Reset":
        cursor.execute("UPDATE users SET hwid = NULL WHERE id = ?", (user["id"],))
        conn.commit()
        conn.close()
        return {"status": "ok", "message": "HWID успешно сброшен!", "hwid": "—"}
    elif k_type == "Lifetime":
        sub_type = "Lifetime"
        until = "Forever"
    elif k_type == "90 Days":
        sub_type = "90 Days"
        until = "16.01.2027"
    else:
        sub_type = "30 Days"
        until = "16.11.2026"

    cursor.execute("UPDATE users SET subscription = ?, subscription_until = ? WHERE id = ?", (sub_type, until, user["id"]))
    conn.commit()
    conn.close()
    return {
        "status": "ok",
        "message": f"Лицензия {sub_type} успешно активирована!",
        "subscription": sub_type,
        "subscription_until": until,
        "has_active_sub": True
    }

@app.get("/api/download-launcher")
async def api_download_launcher(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    if not user.get("has_active_sub"):
        raise HTTPException(
            status_code=403, 
            detail="Скачивание лаунчера доступно только пользователям с активной подпиской."
        )
    
    custom_url = get_launcher_url()
    if custom_url and (custom_url.startswith("http://") or custom_url.startswith("https://")):
        return RedirectResponse(url=custom_url, status_code=302)
    
    launcher_path = os.path.join(os.path.dirname(__file__), "static", "downloads", "DanyaClient-Launcher.exe")
    if not os.path.exists(launcher_path):
        os.makedirs(os.path.dirname(launcher_path), exist_ok=True)
        with open(launcher_path, "wb") as f:
            f.write(b"MZ\x90\x00" + b"\x00" * 58 + b"\x80\x00\x00\x00" + b"DanyaClient Official Client Launcher v1.21.11\r\n" + b"\x00" * 2048)
            
    return FileResponse(
        path=launcher_path,
        filename="DanyaClient-Launcher.exe",
        media_type="application/octet-stream"
    )

class ChangePasswordPayload(BaseModel):
    old_password: str
    new_password: str

@app.post("/api/change-password")
async def api_change_password(payload: ChangePasswordPayload, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, salt FROM users WHERE id = ?", (user["id"],))
    u_row = cursor.fetchone()

    check_hash, _ = hash_password(payload.old_password, u_row["salt"])
    if check_hash != u_row["password_hash"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash, new_salt = hash_password(payload.new_password)
    cursor.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (new_hash, new_salt, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Password updated successfully"}

@app.post("/api/reset-hwid")
async def api_reset_hwid(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET hwid = NULL WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "HWID reset successfully", "hwid": "—"}

class BannerPayload(BaseModel):
    banner_url: str

@app.post("/api/change-banner")
async def api_change_banner(payload: BannerPayload, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET banner_url = ? WHERE id = ?", (payload.banner_url.strip(), user["id"]))
# ================= ADMIN ROUTES =================
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    if user.get("role") != "admin":
        return templates.TemplateResponse(
            request=request, 
            name="403.html", 
            context={"user": user, "active_page": "admin"},
            status_code=403
        )
    return templates.TemplateResponse(
        request=request, 
        name="admin.html", 
        context={
            "user": user, 
            "active_page": "admin",
            "launcher_url": get_launcher_url()
        }
    )

@app.get("/api/admin/stats")
async def api_admin_stats(request: Request):
    require_admin(request)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admin_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM license_keys")
    total_keys = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM license_keys WHERE is_used = 0")
    active_keys = cursor.fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "banned_users": banned_users,
        "admin_users": admin_users,
        "total_keys": total_keys,
        "active_keys": active_keys
    }

@app.get("/api/admin/users")
async def api_admin_get_users(request: Request):
    require_admin(request)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, email, role, subscription, subscription_until,
               hwid, banner_url, is_banned, ban_reason, created_at, uid
        FROM users
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    users_list = []
    for r in rows:
        u = dict(r)
        user_uid = u.get("uid") or (999 + u['id'])
        u["uid"] = f"#{user_uid}"
        try:
            dt = datetime.fromisoformat(str(u["created_at"]))
            u["registered_date"] = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            u["registered_date"] = "16.10.2026"
        users_list.append(u)
    return {"users": users_list}

class BanPayload(BaseModel):
    user_id: int
    is_banned: bool
    ban_reason: Optional[str] = "Нарушение правил проекта"

@app.post("/api/admin/users/ban")
async def api_admin_ban_user(payload: BanPayload, request: Request):
    admin = require_admin(request)
    if payload.user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать собственный аккаунт администратора")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (payload.user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if target["username"] == "INOAGENT":
        conn.close()
        raise HTTPException(status_code=400, detail="Нельзя заблокировать главного администратора INOAGENT")
    
    if payload.is_banned:
        cursor.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE id = ?", (payload.ban_reason or "Нарушение правил", payload.user_id))
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (payload.user_id,))
        msg = f"Пользователь {target['username']} успешно заблокирован на сайте."
    else:
        cursor.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = ?", (payload.user_id,))
        msg = f"Пользователь {target['username']} успешно разблокирован."
    
    conn.commit()
    conn.close()
    return {"status": "ok", "message": msg, "user_id": payload.user_id, "is_banned": payload.is_banned}

class RolePayload(BaseModel):
    user_id: int
    role: str

@app.post("/api/admin/users/role")
async def api_admin_set_role(payload: RolePayload, request: Request):
    admin = require_admin(request)
    new_role = payload.role.strip().lower()
    if new_role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Недопустимая роль. Доступно: user, admin")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (payload.user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if target["username"] == "INOAGENT" and new_role != "admin":
        conn.close()
        raise HTTPException(status_code=400, detail="Нельзя снять роль администратора с INOAGENT")

    if payload.user_id == admin["id"] and new_role != "admin":
        conn.close()
        raise HTTPException(status_code=400, detail="Нельзя снять права администратора с самого себя")
    
    cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, payload.user_id))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"Роль пользователя {target['username']} изменена на {new_role}", "role": new_role}

class AdminResetHwidPayload(BaseModel):
    user_id: int

@app.post("/api/admin/users/reset-hwid")
async def api_admin_reset_user_hwid(payload: AdminResetHwidPayload, request: Request):
    require_admin(request)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET hwid = NULL WHERE id = ?", (payload.user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "HWID пользователя успешно сброшен"}

class AdminSubPayload(BaseModel):
    user_id: int
    subscription: str

@app.post("/api/admin/users/subscription")
async def api_admin_set_sub(payload: AdminSubPayload, request: Request):
    require_admin(request)
    sub = payload.subscription.strip()
    if sub == "Lifetime":
        until = "Forever"
    elif sub == "90 Days":
        until = "16.01.2027"
    elif sub == "30 Days":
        until = "16.11.2026"
    else:
        sub = "Free"
        until = "Unavailable"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET subscription = ?, subscription_until = ? WHERE id = ?", (sub, until, payload.user_id))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"Подписка обновлена: {sub} ({until})", "subscription": sub, "subscription_until": until}

@app.get("/api/admin/keys")
async def api_admin_get_keys(request: Request):
    require_admin(request)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, key_code, key_type, is_used, used_by_user_id, used_by_username, used_at, created_at
        FROM license_keys
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return {"keys": [dict(r) for r in rows]}

class CreateKeysPayload(BaseModel):
    key_type: str
    count: int = 1
    prefix: Optional[str] = None

@app.post("/api/admin/keys/create")
async def api_admin_create_keys(payload: CreateKeysPayload, request: Request):
    require_admin(request)
    count = max(1, min(payload.count, 50))
    valid_types = ["30 Days", "90 Days", "Lifetime", "HWID Reset"]
    k_type = payload.key_type if payload.key_type in valid_types else "30 Days"
    
    type_abbr = {
        "30 Days": "30D",
        "90 Days": "90D",
        "Lifetime": "LIFE",
        "HWID Reset": "HWID"
    }.get(k_type, "KEY")

    created_keys = []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for _ in range(count):
        pfx = payload.prefix.strip().upper() if payload.prefix else f"DC-{type_abbr}"
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        part3 = secrets.token_hex(2).upper()
        key_code = f"{pfx}-{part1}-{part2}-{part3}"
        cursor.execute("INSERT INTO license_keys (key_code, key_type) VALUES (?, ?)", (key_code, k_type))
        created_keys.append(key_code)

    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"Сгенерировано {count} ключей ({k_type})", "keys": created_keys, "count": count, "key_type": k_type}

@app.delete("/api/admin/keys/{key_id}")
async def api_admin_delete_key(key_id: int, request: Request):
    require_admin(request)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM license_keys WHERE id = ? AND is_used = 0", (key_id,))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    if rows == 0:
        raise HTTPException(status_code=400, detail="Ключ не найден или уже был активирован")
    return {"status": "ok", "message": "Ключ успешно удален"}

# ================= LAUNCHER URL ADMIN ENDPOINTS =================
@app.get("/api/admin/launcher-url")
async def api_admin_get_launcher_url(request: Request):
    require_admin(request)
    return {"launcher_url": get_launcher_url()}

class LauncherUrlPayload(BaseModel):
    launcher_url: str

@app.post("/api/admin/launcher-url")
async def api_admin_update_launcher_url(payload: LauncherUrlPayload, request: Request):
    require_admin(request)
    raw_url = payload.launcher_url.strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="Ссылка не может быть пустой")
    if not (raw_url.startswith("http://") or raw_url.startswith("https://") or raw_url.startswith("/")):
        raw_url = "https://" + raw_url
    saved_url = set_launcher_url(raw_url)
    return {
        "status": "ok", 
        "message": "Ссылка на лаунчер успешно обновлена и активна для всех пользователей!",
        "launcher_url": saved_url
    }

# ================= RAILWAY DATABASE SYNC & BACKUP =================
@app.get("/api/system/backup/export")
@app.get("/api/admin/database/backup")
async def api_system_export_db(request: Request):
    verify_backup_auth(request)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        conn.close()
    except Exception:
        pass

    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="Файл базы данных не найден")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        path=DB_PATH,
        filename=f"danyaclient_{timestamp}.db",
        media_type="application/x-sqlite3"
    )

@app.post("/api/system/backup/restore")
@app.post("/api/admin/database/restore")
async def api_system_restore_db(request: Request):
    verify_backup_auth(request)

    body_bytes = await request.body()
    if len(body_bytes) < 100:
        raise HTTPException(status_code=400, detail="Размер файла слишком мал для базы данных SQLite")

    if not body_bytes.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=400, detail="Загруженный файл не является валидной базой данных SQLite")

    temp_incoming = DB_PATH + ".incoming"
    try:
        with open(temp_incoming, "wb") as f:
            f.write(body_bytes)

        # Integrity verification
        test_conn = sqlite3.connect(temp_incoming)
        test_c = test_conn.cursor()
        test_c.execute("PRAGMA integrity_check")
        status_row = test_c.fetchone()
        if not status_row or status_row[0] != "ok":
            test_conn.close()
            os.remove(temp_incoming)
            raise HTTPException(status_code=400, detail="Ошибка целостности загруженной базы данных")

        test_c.execute("SELECT COUNT(*) FROM users")
        users_cnt = test_c.fetchone()[0]
        test_c.execute("SELECT COUNT(*) FROM license_keys")
        keys_cnt = test_c.fetchone()[0]
        test_conn.close()

        # Create safety backup of existing DB
        if os.path.exists(DB_PATH):
            shutil.copyfile(DB_PATH, DB_PATH + ".bak")

        # Replace database file
        shutil.move(temp_incoming, DB_PATH)

        # Re-initialize to ensure schemas/settings are refreshed
        init_db()

        return {
            "status": "ok",
            "message": f"База данных успешно восстановлена! Загружено {users_cnt} пользователей и {keys_cnt} ключей.",
            "users_count": users_cnt,
            "keys_count": keys_cnt
        }
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(temp_incoming):
            try:
                os.remove(temp_incoming)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Ошибка восстановления базы: {str(e)}")

@app.get("/api/system/backup/info")
async def api_system_backup_info(request: Request):
    verify_backup_auth(request)
    
    size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    size_kb = round(size_bytes / 1024, 1)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM license_keys")
    keys_cnt = c.fetchone()[0]
    conn.close()

    mtime = datetime.fromtimestamp(os.path.getmtime(DB_PATH)).strftime("%d.%m.%Y %H:%M:%S") if os.path.exists(DB_PATH) else "—"

    return {
        "status": "ok",
        "db_path": DB_PATH,
        "size_kb": size_kb,
        "users_count": users_cnt,
        "keys_count": keys_cnt,
        "last_modified": mtime,
        "backup_secret_key": BACKUP_SECRET_KEY
    }

@app.get("/api/stats")
async def api_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    db_users = cursor.fetchone()[0]
    conn.close()
    total_users = 542 + db_users
    return {
        "users_count": total_users,
        "client_version": "1.21.11",
        "supported_engines": ["Fabric", "Forge", "Vanilla"],
        "status": "online",
        "ping_ms": 14
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
    except (ValueError, TypeError):
        port = 8000
    uvicorn.run("main:app", host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
