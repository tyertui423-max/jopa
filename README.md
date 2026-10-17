# DanyaClient — Gaming Client Web Portal (Python / FastAPI)

Современный и атмосферный веб-сайт игрового клиента **DanyaClient**, полностью адаптированный под дизайн из макетов и скриншотов, готовый к бесплатному деплою на **[Railway.com](https://railway.com)**.

---

## 🚀 Особенности

- **Дизайн 1:1 по скриншотам**:
  - **Login (Скриншот 1)**: Стильная левая док-панель авторизации на фоне ночной беседки Minecraft с фонарями, кастомный логотип `DanyaClient`, Cloudflare Turnstile виджет (`Идет проверка..` / `Успешно.`), ссылка «Forgot password?» и лавандовая кнопка входа `Login`.
  - **Products / Магазин (Скриншот 2)**: Верхний заголовок «Your game. Your advantage.», гигантский стилизованный логотип `D` («Built for your game.»), фильтры-пилюли `Subscriptions` и `Add-ons`, счетчик `03 products`, и 3 карточки тарифов (30 Days — 269 ₽, 90 Days — 399 ₽, Lifetime — 599 ₽ с бейджем «Best value») с кнопками «Purchase →».
  - Плавающий стеклянный Dock / Navigation Bar по центру с логотипом `D` и ссылками Home, Functions, FAQ, Products, Login, Registration.
  - Атмосферный ночной Hero-блок в дожде с аутентичной графикой Minecraft.
  - Блок функций «Why Us?» (Optimization, Aesthetics, Safety) с HUD-превью и бейджами.
  - Аккордеон FAQ («Answers to popular questions») с раскрывающимися ответами.
  - Финальный баннер «Ready for new achievements together in DanyaClient?».
  - Полноценный футер с живым счетчиком пользователей (`over 500 users •`) и ссылками.
  - Страница регистрации с рабочим виджетом Cloudflare Turnstile и валидацией.
- **Бэкенд на Python**:
  - Фреймворк: **FastAPI** + **Uvicorn** + **Jinja2**
  - База данных: **SQLite** (`danyaclient.db`) с безопасным хешированием паролей (SHA-256 + Salt)
  - Сессии через защищенные cookies (HttpOnly, SameSite)
  - REST API эндпоинты (`/api/register`, `/api/login`, `/api/stats`, `/api/logout`)
- **Готов к деплою на Railway**:
  - `Procfile`
  - `railway.json` (Nixpacks builder)
  - `Dockerfile` (на случай сборки через Docker)
  - `requirements.txt`

---

## 🛠 Локальный запуск (Localhost)

1. Убедитесь, что установлен Python 3.10+:
   ```bash
   python --version
   ```

2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Запустите сервер:
   ```bash
   python main.py
   ```
   *или:*
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Откройте в браузере:
   **[http://localhost:8000](http://localhost:8000)**

---

## ☁️ Бесплатный деплой на Railway (Пошагово)

### Способ 1: Через GitHub (Самый простой)

1. Загрузите файлы этого проекта в свой GitHub репозиторий:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for DanyaClient site"
   git remote add origin https://github.com/ВАШ_ЛОГИН/danyaclient-site.git
   git push -u origin main
   ```

2. Зайдите на сайт **[railway.com](https://railway.com)** и войдите через GitHub.
3. Нажмите кнопку **«+ New Project»** → выберите **«Deploy from GitHub repo»**.
4. Выберите репозиторий `danyaclient-site`.
5. Railway автоматически обнаружит Python, установит `requirements.txt` и запустит команду из `Procfile`.
6. Перейдите во вкладку **Settings** сервиса → в разделе **Networking** нажмите **«Generate Domain»**.
7. Получите бесплатный публичный адрес: `https://danyaclient-production.up.railway.app`!

---

## 📁 Структура проекта

```
inoagent site/
├── main.py                  # Сервер FastAPI, роутинг, SQLite база данных и API
├── requirements.txt         # fastapi, uvicorn, jinja2, pydantic
├── Procfile                 # Команда запуска для Railway
├── railway.json             # Конфигурация деплоя Railway Nixpacks
├── Dockerfile               # Контейнеризация проекта
├── templates/
│   ├── base.html            # Базовый шаблон со стеклянным dock, модальным окном и футером
│   ├── index.html           # Главная страница (Hero, Functions, FAQ, CTA)
│   ├── login.html           # Левая док-панель входа (Скриншот 1)
│   ├── register.html        # Страница регистрации с Turnstile
│   └── products.html        # Страница тарифов 269/399/599 ₽ (Скриншот 2)
└── static/
    ├── css/style.css        # Современная дизайн-система, Glassmorphism, сетки
    ├── js/main.js           # Обработчики форм, анимация Turnstile, аккордеон FAQ
    └── images/              # Атмосферные изображения Minecraft
```

---

© 2026 DanyaClient, Inc. All rights reserved.
