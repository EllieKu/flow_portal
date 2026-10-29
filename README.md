# Flow Portal

單一組織內部的 Bot 入口，提供帳號登入、Bot 管理、群組／個人授權，以及透過 Dify API 使用聊天與歷史對話。

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

聊天開發請使用 ASGI 伺服器：

```bash
uvicorn config.asgi:application --host 127.0.0.1 --port 8002
```

`runserver` 使用 WSGI，串流回覆可能等到生成完成後才一次顯示，因此只適合不需測試聊天串流的後台開發：

```bash
python manage.py runserver
```

- Portal：http://127.0.0.1:8002/
- 登入：http://127.0.0.1:8002/login/
- 管理後台：http://127.0.0.1:8002/admin/
- Bot 清單：http://127.0.0.1:8002/bots/（登入後首頁亦顯示清單）

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
| `DIFY_READ_TIMEOUT` | 等待 Dify 串流資料的逾時秒數，預設為 `120` |


## 模組

- `config`：設定、根路由與 ASGI／WSGI 入口。
- `accounts`：使用者、Admin、登入登出及受保護首頁。
- `bots`：Bot 設定、Admin、共用授權與快取、可用 Bot 清單及受保護入口。
- `chat`：聊天頁、歷史對話、Dify API 串接、串流回覆與停止生成。
