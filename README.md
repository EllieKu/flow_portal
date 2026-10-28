# Flow Portal

單一組織內部的 Bot 入口。第一階段提供 Django 專案骨架、SQLite、自訂使用者、管理後台及登入／登出。完整方向見 [PLAN.md](PLAN.md)。

## 安裝
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
```

## 啟動

開發：

```bash
python manage.py runserver
```

生產：

```bash
uvicorn config.asgi:application --host 127.0.0.1 --port 8002
```

- Portal：http://127.0.0.1:8002/
- 登入：http://127.0.0.1:8002/login/
- 管理後台：http://127.0.0.1:8002/admin/


## 測試

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```



## 環境變數

| 變數 | 說明 |
|---|---|
| `DJANGO_SECRET_KEY` | 必填；正式環境請提供獨立且固定的隨機密鑰 |
| `DJANGO_DEBUG` | 預設關閉；本機 HTTP 開發設為 `1` |
| `DJANGO_ALLOWED_HOSTS` | 允許的主機名稱，以逗號分隔 |
| `SQLITE_PATH` | SQLite 檔案位置，預設為專案根目錄 `db.sqlite3`；相對路徑以專案根目錄為準 |


## 模組

- `config`：設定、根路由與 ASGI／WSGI 入口。
- `accounts`：使用者、Admin、登入登出及受保護首頁。
- `bots`、`chat`：已註冊的 app 骨架，後續階段實作。
