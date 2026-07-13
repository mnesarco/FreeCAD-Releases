function copySHA(hash, btn) {
    if (!hash) return;
    navigator.clipboard.writeText(hash).then(function () {
        showToast("SHA256 copied to clipboard");
        if (btn) {
            var icon = btn.querySelector("i");
            if (icon) {
                var orig = icon.className;
                icon.className = "ti ti-check";
                setTimeout(function () { icon.className = orig; }, 1500);
            }
        }
    }).catch(function () {
        showToast("Failed to copy SHA256");
    });
}

function showToast(msg) {
    var container = document.getElementById("toastContainer");
    var toast = document.createElement("div");
    toast.className = "toast show";
    toast.innerHTML = '<div class="toast-body d-flex align-items-center gap-2"><i class="ti ti-check" style="color:var(--tblr-primary)"></i>' + msg + '</div>';
    container.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 2500);
}

function detectPlatform() {
    var ua = navigator.userAgent;
    var platform = null, arch = null;
    if (/Windows/.test(ua)) { platform = "windows"; arch = "installer"; }
    else if (/Mac/.test(ua)) { platform = "macos"; arch = /ARM|aarch64/.test(ua) || navigator.platform === "MacARM" ? "arm" : "intel"; }
    else if (/Linux/.test(ua) && !/Android/.test(ua)) { platform = "linux"; arch = /arm|aarch64/.test(ua) ? "aarch64" : "x86_64"; }
    return { platform: platform, arch: arch };
}

function switchPlatformTab(pkey) {
    var tab = document.querySelector('[data-platform-tab="' + pkey + '"]');
    if (!tab) return;
    document.querySelectorAll('[data-platform-tab]').forEach(function (t) { t.classList.remove("active"); });
    tab.classList.add("active");
    document.querySelectorAll(".tab-pane").forEach(function (p) { p.classList.remove("active", "show"); });
    var pane = document.querySelector(tab.getAttribute("data-target"));
    if (pane) pane.classList.add("active", "show");
    return pane;
}

function selectArch(pane, akey) {
    var btn = pane.querySelector('[data-arch="' + akey + '"]');
    if (!btn) {
        btn = pane.querySelector('[data-arch]');
        if (btn) akey = btn.getAttribute("data-arch");
    }
    if (!btn) return;
    pane.querySelectorAll('[data-arch]').forEach(function (b) { b.classList.remove("active"); });
    btn.classList.add("active");
    pane.querySelectorAll("[data-arch-content]").forEach(function (c) { c.classList.add("d-none"); });
    var content = pane.querySelector('[data-arch-content="' + akey + '"]');
    if (content) content.classList.remove("d-none");
}

document.addEventListener("DOMContentLoaded", function () {
    var detected = detectPlatform();

    document.querySelectorAll('[data-platform-tab]').forEach(function (tab) {
        tab.addEventListener("click", function (e) {
            e.preventDefault();
            switchPlatformTab(this.getAttribute("data-platform-tab"));
        });
    });

    document.querySelectorAll('[data-arch]').forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            var pane = this.closest(".tab-pane");
            selectArch(pane, this.getAttribute("data-arch"));
        });
    });

    if (detected.platform) {
        var pane = switchPlatformTab(detected.platform);
        if (pane) {
            selectArch(pane, detected.arch);
        }
    }
});
