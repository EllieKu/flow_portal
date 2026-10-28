# Changelog

## 2026.10.28

### Bot 管理與授權

- 新增 Bot 模型與 SQLite migration，使用 Django Admin 管理基本資料、啟停、Dify API 網址與金鑰環境變數名稱。
- 支援個人及群組授權，預設不授權，管理員不自動取得 Bot 使用權。
- 登入首頁與 `/bots/` 顯示可用 Bot 清單，入口共用授權判斷，防止直接網址繞過權限。
- 加入 60 秒本機授權快取、交易提交後失效及快取故障回退資料庫機制；多 worker 即時失效待共用快取支援。
- Django 系統檢查及 migration 一致性檢查通過，已套用 Bot migration。

### 新增

- 建立 Django 專案與 `accounts`、`bots`、`chat` 三個 app
- 使用 SQLite，提供初始 migration 與可設定的資料庫檔案位置。
- 建立自訂 User，為每個帳號產生固定且唯一的 Dify 使用者 UUID。
- 啟用 Django Admin，支援帳號、群組與帳號啟停管理。
- 提供前台登入、登出與受登入保護的首頁。
- 提供環境變數範例、套件依賴、Git 忽略規則與本機啟動說明。
