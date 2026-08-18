(function () {
    var DEFAULT_AMOUNT_DATA = {
        monthly: [
            { amount: '500', desc: '用行動擺脫無力感，把不可能化為可能。' },
            { amount: '1000', desc: '成為守護環境的穩定社會力。' },
            { amount: '1500', desc: '從關注個案到監督制度，打造專業的環境倡議團隊。' }
        ],
        once: [
            { amount: '1200', desc: '一份捐款，一個珍貴的環保力！' },
            { amount: '3000', desc: '在關鍵時刻，挺身守護家園。' },
            { amount: '5000', desc: '和地球公民一起前進，看顧孕育我們的島嶼！' }
        ]
    };

    function mergeAmountData(defaults, overrides) {
        if (!overrides) return defaults;
        var merged = {};
        Object.keys(defaults).forEach(function (tabKey) {
            var baseList = defaults[tabKey] || [];
            var overrideList = overrides[tabKey] || [];
            merged[tabKey] = baseList.map(function (item, index) {
                var overrideItem = overrideList[index] || {};
                return {
                    amount: overrideItem.amount != null ? overrideItem.amount : item.amount,
                    desc: overrideItem.desc != null ? overrideItem.desc : item.desc
                };
            });
        });
        return merged;
    }

    var AMOUNT_DATA = mergeAmountData(DEFAULT_AMOUNT_DATA, window.DONATION_BOX_AMOUNT_DATA);
    var DEFAULT_OPTION_INDEX = 1;
    var TAB_TYPE = {
        monthly: 'recurring',
        once: 'non-recurring'
    };

    var box = document.getElementById('donation-box');
    if (!box) return;

    var tabs = box.querySelectorAll('.donation-box__tab');
    var panelAmount = document.getElementById('donate-panel-amount');
    var panelOther = document.getElementById('donate-panel-other');
    var amountList = document.getElementById('donate-amount-list');
    var customInput = document.getElementById('donate-custom-amount');
    var errorEl = document.getElementById('donate-amount-error');
    var submitBtn = document.getElementById('donate-submit');
    var currentTab = 'monthly';

    function toHalfWidthDigits(value) {
        return String(value || '')
            .replace(/[０-９]/g, function (ch) {
                return String.fromCharCode(ch.charCodeAt(0) - 0xFEE0);
            })
            .replace(/\D/g, '');
    }

    function getAmountOptions() {
        return amountList ? amountList.querySelectorAll('.donation-box__amount-option') : [];
    }

    function clearAmountSelection() {
        getAmountOptions().forEach(function (btn) {
            btn.classList.remove('is-active');
            btn.setAttribute('aria-pressed', 'false');
        });
    }

    function selectAmountOption(btn) {
        clearAmountSelection();
        if (!btn) return;
        btn.classList.add('is-active');
        btn.setAttribute('aria-pressed', 'true');
        if (customInput) customInput.value = '';
        hideAmountError();
    }

    function hideAmountError() {
        if (errorEl) errorEl.hidden = true;
    }

    function showAmountError() {
        if (errorEl) {
            errorEl.hidden = false;
            errorEl.focus && errorEl.focus();
        }
        if (customInput) customInput.focus();
    }

    function renderAmountOptions(tabKey) {
        var data = AMOUNT_DATA[tabKey];
        if (!data || !amountList) return;

        var options = getAmountOptions();
        data.forEach(function (item, index) {
            var btn = options[index];
            if (!btn) return;
            btn.setAttribute('data-amount', item.amount);
            var numberEl = btn.querySelector('.donation-box__number');
            var descEl = btn.querySelector('.donation-box__amount-desc');
            if (numberEl) numberEl.textContent = item.amount;
            if (descEl) descEl.textContent = item.desc;
        });

        if (customInput) customInput.value = '';
        selectAmountOption(options[DEFAULT_OPTION_INDEX] || options[0]);
        hideAmountError();
    }

    function setActiveTab(tabKey) {
        currentTab = tabKey;
        tabs.forEach(function (tab) {
            var isActive = tab.getAttribute('data-donate-tab') === tabKey;
            tab.classList.toggle('is-active', isActive);
            tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        var isOther = tabKey === 'other';
        if (panelAmount) {
            panelAmount.hidden = isOther;
            panelAmount.setAttribute('aria-labelledby', isOther ? '' : (tabKey === 'once' ? 'donate-tab-once' : 'donate-tab-monthly'));
        }
        if (panelOther) panelOther.hidden = !isOther;
        if (submitBtn) submitBtn.hidden = isOther;

        if (!isOther) {
            renderAmountOptions(tabKey);
        } else {
            hideAmountError();
        }
    }

    function getSelectedAmount() {
        var customAmount = toHalfWidthDigits(customInput && customInput.value);
        if (customAmount) {
            return customAmount;
        }
        var active = amountList && amountList.querySelector('.donation-box__amount-option.is-active');
        if (active) {
            return active.getAttribute('data-amount');
        }
        return null;
    }

    // netiCRM 金額預填：https://neticrm.tw/resources/2423#5
    // &_amt=金額（不在選項中則視為自訂金額）
    // &_grouping=recurring | non-recurring
    function getDonatePageBaseUrl() {
        var link = document.querySelector('link[rel="canonical"]');
        return (link && link.href) || 'https://dev.cet-taiwan.org/civicrm/contribute/transact?reset=1&id=43';
    }

    function buildDonateUrl(amount, grouping) {
        var url = new URL(getDonatePageBaseUrl(), window.location.href);
        url.searchParams.set('_amt', String(amount));
        url.searchParams.set('_grouping', grouping);
        return url.toString();
    }

    function goToDonatePage(amount, grouping) {
        var target = buildDonateUrl(amount, grouping);
        if (window.top && window.top !== window) {
            window.top.location.href = target;
        } else {
            window.location.href = target;
        }
    }

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            setActiveTab(tab.getAttribute('data-donate-tab'));
        });
    });

    if (amountList) {
        amountList.addEventListener('click', function (event) {
            var btn = event.target.closest('.donation-box__amount-option');
            if (!btn || !amountList.contains(btn)) return;
            selectAmountOption(btn);
        });
    }

    if (customInput) {
        customInput.addEventListener('input', function () {
            var normalized = toHalfWidthDigits(customInput.value);
            if (customInput.value !== normalized) {
                customInput.value = normalized;
            }
            if (normalized) {
                clearAmountSelection();
                hideAmountError();
            }
        });
        customInput.addEventListener('blur', function () {
            customInput.value = toHalfWidthDigits(customInput.value);
        });
    }

    if (submitBtn) {
        submitBtn.addEventListener('click', function () {
            if (currentTab === 'other') return;

            var selectedAmount = getSelectedAmount();
            if (!selectedAmount || selectedAmount === '0') {
                showAmountError();
                return;
            }

            hideAmountError();
            goToDonatePage(selectedAmount, TAB_TYPE[currentTab]);
        });
    }

    document.querySelectorAll('.donation-plan__cta[data-donate-tab]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tabKey = btn.getAttribute('data-donate-tab');
            if (!tabKey || !AMOUNT_DATA[tabKey]) return;
            setActiveTab(tabKey);
            box.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    window.DonationBox = {
        setTab: setActiveTab
    };

    setActiveTab('monthly');
})();
