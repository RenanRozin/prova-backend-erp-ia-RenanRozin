"""Reexporta os modelos para que o `Base.metadata` esteja completo quando o
Alembic fizer autogenerate. Sem isto, tabela importada em lugar nenhum some da
migração — e o erro só aparece no deploy."""

from app.models.product import Product
from app.models.stock_alert import StockAlert
from app.models.user import User

__all__ = ["Product", "StockAlert", "User"]
