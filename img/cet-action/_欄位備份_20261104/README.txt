地球公民基金會網站「行動介紹頁」欄位備份
備份時間：2026-11-04 15:36–15:50（台北時間）
來源：https://www.cet-taiwan.org/taxonomy/term/<編號>/edit（只讀取，未儲存任何變更）

檔案說明
- <編號>.json：每頁一個檔，內容為編輯頁所有可編輯欄位的值
    main_fields   名稱、所屬議題、代表圖（fids）、替代文字、焦點位置、描述與關鍵個案（原始 HTML）、上層、權重、發表狀態、路徑別名等
    main_files    代表圖檔名與檔案編號
    ief.field_action_item   「地球公民的行動」每個 row：標題、圖片 fids／檔名、替代文字、焦點位置、內文 HTML、文字格式
    ief.field_curation      「策展圖文區」每個 row：標題、圖片、摘要、連結
- all_pages.json：22 頁合併成一個檔
- 行動row對照.csv：每個 row 目前的圖片與預定換上的圖片（用 Excel 開啟）
- progress.csv：備份進度紀錄
- compare.py：換圖後再備份一次，用 python compare.py <換圖前資料夾> <換圖後資料夾> 逐欄比對

注意
- 348 已在 2026-10-29 換過圖，這份是換圖後的狀態。
- JSON 的鍵已排序、縮排，方便直接用文字比對工具（例如 VS Code / WinMerge）比較。
