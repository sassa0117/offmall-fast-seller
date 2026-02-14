"""
オフモール即売れ分析 - FastAPI メインアプリケーション
"""
import os
import io
import csv
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc

from database import init_db, get_db
from models import Product, Keyword
from worker import start_scan_worker, start_check_worker, run_scan, run_check
from scraper import CATEGORIES

app = FastAPI(
    title="オフモール即売れ分析",
    description="複数カテゴリの即売れ商品を分析・キーワード抽出",
    version="2.0.0",
)

# 静的ファイル配信
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ========== Pydanticモデル ==========

class IncomingProduct(BaseModel):
    id: str
    name: str
    price: str = ""
    url: str
    image_url: str = ""


class KeywordCreate(BaseModel):
    keyword: str
    exclude: str = ""


class KeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    exclude: Optional[str] = None
    selected: Optional[bool] = None


# ========== 起動時処理 ==========

@app.on_event("startup")
def startup():
    init_db()
    start_scan_worker()
    start_check_worker()


# ========== API エンドポイント ==========

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    today_scanned = db.query(sqlfunc.count(Product.id)).filter(
        Product.created_at >= today
    ).scalar() or 0

    today_sold = db.query(sqlfunc.count(Product.id)).filter(
        Product.status == "sold",
        Product.sold_at >= today,
        Product.minutes_to_sell != None,
    ).scalar() or 0

    week_sold = db.query(sqlfunc.count(Product.id)).filter(
        Product.status == "sold",
        Product.sold_at >= week_ago,
        Product.minutes_to_sell != None,
    ).scalar() or 0

    pending = db.query(sqlfunc.count(Product.id)).filter(
        Product.status == "active"
    ).scalar() or 0

    keyword_count = db.query(sqlfunc.count(Keyword.id)).scalar() or 0

    selected_count = db.query(sqlfunc.count(Keyword.id)).filter(
        Keyword.selected == True
    ).scalar() or 0

    return {
        "today_scanned": today_scanned,
        "today_sold": today_sold,
        "week_sold": week_sold,
        "pending": pending,
        "keyword_count": keyword_count,
        "selected_count": selected_count,
    }


@app.get("/api/keywords")
def get_keywords(db: Session = Depends(get_db)):
    """キーワード一覧"""
    keywords = db.query(Keyword).order_by(Keyword.id.desc()).all()
    return [
        {
            "id": k.id,
            "keyword": k.keyword,
            "exclude": k.exclude or "",
            "selected": k.selected,
            "source_product_name": k.source_product_name or "手動追加",
            "source_price": k.source_price or "",
            "minutes_to_sell": k.minutes_to_sell,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keywords
    ]


@app.post("/api/keywords")
def add_keyword(data: KeywordCreate, db: Session = Depends(get_db)):
    """手動キーワード追加"""
    kw = Keyword(
        keyword=data.keyword,
        exclude=data.exclude or "",
        selected=True,
        source_product_name="手動追加",
    )
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return {"id": kw.id, "status": "ok"}


@app.put("/api/keywords/{keyword_id}")
def update_keyword(keyword_id: int, data: KeywordUpdate, db: Session = Depends(get_db)):
    """キーワード更新"""
    kw = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not kw:
        return {"error": "not found"}

    if data.keyword is not None:
        kw.keyword = data.keyword
    if data.exclude is not None:
        kw.exclude = data.exclude
    if data.selected is not None:
        kw.selected = data.selected

    db.commit()
    return {"status": "ok"}


@app.delete("/api/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """キーワード削除"""
    kw = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not kw:
        return {"error": "not found"}

    db.delete(kw)
    db.commit()
    return {"status": "ok"}


@app.post("/api/keywords/select-all")
def select_all_keywords(selected: bool = True, db: Session = Depends(get_db)):
    """全選択/全解除"""
    db.query(Keyword).update({Keyword.selected: selected})
    db.commit()
    return {"status": "ok"}


@app.get("/api/keywords/export")
def export_keywords(db: Session = Depends(get_db)):
    """選択済みキーワードをCSVエクスポート（監視ツール互換）"""
    keywords = db.query(Keyword).filter(Keyword.selected == True).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["keyword", "exclude"])
    for kw in keywords:
        writer.writerow([kw.keyword, kw.exclude or ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=keywords.csv"},
    )


@app.post("/api/incoming-products")
def receive_products(products: List[IncomingProduct], db: Session = Depends(get_db)):
    """新着通知ツールから商品リストを受信してDBに保存"""
    new_count = 0
    for p in products:
        existing = db.query(Product).filter(Product.product_id == p.id).first()
        if not existing:
            product = Product(
                product_id=p.id,
                name=p.name,
                price=p.price,
                url=p.url,
                image_url=p.image_url,
                status="active",
            )
            db.add(product)
            new_count += 1

    db.commit()
    return {"received": len(products), "new": new_count}


@app.get("/api/fast-sellers")
def get_fast_sellers(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """即売れ商品一覧"""
    since = datetime.now() - timedelta(days=days)

    sellers = db.query(Product).filter(
        Product.status == "sold",
        Product.minutes_to_sell != None,
        Product.sold_at >= since,
    ).order_by(Product.minutes_to_sell.asc()).limit(limit).all()

    return [
        {
            "id": s.id,
            "product_id": s.product_id,
            "name": s.name,
            "price": s.price or "",
            "url": s.url,
            "image_url": s.image_url or "",
            "category": s.category or "hobby",
            "category_name": CATEGORIES.get(s.category or "hobby", {}).get("name", "不明"),
            "minutes_to_sell": s.minutes_to_sell,
            "sold_at": s.sold_at.isoformat() if s.sold_at else None,
        }
        for s in sellers
    ]


@app.get("/api/categories")
def get_categories():
    """監視中のカテゴリ一覧"""
    return [{"key": k, "name": v["name"]} for k, v in CATEGORIES.items()]


@app.post("/api/scan")
def manual_scan():
    """手動スキャン"""
    result = run_scan()
    return result


@app.post("/api/check")
def manual_check():
    """手動チェック"""
    result = run_check()
    return result


@app.get("/sw.js")
def service_worker():
    """Service Workerをルートスコープで配信"""
    sw_path = os.path.join(FRONTEND_DIR, "sw.js")
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.json")
def manifest():
    """manifestをルートから配信"""
    manifest_path = os.path.join(FRONTEND_DIR, "manifest.json")
    return FileResponse(manifest_path, media_type="application/manifest+json")


@app.get("/", response_class=HTMLResponse)
def index():
    """index.html配信"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()
