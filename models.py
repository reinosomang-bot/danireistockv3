from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class Transaction(BaseModel):
    symbol: str
    date: date
    type: str  # Compra/Venta
    quantity: float
    price: float
    currency: str
    exchange_rate: float
    fees: float = 0.0

class Holding(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_percentage: float
    realized_pl: float
    currency: str

class PortfolioSummary(BaseModel):
    total_value_eur: float
    total_invested_eur: float
    total_unrealized_pl_eur: float
    total_realized_pl_eur: float
    irr: float
    holdings: List[Holding]
