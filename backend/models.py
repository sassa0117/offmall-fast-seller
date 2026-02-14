"""
データベースモデル定義 - 即売れチェッカー
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Product(Base):
    """スキャンした商品"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(Text, nullable=False)
    price = Column(String(50), nullable=True)
    url = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    category = Column(String(50), default="hobby")  # "hobby" / "fishing" etc.
    status = Column(String(20), default="active")  # "active" / "sold"
    sold_at = Column(DateTime(timezone=True), nullable=True)
    minutes_to_sell = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Keyword(Base):
    """即売れ商品から抽出されたキーワード"""
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(255), nullable=False)
    exclude = Column(Text, nullable=True)
    selected = Column(Boolean, default=True)
    source_product_name = Column(Text, nullable=True)
    source_price = Column(String(50), nullable=True)
    minutes_to_sell = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
