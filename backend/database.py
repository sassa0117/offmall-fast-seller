"""
データベース接続設定 - SQLite
"""
import os
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fast_seller.db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """データベースの初期化（テーブル作成 + マイグレーション）"""
    Base.metadata.create_all(bind=engine)
    # categoryカラムが無い既存DBへのマイグレーション
    insp = inspect(engine)
    if "products" in insp.get_table_names():
        columns = [c["name"] for c in insp.get_columns("products")]
        if "category" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE products ADD COLUMN category VARCHAR(50) DEFAULT 'hobby'"))
            print("Migration: added category column")
    print("Database initialized")


def get_db():
    """データベースセッションを取得"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
