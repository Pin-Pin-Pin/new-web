/**
 * 統一 CiviCRM 電子報 iframe 樣式（對齊 /civicrm/mailing/subscribe）
 * 父層請用 .newsletter-embed 包住 iframe.crm-container-embed
 * data-newsletter-theme="dark|light"（預設 light）
 * data-hide-group="true" 隱藏訂閱群組列
 */
(function () {
  if (window.cetNewsletterEmbedLoaded) return;
  window.cetNewsletterEmbedLoaded = true;
  var STYLE_ID = "cet-newsletter-embed-style";
  var FONT_ID = "cet-newsletter-embed-font";

  function cssText(iframe) {
    var dark = iframe.getAttribute("data-newsletter-theme") === "dark";
    var hideGroup = iframe.getAttribute("data-hide-group") === "true";
    var label = dark ? "#FAFAFA" : "#3E3E3E";
    return [
      "html,body{margin:0;padding:0;background:transparent!important;overflow:visible!important;font-family:\"Noto Sans TC\",\"PingFang TC\",\"Microsoft JhengHei\",sans-serif!important;}",
      "#crm-container,.crm-container{margin:0 auto!important;padding:8px 0 16px!important;max-width:360px;width:100%;background:transparent!important;box-shadow:none!important;overflow:visible!important;text-align:center;}",
      ".crm-container>p{display:none!important;}",
      "#editrow-last_name,#editrow-first_name,#editrow-email-1,#editrow-group{display:flex!important;flex-direction:column;align-items:stretch;float:none!important;clear:both!important;width:256px!important;max-width:100%!important;margin:0 auto 12px!important;padding:0!important;min-height:0!important;height:auto!important;overflow:visible!important;text-align:left!important;}",
      hideGroup ? "#editrow-group{display:none!important;}" : "",
      ".label,.edit-value.content{float:none!important;width:100%!important;max-width:100%;margin:0 0 4px!important;padding:0!important;text-align:left!important;}",
      ".crm-container label{display:block!important;width:100%!important;text-align:left!important;font-size:14px!important;line-height:1.5!important;color:" + label + "!important;font-family:\"Noto Sans TC\",sans-serif!important;}",
      "input.form-text,input[type=text],input[type=email]{box-sizing:border-box!important;width:100%!important;max-width:100%!important;height:40px!important;padding:0 14px!important;border:1px solid #D0D0D0!important;border-radius:4px!important;background:#FAFAFA!important;color:#2B2B2B!important;font-size:16px!important;line-height:24px!important;font-family:\"Noto Sans TC\",sans-serif!important;}",
      "#editrow-group table,#crm-tagGroupTable{margin:0 auto!important;width:auto!important;max-width:100%!important;border:0!important;}",
      ".crm-section.recaptcha-section{display:flex!important;justify-content:center;margin:16px 0!important;overflow:visible!important;float:none!important;width:100%!important;}",
      ".crm-submit-buttons{display:flex!important;justify-content:center;gap:8px;margin:16px 0 0!important;float:none!important;width:100%!important;}",
      "#_qf_Edit_next,input.form-submit.default{height:36px!important;min-height:36px!important;min-width:64px!important;padding:0 16px!important;border:0!important;border-radius:4px!important;background:#35A97C!important;color:#fff!important;font-size:16px!important;font-family:\"Noto Sans TC\",sans-serif!important;cursor:pointer;}",
      "#_qf_Edit_next:hover,#_qf_Edit_next:focus,input.form-submit.default:hover,input.form-submit.default:focus{background:#55716C!important;color:#fff!important;}",
      "#_qf_Edit_cancel,.crm-button-type-cancel .form-submit{height:36px!important;min-height:36px!important;padding:0 16px!important;border:1px solid #35A97C!important;border-radius:4px!important;background:#fff!important;color:#35A97C!important;font-size:16px!important;font-family:\"Noto Sans TC\",sans-serif!important;cursor:pointer;}"
    ].join("");
  }

  function inject(iframe) {
    var doc;
    try {
      doc = iframe.contentDocument || iframe.contentWindow.document;
    } catch (e) {
      return false;
    }
    if (!doc || !doc.head) return false;

    if (!doc.getElementById(FONT_ID)) {
      var font = doc.createElement("link");
      font.id = FONT_ID;
      font.rel = "stylesheet";
      font.href = "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap";
      doc.head.appendChild(font);
    }

    var style = doc.getElementById(STYLE_ID);
    if (!style) {
      style = doc.createElement("style");
      style.id = STYLE_ID;
      doc.head.appendChild(style);
    }
    style.textContent = cssText(iframe);
    return true;
  }

  function resize(iframe) {
    if (iframe.iFrameResizer) iframe.iFrameResizer.resize();
  }

  function setup(iframe) {
    var n = 0;
    var timer = setInterval(function () {
      n += 1;
      if (inject(iframe) || n > 40) {
        clearInterval(timer);
        resize(iframe);
      }
    }, 200);
    iframe.addEventListener("load", function () {
      inject(iframe);
      setTimeout(function () {
        resize(iframe);
      }, 400);
    });
  }

  function init() {
    var frames = document.querySelectorAll("iframe.crm-container-embed");
    for (var i = 0; i < frames.length; i++) setup(frames[i]);
    if (typeof iFrameResize === "function") {
      iFrameResize(
        { heightCalculationMethod: "lowestElement", checkOrigin: false },
        "iframe.crm-container-embed"
      );
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
