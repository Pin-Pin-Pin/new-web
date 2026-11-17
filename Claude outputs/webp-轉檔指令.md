# 圖片轉 WebP 作業指令（給 AI Agent）

## 任務
把指定的 PNG / JPG 圖片轉成 WebP，依圖片類型選擇最適合的編碼方式。目標依序為：
1. **清晰**：圖表、文字、線條、Logo 不可模糊、不可出現色邊或雜訊。
2. **檔案小**：WebP 必須比來源檔小，否則保留來源格式。
3. **不破壞原檔**：原始圖片一律唯讀，輸出到新資料夾。

## 使用工具
- ImageMagick（`magick`）：讀取資訊、縮尺寸、輸出中間檔。
- libwebp（`cwebp`）：WebP 編碼。
- 開始前先執行 `magick -version` 與 `cwebp -version`。任一指令不存在就停止，並回報需要安裝哪一個工具。
- 不要使用 `cwebp -resize`。縮尺寸一律由 ImageMagick 處理。

---

## 步驟 1：判斷每張圖的兩個屬性

### 1-1 是否透明
```
magick identify -format "%[opaque]" input.png
```
- `False` → **透明**（含半透明像素）
- `True` → **不透明**（即使 PNG 帶有 alpha 通道，只要全部不透明就視為不透明）
- JPG 一律視為不透明。

### 1-2 是照片還是圖像（圖表、文字、截圖、Logo、圖示、扁平插畫）
依下列順序判斷，**前面的規則優先**：
1. 使用者明確指定類型（例如資料夾名稱、檔名含 chart／圖表／logo／icon／screenshot，或在指令中說明）→ 依使用者的指定。
2. 來源是 JPG → **照片**。
3. 計算顏色數：
   ```
   magick identify -format "%k" input.png
   ```
   - ≤ 256 色 → **圖像**
   - 其他情況：查看圖片內容。有大面積純色、清晰文字或細線 → **圖像**；連續漸層、自然場景、人像、產品攝影 → **照片**。
4. 仍無法確定 → 當作**圖像**處理（無損最安全），並在報告中註明「類型不確定」。

依兩個屬性組合，每張圖會落入下列 A–D 其中一類。

---

## 步驟 2：縮尺寸（需要時）

- **不放大**：目標寬度大於原圖寬度時，直接使用原寬度。
- 依固定寬度等比例縮放：`-resize {寬度}x`
- 中間檔一律存成 PNG（無損），再交給 cwebp 編碼。

| 類型 | 縮圖指令 |
|---|---|
| 不透明 | `magick input -strip -alpha off -resize {W}x PNG24:tmp.png` |
| 透明 | `magick input -strip -resize {W}x PNG32:tmp.png` |
| 圖像類且縮小超過 30% | 在 `-resize` 後加 `-unsharp 0x0.75+0.75+0.008`，補回文字銳利度 |

> 圖表類圖片若需大幅縮小，請在報告中建議使用者改從原始檔（Excel、Figma、Canva 等）直接匯出目標尺寸，這樣文字最清楚。

不需縮尺寸時，直接把原檔交給 cwebp（不透明的 PNG 仍可先用 `-alpha off` 轉出中間檔）。

---

## 步驟 3：依類型編碼

### A. 照片．不透明（一般照片、活動照、風景、人像）
```
cwebp -preset photo -q 80 -m 6 -sharp_yuv -mt tmp.png -o output.webp
```
- 品質參考：主視覺／大圖 `-q 80`；內文圖 `-q 78`；縮圖、卡片小圖 `-q 75`。
- 來源是已經高度壓縮的 JPG 時，WebP 可能反而比較大。處理方式：每次 `-q` 降 5 重新編碼，最低降到 70；仍比較大就保留 JPG。

### B. 照片．透明（去背的人物、商品去背圖）
```
cwebp -preset photo -q 80 -m 6 -sharp_yuv -alpha_q 100 -alpha_filter best -mt tmp.png -o output.webp
```
- `-alpha_q 100` 讓透明邊緣維持無損，避免去背邊緣出現鋸齒或毛邊。
- 比對對象是來源 PNG；WebP 通常會明顯較小。

### C. 圖像．不透明（圖表、資訊圖、截圖、含文字的圖片）
**禁止使用有損編碼。** 依序嘗試，取第一個比來源 PNG 小的結果：
1. 無損，最大壓縮：
   ```
   cwebp -lossless -z 9 -mt tmp.png -o output.webp
   ```
2. 如果仍 ≥ 來源 PNG，改用近無損：
   ```
   cwebp -lossless -near_lossless 60 -z 9 -mt tmp.png -o output.webp
   ```
   還是太大可以改用 `-near_lossless 40`，不要低於 40。
3. 還是 ≥ 來源 PNG（通常是已被 pngquant/TinyPNG 壓過的 8-bit PNG）→ **不輸出 WebP，保留 PNG**，並在報告中註明。

### D. 圖像．透明（Logo、圖示、透明背景的圖表）
與 C 相同的三個步驟（`-lossless -z 9` → `-near_lossless 60` → 保留 PNG）。
- 無損模式會完整保留透明度。cwebp 預設會調整「完全透明像素」底下的顏色來提高壓縮率，肉眼看不出差異，不需要加 `-exact`。

### 參數說明（避免誤用）
- 無損模式下的 `-q` 代表壓縮努力程度，**不是畫質**。使用 `-z 9` 時可以忽略 `-q` 與 `-m`。
- `-sharp_yuv`：讓有損編碼的彩色邊緣比較銳利，照片類一律加上。
- `-preset` 必須是 cwebp 的第一個參數。
- 不要對圖表、文字類使用 `-preset text` 搭配有損編碼來取代無損；只有使用者明確要求有損時才可以使用，而且至少要 `-preset text -q 90 -m 6 -sharp_yuv`。

---

## 步驟 4：驗證
每張輸出圖都要檢查：
1. **尺寸**：`magick identify -format "%wx%h" output.webp` 與預期寬度一致。
2. **檔案大小**：WebP 必須小於來源檔，否則依上方規則處理（降品質或保留原格式）。
3. **畫質**：
   - C、D 類使用 `-lossless`（未加 near_lossless）時，應與中間檔完全一致：
     ```
     magick compare -metric AE tmp.png output.webp null:
     ```
     結果應為 `0`。
   - A、B 類與近無損：以 100% 比例檢視，確認文字、細線、去背邊緣沒有模糊、色邊或區塊雜訊。有疑慮時提高 `-q`（照片）或提高 `-near_lossless` 數值（圖像）後重做。
4. 透明圖確認輸出仍為透明：`magick identify -format "%[opaque]" output.webp` 應為 `False`。

---

## 輸出規則
- 輸出到新資料夾（例如 `webp-photo-q80/`、`webp-lossless/`），不覆蓋原檔。
- 檔名格式：`{原檔名}-{寬度}.webp`，例如 `report-chart-1200.webp`。
- 刪除暫存的中間檔。

## 最後回報
用表格列出每張圖：

| 檔名 | 類型（A/B/C/D） | 寬度 | 使用的參數 | 來源大小 | WebP 大小 | 節省 % | 備註（保留原檔／類型不確定／建議重新匯出等） |

並另外列出：
- 保留原格式、沒有輸出 WebP 的檔案與原因。
- 判斷為「類型不確定」的檔案，請使用者確認。
