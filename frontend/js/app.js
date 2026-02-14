/**
 * 即売れキーワード整理ツール - フロントエンド
 */

let currentDays = 7;
let keywords = [];

// ========== タブ切り替え ==========

function switchTab(tab) {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    if (tab === "keywords") {
        document.getElementById("keywordsTab").style.display = "";
        document.getElementById("sellersTab").style.display = "none";
        document.querySelectorAll(".tab")[0].classList.add("active");
    } else {
        document.getElementById("keywordsTab").style.display = "none";
        document.getElementById("sellersTab").style.display = "";
        document.querySelectorAll(".tab")[1].classList.add("active");
        loadFastSellers();
    }
}

// ========== 統計 ==========

async function loadStats() {
    try {
        const r = await fetch("/api/stats");
        const data = await r.json();
        document.getElementById("todayScanned").textContent = data.today_scanned;
        document.getElementById("todaySold").textContent = data.today_sold;
        document.getElementById("weekSold").textContent = data.week_sold;
        document.getElementById("pending").textContent = data.pending;
        document.getElementById("keywordCount").textContent = data.keyword_count;
        document.getElementById("selectedCount").textContent = data.selected_count;
    } catch (e) {
        console.error("Stats error:", e);
    }
}

// ========== キーワード一覧 ==========

async function loadKeywords() {
    const container = document.getElementById("keywordList");
    try {
        const r = await fetch("/api/keywords");
        keywords = await r.json();

        if (keywords.length === 0) {
            container.innerHTML = '<div class="empty-state">まだキーワードがありません。即売れ商品が見つかると自動抽出されます。</div>';
            return;
        }

        container.innerHTML = keywords.map(k => `
            <div class="kw-row" id="kw-${k.id}">
                <label class="kw-checkbox">
                    <input type="checkbox" ${k.selected ? "checked" : ""}
                           onchange="toggleKeyword(${k.id}, this.checked)">
                </label>
                <div class="kw-main">
                    <div class="kw-keyword" id="kw-text-${k.id}">${escapeHtml(k.keyword)}</div>
                    ${k.exclude ? `<div class="kw-exclude">除外: ${escapeHtml(k.exclude)}</div>` : ""}
                    <div class="kw-source">
                        ${k.source_product_name !== "手動追加" ? `
                            <span class="kw-time">${k.minutes_to_sell}分売れ</span>
                            <span class="kw-price">${escapeHtml(k.source_price || "")}</span>
                            <span class="kw-name">${escapeHtml((k.source_product_name || "").substring(0, 40))}</span>
                        ` : `<span class="kw-manual">手動追加</span>`}
                    </div>
                </div>
                <div class="kw-actions">
                    <button class="btn-icon" onclick="editKeyword(${k.id})" title="編集">&#9998;</button>
                    <button class="btn-icon btn-icon-danger" onclick="deleteKeyword(${k.id})" title="削除">&times;</button>
                </div>
            </div>
        `).join("");
    } catch (e) {
        container.innerHTML = '<div class="empty-state">読み込みエラー</div>';
        console.error("Keywords error:", e);
    }
}

// ========== キーワード操作 ==========

async function toggleKeyword(id, selected) {
    try {
        await fetch(`/api/keywords/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ selected }),
        });
        loadStats();
    } catch (e) {
        console.error("Toggle error:", e);
    }
}

async function selectAll(selected) {
    try {
        await fetch(`/api/keywords/select-all?selected=${selected}`, { method: "POST" });
        loadKeywords();
        loadStats();
    } catch (e) {
        console.error("Select all error:", e);
    }
}

function editKeyword(id) {
    const kw = keywords.find(k => k.id === id);
    if (!kw) return;

    const row = document.getElementById(`kw-${id}`);
    const mainDiv = row.querySelector(".kw-main");

    mainDiv.innerHTML = `
        <div class="edit-form">
            <input type="text" id="edit-kw-${id}" value="${escapeHtml(kw.keyword)}" class="input input-sm" placeholder="キーワード">
            <input type="text" id="edit-ex-${id}" value="${escapeHtml(kw.exclude || "")}" class="input input-sm" placeholder="除外ワード">
            <div class="edit-actions">
                <button class="btn btn-primary btn-small" onclick="saveKeyword(${id})">保存</button>
                <button class="btn btn-small" style="background:#888;color:#fff" onclick="loadKeywords()">キャンセル</button>
            </div>
        </div>
    `;
    document.getElementById(`edit-kw-${id}`).focus();
}

async function saveKeyword(id) {
    const keyword = document.getElementById(`edit-kw-${id}`).value.trim();
    const exclude = document.getElementById(`edit-ex-${id}`).value.trim();

    if (!keyword) return;

    try {
        await fetch(`/api/keywords/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ keyword, exclude }),
        });
        loadKeywords();
    } catch (e) {
        console.error("Save error:", e);
    }
}

async function deleteKeyword(id) {
    if (!confirm("このキーワードを削除しますか？")) return;
    try {
        await fetch(`/api/keywords/${id}`, { method: "DELETE" });
        loadKeywords();
        loadStats();
    } catch (e) {
        console.error("Delete error:", e);
    }
}

async function addKeyword() {
    const keyword = document.getElementById("addKeyword").value.trim();
    const exclude = document.getElementById("addExclude").value.trim();
    if (!keyword) return;

    try {
        await fetch("/api/keywords", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ keyword, exclude }),
        });
        document.getElementById("addKeyword").value = "";
        document.getElementById("addExclude").value = "";
        loadKeywords();
        loadStats();
    } catch (e) {
        console.error("Add error:", e);
    }
}

function exportCSV() {
    window.location.href = "/api/keywords/export";
}

// ========== 即売れ商品 ==========

async function loadFastSellers() {
    const container = document.getElementById("fastSellerList");
    container.innerHTML = '<div class="loading">読み込み中...</div>';

    try {
        const r = await fetch(`/api/fast-sellers?days=${currentDays}&limit=100`);
        const items = await r.json();

        if (items.length === 0) {
            container.innerHTML = '<div class="empty-state">まだ即売れ商品がありません。データ収集中...</div>';
            return;
        }

        container.innerHTML = items.map(item => `
            <div class="product-card">
                <a href="${item.url}" target="_blank" rel="noopener">
                    ${item.image_url ? `<img class="product-card-img" src="${item.image_url}" alt="" loading="lazy" onerror="this.style.display='none'">` : ""}
                    <div class="product-card-body">
                        <div class="product-card-name">${escapeHtml(item.name)}</div>
                        <div class="product-card-price">${escapeHtml(item.price || "価格不明")}</div>
                        <div class="product-card-meta">
                            <span class="category-badge category-${item.category || 'hobby'}">${escapeHtml(item.category_name || 'ホビー')}</span>
                            <span class="product-card-time">${item.minutes_to_sell}分で売り切れ</span>
                        </div>
                    </div>
                </a>
            </div>
        `).join("");

    } catch (e) {
        container.innerHTML = '<div class="empty-state">読み込みエラー</div>';
        console.error("FastSellers error:", e);
    }
}

function changeDays(days) {
    currentDays = days;
    loadFastSellers();
}

// ========== 手動スキャン/チェック ==========

async function runScan() {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = "スキャン中...";

    try {
        await fetch("/api/scan", { method: "POST" });
        loadStats();
    } catch (e) {
        console.error("Scan error:", e);
    } finally {
        btn.disabled = false;
        btn.textContent = "手動スキャン";
    }
}

async function runCheck() {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = "チェック中...";

    try {
        await fetch("/api/check", { method: "POST" });
        loadStats();
        loadKeywords();
    } catch (e) {
        console.error("Check error:", e);
    } finally {
        btn.disabled = false;
        btn.textContent = "手動チェック";
    }
}

// ========== ユーティリティ ==========

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ========== 初期化 ==========

document.addEventListener("DOMContentLoaded", () => {
    loadStats();
    loadKeywords();

    // 1分ごとに自動更新
    setInterval(() => {
        loadStats();
        loadKeywords();
    }, 60000);
});
