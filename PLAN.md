# Flow Portal

## 設計方向

提供單一組織內部使用的 Bot 入口，管理帳號與 Bot 使用權限，聊天功能透過後端串接 Dify API。資料表、API、快取與部署細節留待後續討論。

## 核心功能

### 後台：使用 Django Admin

- 帳號與群組管理。
- Bot 基本資料、啟停及 Dify 連線設定。
- 依群組或個人設定 Bot 使用權限。

### 前台

- 登入、登出。
- 顯示有權使用的 Bot。
- Bot 聊天頁：同頁提供新對話、歷史對話切換、串流回覆與停止生成。

## 架構方向

- Django + Django Templates + 輕量 JavaScript。
- 初期單機部署使用 SQLite 保存帳號、群組、Bot 設定（含 Dify 應用金鑰）與授權。
- Django 後端統一串接 Dify API，API Key 保留於後端。
- 使用固定的登入者識別向 Dify 查詢自己的歷史對話。
- 對話與訊息由 Dify 管理；Portal 不保存對話、訊息或生成控制狀態。
- Bot 更換 Dify 應用後，使用新應用的對話，不保留舊對話入口。
- 授權採快取優先，減少資料庫查詢；多 worker 部署的共用快取留待後續處理。

## 最小模組拆分

只建立三個 Django app，共用 Django 內建認證、群組與 Admin 功能。

| 模組 | 責任 |
|---|---|
| `accounts` | 使用者、固定的 Dify 使用者識別、登入與登出 |
| `bots` | Bot 設定、群組／個人授權、授權快取與可用 Bot 清單 |
| `chat` | 聊天與歷史對話同頁介面、Dify API 串接、串流與停止生成 |

- 專案設定、根路由與 ASGI 入口放在 `config`，不另建業務模組。
- Dify Adapter 先作為 `chat` 內的獨立 Python 檔案，不額外建立 integrations app。
- 授權判斷集中在 `bots`，聊天功能共用同一入口，避免重複實作。
- 不建立對話資料模型、獨立稽核模組、背景任務或生成狀態管理模組。

## 後續待辦與擴充

目前核心功能與單機部署說明已完成，完成項目記錄於 [CHANGELOG.md](CHANGELOG.md)。

- 初期以 SQLite 及單一 Uvicorn worker 部署。
- 正式環境可用後，依 [DEPLOYMENT.md](DEPLOYMENT.md) 驗證 HTTPS、反向代理、SSE、靜態檔案、服務重啟與 SQLite 備份還原。
- 使用量需要水平擴充時，再評估 PostgreSQL、共用快取與多 worker 部署。
- 附件、語音、Workflow 特有互動、SSO 與多租戶依實際需求規劃。

每階段只細化當下需要的介面與設定；優先完成可驗證的使用流程，再討論效能與部署細節。
