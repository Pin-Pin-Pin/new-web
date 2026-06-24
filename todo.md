    <picture class="bg">
        <source srcset="https://www.cet-taiwan.org/sites/cet-taiwan.org/files/u422/.webp" type="image/webp" />
        <source media="(min-width: 768px)" srcset="https://www.cet-taiwan.org/sites/cet-taiwan.org/files/u422/.webp" type="image/webp" />
        <source media="(min-width: 1400px)" srcset="https://www.cet-taiwan.org/sites/cet-taiwan.org/files/u422/.webp" type="image/webp" />
        <img decoding="async" fetchpriority="high" alt="" src="https://www.cet-taiwan.org/sites/cet-taiwan.org/files/u422/.jpg" />
    </picture>


#上稿時
<meta name="robots" content="noindex,nofollow">拿掉

我想請你撰寫一隻python程式碼，依次執行以下步驟：
1.讓使用者輸入html的檔名，建立同名資料夾，將該檔案內img標籤的圖片下載到該資料夾。
2.推算圖片在這些寬度下所需的寬度，手機以375px計算，圖片寬度要再*2；平板寬度以768px計算，電腦寬度以1400px計算。請先幫我想下有沒有比較簡單的邏輯可以推算
container寬度或
3.將資料夾內的圖片依據上一步推算的結果，分別重新調整圖片大小(寬度縮小，長寬比不變)，分別命名為原檔名加上底線與裝置類型後墜，例如原本為btn.png，則變成btn_mb.png、btn_tbl.png、btn_dt.png，放入新資料夾，新資料夾檔名為原資料夾名稱加上_change
4.將_change資料夾中的圖片轉成webp檔案
3.在html中將原先img的結構改成使用picture+source+img標籤，並在source標籤分別使用media為手機(<768px)、平板(>=768px)桌機(>=1200px)設定不同寬度的webp圖片。

4.將_change資料夾中的圖片轉成webp檔案。指令為 cd _change資料夾，
3.在html中將原先img的結構改成使用picture+source+img標籤，並在source標籤分別使用media為手機(<768px)、平板(>=768px)桌機(>=1200px)設定不同寬度的webp圖片。

##merge.js
style標籤請幫我加上
body模式改成移除meta tag，不只是註解。另外style標籤也加上type="text/css"

##工作區
上稿前(盡量不調整跑版，或調整要在code註記)

募款頁：放測試募款頁
自由頁面：邀請分享、成為志工、成為實習生、成為員工、關於我們：放gb自編內容
拖拉編輯landing page：放gb自編內容

先看跑版嚴不嚴重
避免被搜尋、seo問題有要設定那個嗎
確認這個有被加上<meta name="robots" content="noindex">

要怎麼不把b放入sitemap?並且不要出現在官網文章列表?還是讓它出現在很舊的地方


上稿後：直接上
##共同
按鈕在手機按下會變成文字周遭會被圈起來
按鈕檢查、按鈕其他互動樣式
通用募款頁、違章募款頁表單、footer

##通用募款頁
拼圖還是不清楚

##違章募款頁
圖片替換webp跟rwd，手機有點不清楚
裝飾等footer好ㄌ再看高度有無要調整
footer


container padding上下左右統一
請ai寫一個自動切圖py


##研究
    /* height: auto; 5這是預設嗎*/
為甚麼內容容器是用max-width不是用width設定?
section container-fluid的使用情境
block 和 flex分別要怎麼致中 靠左靠右
研究下是怎麼透過grid來控制卡片slogan和卡片換行的

把 display: flex 放在 section 層級?
inline flex

#問山抓
按鈕點擊後樣式？