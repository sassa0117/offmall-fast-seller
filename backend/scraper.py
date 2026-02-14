"""
オフモール（ハードオフネットモール）スクレイパー
複数カテゴリの新着商品スキャン + SOLD OUT状態チェック
"""
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Dict

CATEGORIES = {
    "hobby": {
        "name": "ホビー",
        "url": "https://netmall.hardoff.co.jp/cate/040000000000000/",
    },
    "fishing": {
        "name": "釣具",
        "url": "https://netmall.hardoff.co.jp/cate/00010019/",
    },
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def scan_category(category_key: str) -> List[Dict]:
    """指定カテゴリの新着商品を取得"""
    cat = CATEGORIES.get(category_key)
    if not cat:
        print(f"Unknown category: {category_key}")
        return []

    url = cat["url"] + "?s=1"  # s=1: 新着順
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"Scan error ({cat['name']}): {e}")
        return []

    products = _parse_product_list(r.text)
    for p in products:
        p["category"] = category_key
    return products


def scan_hobby_new_arrivals() -> List[Dict]:
    """後方互換: ホビーカテゴリの新着商品を取得"""
    return scan_category("hobby")


def _parse_product_list(html: str) -> List[Dict]:
    """商品一覧ページをパースして商品リストを返す"""
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen_ids = set()

    product_links = soup.find_all("a", href=re.compile(r"/product/\d+/?"))

    for link in product_links:
        href = link.get("href", "")
        match = re.search(r"/product/(\d+)", href)
        if not match:
            continue

        product_id = match.group(1)
        if product_id in seen_ids:
            continue
        seen_ids.add(product_id)

        product_url = f"https://netmall.hardoff.co.jp/product/{product_id}/"

        # 親要素を遡って商品カードコンテナを探す
        container = link
        full_text = ""
        for _ in range(8):
            parent = container.parent
            if parent is None:
                break
            container = parent
            text = container.get_text(separator=" ", strip=True)
            if "円" in text and len(text) > 30:
                full_text = text
                break

        # 価格を抽出
        price = ""
        price_match = re.search(r"([\d,]+)\s*円", full_text)
        if price_match:
            price = price_match.group(1) + "円"

        # 商品名を抽出
        name = ""
        link_text = link.get_text(separator=" ", strip=True)
        link_text_clean = re.sub(r"[\d,]+円|新着|ジャンク|ランク[A-Z]", "", link_text).strip()
        if link_text_clean and len(link_text_clean) > 2:
            name = link_text_clean

        if not name:
            img = link.find("img")
            if img and img.get("alt"):
                name = img.get("alt").strip()

        if not name:
            title = link.get("title", "")
            if title:
                name = title.strip()

        if not name and full_text:
            parts = re.split(r"[\d,]+円|\d+件|新着|ジャンク品?|ランク[A-Z]", full_text)
            parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
            if parts:
                name = max(parts, key=len)[:80]

        if not name:
            name = f"商品ID: {product_id}"

        # 画像URL
        image_url = ""
        img = link.find("img")
        if img:
            image_url = img.get("src", "") or img.get("data-src", "")

        products.append({
            "product_id": product_id,
            "name": name[:200],
            "price": price,
            "url": product_url,
            "image_url": image_url,
        })

    return products


def check_sold_out(product_url: str) -> bool:
    """商品ページにアクセスしてSOLD OUTかどうかチェック"""
    try:
        r = requests.get(product_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        text = r.text.lower()
        return "sold" in text or "売り切れ" in text or "販売終了" in text
    except Exception as e:
        print(f"Check error for {product_url}: {e}")
        return False


def extract_keywords(product_name: str) -> List[str]:
    """商品名からキーワードを抽出"""
    # 不要な文字を除去
    cleaned = re.sub(r"[\[\]【】（）\(\)「」『』]", " ", product_name)
    cleaned = re.sub(r"(ジャンク品?|ランク[A-Z]|中古|未開封|新品|送料無料)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 意味のあるキーワードを抽出（2文字以上の単語）
    keywords = []
    parts = cleaned.split()
    for part in parts:
        part = part.strip()
        if len(part) >= 2 and not re.match(r"^[\d,]+円?$", part):
            keywords.append(part)

    # 最も特徴的なキーワード（最長のもの）を返す
    if keywords:
        keywords.sort(key=len, reverse=True)
        return keywords[:3]
    return []
