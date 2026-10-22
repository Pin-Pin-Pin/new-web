/**
 * 統一 CiviCRM 電子報 iframe 樣式
 * 父層請用 .newsletter-card > .newsletter-embed 包住 iframe.crm-container-embed
 * data-hide-group="true" 隱藏訂閱群組列
 * data-btn-color / data-btn-hover 訂閱按鈕配色
 */
(function () {
  if (window.cetNewsletterEmbedLoaded) return;
  window.cetNewsletterEmbedLoaded = true;
  var STYLE_ID = "cet-newsletter-embed-style";
  var FONT_ID = "cet-newsletter-embed-font";
  var RECAPTCHA_W = 304;
  var RECAPTCHA_H = 78;

  function cssText(iframe) {
    var hideGroup = iframe.getAttribute("data-hide-group") === "true";
    var btn = iframe.getAttribute("data-btn-color") || "#35A97C";
    var hover = iframe.getAttribute("data-btn-hover") || "#55716C";
    return [
      "html,body{margin:0;padding:0;background:transparent!important;overflow:visible!important;font-family:\"Noto Sans TC\",\"PingFang TC\",\"Microsoft JhengHei\",sans-serif!important;}",
      "#crm-container,.crm-container{margin:0 auto!important;padding:0!important;max-width:100%;width:100%;background:transparent!important;box-shadow:none!important;overflow:visible!important;text-align:center;}",
      ".crm-container>p{display:none!important;}",
      "#editrow-last_name,#editrow-first_name,#editrow-email-1,#editrow-group{display:flex!important;flex-direction:column;align-items:stretch;float:none!important;clear:both!important;width:100%!important;max-width:100%!important;margin:0 0 12px!important;padding:0!important;min-height:0!important;height:auto!important;overflow:visible!important;text-align:left!important;}",
      hideGroup ? "#editrow-group{display:none!important;}" : "",
      ".label,.edit-value.content{float:none!important;width:100%!important;max-width:100%;margin:0 0 4px!important;padding:0!important;text-align:left!important;}",
      ".crm-container label{display:block!important;width:100%!important;text-align:left!important;font-size:14px!important;line-height:1.5!important;color:#3E3E3E!important;font-family:\"Noto Sans TC\",sans-serif!important;}",
      "input.form-text,input[type=text],input[type=email]{box-sizing:border-box!important;width:100%!important;max-width:100%!important;height:40px!important;padding:0 14px!important;border:1px solid #D0D0D0!important;border-radius:4px!important;background:#FAFAFA!important;color:#2B2B2B!important;font-size:16px!important;line-height:24px!important;font-family:\"Noto Sans TC\",sans-serif!important;}",
      "#editrow-group table,#crm-tagGroupTable{margin:0 auto!important;width:auto!important;max-width:100%!important;border:0!important;}",
      ".crm-section.recaptcha-section{display:flex!important;justify-content:flex-start;align-items:flex-start;margin:8px 0 12px!important;overflow:visible!important;float:none!important;width:100%!important;}",
      ".g-recaptcha{transform-origin:top left;}",
      ".crm-submit-buttons{display:block!important;float:none!important;width:100%!important;margin:0!important;padding:0!important;overflow:visible!important;}",
      ".crm-submit-buttons .crm-button{display:block!important;float:none!important;width:100%!important;max-width:100%!important;margin:0!important;padding:0!important;height:auto!important;overflow:visible!important;background:none!important;border:0!important;}",
      "#_qf_Edit_next,input.form-submit.default{display:block!important;box-sizing:border-box!important;width:100%!important;max-width:100%!important;height:40px!important;min-height:40px!important;padding:0 16px!important;border:0!important;border-radius:4px!important;background:" + btn + "!important;color:#fff!important;font-size:16px!important;line-height:40px!important;font-family:\"Noto Sans TC\",sans-serif!important;cursor:pointer;overflow:visible!important;}",
      "#_qf_Edit_next:hover,#_qf_Edit_next:focus,input.form-submit.default:hover,input.form-submit.default:focus{background:" + hover + "!important;color:#fff!important;}",
      "#_qf_Edit_cancel,.crm-button-type-cancel,.crm-button-type-cancel .form-submit{display:none!important;}"
    ].join("");
  }

  function polish(doc) {
    var btn = doc.getElementById("_qf_Edit_next") || doc.querySelector("input.form-submit.default");
    if (btn) btn.value = "訂閱";
  }

  function scaleRecaptcha(iframe, doc) {
    var section = doc.querySelector(".crm-section.recaptcha-section");
    var widget = doc.querySelector(".g-recaptcha") || (section && section.querySelector("div"));
    if (!widget) return;
    var avail = iframe.clientWidth || 0;
    var scale = avail > 0 && avail < RECAPTCHA_W ? avail / RECAPTCHA_W : 1;
    widget.style.transformOrigin = "top left";
    widget.style.transform = scale < 0.999 ? "scale(" + scale + ")" : "none";
    if (section) {
      section.style.justifyContent = "flex-start";
      section.style.overflow = "visible";
      section.style.height = Math.ceil(RECAPTCHA_H * scale) + "px";
      section.style.minHeight = Math.ceil(RECAPTCHA_H * scale) + "px";
    }
  }

  function fitHeight(iframe) {
    var doc;
    try {
      doc = iframe.contentDocument || iframe.contentWindow.document;
    } catch (e) {
      return;
    }
    if (!doc || !doc.body) return;
    scaleRecaptcha(iframe, doc);
    var btn = doc.getElementById("_qf_Edit_next") || doc.querySelector("input.form-submit.default");
    var h = 0;
    if (btn) {
      var br = btn.getBoundingClientRect();
      var y = (doc.defaultView && doc.defaultView.pageYOffset) || 0;
      h = Math.ceil(br.bottom + y + 8);
    } else {
      h = Math.max(doc.documentElement.scrollHeight || 0, doc.body.scrollHeight || 0);
    }
    iframe.style.height = Math.max(h, 1) + "px";
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
    polish(doc);
    fitHeight(iframe);
    return true;
  }

  function resize(iframe) {
    fitHeight(iframe);
    if (iframe.iFrameResizer) iframe.iFrameResizer.resize();
  }

  function setup(iframe) {
    var n = 0;
    var timer = setInterval(function () {
      n += 1;
      inject(iframe);
      resize(iframe);
      if (n > 40) clearInterval(timer);
    }, 200);
    iframe.addEventListener("load", function () {
      inject(iframe);
      setTimeout(function () { resize(iframe); }, 400);
      setTimeout(function () { resize(iframe); }, 1200);
      setTimeout(function () { resize(iframe); }, 2500);
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
    window.addEventListener("resize", function () {
      var list = document.querySelectorAll("iframe.crm-container-embed");
      for (var i = 0; i < list.length; i++) resize(list[i]);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
