# Flow Portal 單機部署

本文件適用於單一主機、SQLite、單一 Uvicorn worker，以及由反向代理提供 HTTPS 的初期部署。

## 環境設定

正式環境的 `.env` 至少設定：

```dotenv
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=請替換為固定且足夠長的隨機字串
DJANGO_ALLOWED_HOSTS=portal.example.com
DJANGO_BEHIND_HTTPS_PROXY=1
SQLITE_PATH=/var/lib/flow-portal/db.sqlite3
DIFY_READ_TIMEOUT=120
```

`.env`、SQLite 檔案及備份都可能包含敏感資料，檔案權限應限制為執行服務的帳號可讀寫。

## 更新與啟動

在虛擬環境中安裝依賴、套用 migration 並收集靜態檔案：

```bash
python -m pip install -r requirements.txt
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
```

以單一 worker 啟動 ASGI 應用：

```bash
uvicorn config.asgi:application --host 127.0.0.1 --port 8002 --workers 1
```

單一 worker 可讓目前的本機授權快取立即失效，也符合 SQLite 的初期使用方式。需要多 worker 時，應先改用共用快取，再評估是否改用 PostgreSQL。

## 反向代理

以下為 Nginx 設定範例，網域、憑證及專案路徑需依環境調整：

```nginx
server {
    listen 80;
    server_name portal.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name portal.example.com;

    ssl_certificate /etc/letsencrypt/live/portal.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/portal.example.com/privkey.pem;

    location /static/ {
        alias /opt/flow_portal/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8002;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 180s;
    }
}
```

`proxy_buffering off` 讓聊天內容逐段送至瀏覽器。`DJANGO_BEHIND_HTTPS_PROXY=1` 只能在請求確實先經過可信任代理時啟用。

## SQLite 備份

使用 SQLite 的線上備份指令建立一致的備份：

```bash
sqlite3 /var/lib/flow-portal/db.sqlite3 ".backup '/var/backups/flow-portal/db.sqlite3'"
```

定期將備份複製到另一個受保護的位置，並實際演練還原。Bot 的 Dify API Key 以明文保存在資料庫中，因此備份必須採用與正式資料庫相同的存取限制。

## 部署後確認

```bash
python manage.py check --deploy
```

接著以一般帳號確認登入、Bot 清單、聊天串流、停止生成與歷史切換；以無權限帳號確認無法開啟該 Bot，並從瀏覽器開發工具確認回應內容沒有 Dify API Key。
