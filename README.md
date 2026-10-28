# Flow Portal

單一組織內部的 Bot 入口，目前提供 SQLite、自訂使用者、登入／登出、Bot 管理、群組／個人授權與可用 Bot 清單。Dify 聊天功能於下一階段實作，完整方向見 [PLAN.md](PLAN.md)。

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
- Bot 清單：http://127.0.0.1:8002/bots/（登入後首頁亦顯示清單）

## Bot 管理與授權

1. 在 Admin 建立 Bot，填入名稱、說明、啟用狀態與 Dify API 網址。
2. 「API Key 環境變數名稱」填入例如 `DIFY_SUPPORT_API_KEY`，實際金鑰放在 `.env` 或部署環境，不直接填入後台。
3. 選擇授權使用者或群組；任一授權成立即可使用，未設定授權則沒有人可使用，管理員也不例外。
4. 使用者登入後可在清單開啟獲授權的 Bot。目前入口顯示基本資訊，下一階段再接上聊天與歷史對話。

未登入者導向登入頁；無權限、停用或不存在的 Bot 統一回傳 404。前台不輸出連線設定或金鑰。

授權結果採本機記憶體快取，固定有效 60 秒。透過 Admin 或一般模型儲存／關聯操作異動帳號、群組成員、Bot 與授權時，在交易提交後使目前程序的快取失效。快取故障時改查資料庫，不直接放行。

目前快取適用單一程序；多 worker 的其他程序，以及繞過模型事件的批次更新，最多需等待 60 秒才更新授權。需要多 worker 即時失效時再改用共用快取。此快取不保存對話或生成控制狀態。


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
- `bots`：Bot 設定、Admin、共用授權與快取、可用 Bot 清單及受保護入口。
- `chat`：已註冊的 app 骨架，下一階段實作 Dify 串接。
