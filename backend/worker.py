"""
バックグラウンドワーカー
- スキャン: 新着商品をDBに保存（SCAN_INTERVAL秒ごと）
- チェック: 既存商品のSOLD OUT状態を確認（CHECK_INTERVAL秒ごと）
"""
import os
import time
import threading
from datetime import datetime
from database import SessionLocal
from models import Product, Keyword
from scraper import scan_category, check_sold_out, extract_keywords, CATEGORIES

SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "600"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
SELL_CHECK_MINUTES = int(os.getenv("SELL_CHECK_MINUTES", "30"))


def run_scan():
    """全カテゴリの新着商品をスキャンしてDBに保存"""
    db = SessionLocal()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_scanned = 0
        total_new = 0

        for cat_key, cat_info in CATEGORIES.items():
            print(f"[{now}] スキャン開始: {cat_info['name']}")
            products = scan_category(cat_key)
            new_count = 0

            for p in products:
                existing = db.query(Product).filter(
                    Product.product_id == p["product_id"]
                ).first()
                if not existing:
                    product = Product(
                        product_id=p["product_id"],
                        name=p["name"],
                        price=p["price"],
                        url=p["url"],
                        image_url=p.get("image_url", ""),
                        category=cat_key,
                        status="active",
                    )
                    db.add(product)
                    new_count += 1

            print(f"[{now}] {cat_info['name']}: {len(products)}件取得, {new_count}件新規")
            total_scanned += len(products)
            total_new += new_count
            time.sleep(2)  # カテゴリ間の間隔

        db.commit()
        print(f"[{now}] 全スキャン完了: {total_scanned}件取得, {total_new}件新規")
        return {"scanned": total_scanned, "new": total_new}

    except Exception as e:
        print(f"スキャンエラー: {e}")
        db.rollback()
        return {"scanned": 0, "new": 0}
    finally:
        db.close()


def run_check():
    """active状態の商品のSOLD OUTチェック"""
    db = SessionLocal()
    try:
        now = datetime.now()
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] チェック開始...")

        active_products = db.query(Product).filter(
            Product.status == "active"
        ).all()

        sold_count = 0
        for product in active_products:
            is_sold = check_sold_out(product.url)
            if is_sold:
                product.status = "sold"
                product.sold_at = now
                # 出品から売り切れまでの分数を計算
                if product.created_at:
                    delta = now - product.created_at.replace(tzinfo=None)
                    product.minutes_to_sell = int(delta.total_seconds() / 60)
                else:
                    product.minutes_to_sell = 0

                # 即売れ判定（SELL_CHECK_MINUTES以内に売れた場合）
                if product.minutes_to_sell and product.minutes_to_sell <= SELL_CHECK_MINUTES:
                    _extract_and_save_keyword(db, product)

                sold_count += 1
            time.sleep(1)  # サーバーに負荷をかけない

        db.commit()
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] チェック完了: {len(active_products)}件中 {sold_count}件SOLD OUT")
        return {"checked": len(active_products), "sold": sold_count}

    except Exception as e:
        print(f"チェックエラー: {e}")
        db.rollback()
        return {"checked": 0, "sold": 0}
    finally:
        db.close()


def _extract_and_save_keyword(db, product: Product):
    """即売れ商品からキーワードを抽出してDBに保存"""
    keywords = extract_keywords(product.name)
    if not keywords:
        return

    # 最も特徴的なキーワード（最長）を保存
    main_keyword = keywords[0]

    # 既に同じキーワードがあればスキップ
    existing = db.query(Keyword).filter(
        Keyword.keyword == main_keyword
    ).first()
    if existing:
        return

    kw = Keyword(
        keyword=main_keyword,
        selected=True,
        source_product_name=product.name,
        source_price=product.price,
        minutes_to_sell=product.minutes_to_sell,
    )
    db.add(kw)


def start_scan_worker():
    """スキャンワーカーをバックグラウンドスレッドで開始"""
    def loop():
        print(f"スキャンワーカー開始: {SCAN_INTERVAL}秒間隔")
        while True:
            try:
                run_scan()
            except Exception as e:
                print(f"スキャンワーカーエラー: {e}")
            time.sleep(SCAN_INTERVAL)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def start_check_worker():
    """チェックワーカーをバックグラウンドスレッドで開始"""
    def loop():
        print(f"チェックワーカー開始: {CHECK_INTERVAL}秒間隔")
        # 初回は少し待つ（スキャンが先に走るように）
        time.sleep(30)
        while True:
            try:
                run_check()
            except Exception as e:
                print(f"チェックワーカーエラー: {e}")
            time.sleep(CHECK_INTERVAL)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
