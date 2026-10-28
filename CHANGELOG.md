# Changelog

## 2026.10.28

### 新增

- 建立 Django 專案與 `accounts`、`bots`、`chat` 三個 app
- 使用 SQLite，提供初始 migration 與可設定的資料庫檔案位置。
- 建立自訂 User，為每個帳號產生固定且唯一的 Dify 使用者 UUID。
- 啟用 Django Admin，支援帳號、群組與帳號啟停管理。
- 提供前台登入、登出與受登入保護的首頁。
- 提供環境變數範例、套件依賴、Git 忽略規則與本機啟動說明。
