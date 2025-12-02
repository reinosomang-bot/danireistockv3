import pandas as pd
import numpy as np
import numpy_financial as npf
from datetime import datetime, date
from typing import List, Dict
from models import PortfolioSummary, Holding, Transaction

def parse_csv(file_path: str) -> pd.DataFrame:
    """
    Parses the CSV file and returns a cleaned DataFrame.
    """
    # Try reading with different separators
    try:
        df = pd.read_csv(file_path, sep=None, engine='python')
    except:
        try:
            df = pd.read_csv(file_path, sep=';')
        except:
            df = pd.read_csv(file_path, sep=',')
    
    # Normalize column names
    df.columns = [c.strip() for c in df.columns]
    
    # Parse dates (assuming DD/MM/YYYY format from the user's image)
    df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y').dt.date
    
    # Ensure numeric columns are floats
    numeric_cols = ['Cantidad', 'EURO_DIVISA_BCE', 'Precio_Operacion', 'Precio_Compra_EUR', 'Cotizacion']
    for col in numeric_cols:
        if col in df.columns:
            # Handle potential comma decimals if present in raw data (though sample used dots)
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '.').astype(float)
    
    return df

def calculate_portfolio(df: pd.DataFrame) -> PortfolioSummary:
    """
    Calculates portfolio metrics from the transaction DataFrame.
    """
    holdings: Dict[str, Holding] = {}
    transactions: List[Transaction] = []
    
    # Sort by date to process chronologically
    df = df.sort_values('Fecha')
    
    total_invested_eur = 0.0
    total_realized_pl_eur = 0.0
    cash_flows = [] # For IRR calculation: (date, amount)
    
    # Track inventory for FIFO/Weighted Average
    # Using Weighted Average for simplicity in this version as per common dashboard standards,
    # but we can switch to FIFO if needed. Let's stick to Weighted Average Cost (WAC) for now.
    portfolio_state = {} # symbol -> {quantity, total_cost_eur}

    for _, row in df.iterrows():
        symbol = row['Simbolo']
        op_type = row['Operacion'].lower() # Compra/Venta
        qty = row['Cantidad']
        price_eur = row['Precio_Compra_EUR'] # Using the EUR converted price
        date_obj = row['Fecha']
        
        # Cash flow for IRR
        # Outflow (Buy) is negative, Inflow (Sell) is positive
        amount_eur = qty * price_eur
        
        if 'compra' in op_type:
            cash_flows.append((date_obj, -amount_eur))
            
            if symbol not in portfolio_state:
                portfolio_state[symbol] = {'quantity': 0.0, 'total_cost_eur': 0.0}
            
            portfolio_state[symbol]['quantity'] += qty
            portfolio_state[symbol]['total_cost_eur'] += amount_eur
            
        elif 'venta' in op_type:
            cash_flows.append((date_obj, amount_eur))
            
            if symbol in portfolio_state:
                # Calculate Realized P&L based on Average Cost
                avg_cost = portfolio_state[symbol]['total_cost_eur'] / portfolio_state[symbol]['quantity']
                cost_basis_sold = qty * avg_cost
                realized_pl = amount_eur - cost_basis_sold
                
                total_realized_pl_eur += realized_pl
                
                portfolio_state[symbol]['quantity'] -= qty
                portfolio_state[symbol]['total_cost_eur'] -= cost_basis_sold
                
                # Cleanup if closed
                if portfolio_state[symbol]['quantity'] <= 1e-9:
                     portfolio_state[symbol]['quantity'] = 0
                     portfolio_state[symbol]['total_cost_eur'] = 0

    # Generate Holdings List
    final_holdings = []
    total_value_eur = 0.0
    total_unrealized_pl_eur = 0.0
    
    # Get latest prices from the dataframe (assuming 'Cotizacion' is current price)
    # In a real app, we'd fetch live prices here.
    latest_prices = df.sort_values('Fecha').groupby('Simbolo')['Cotizacion'].last().to_dict()
    
    # We also need the exchange rate to convert the latest price to EUR if it's in USD
    # For simplicity, let's assume the latest transaction's exchange rate or 1.0 if EUR
    # A better approach is to have a separate price/fx fetcher.
    # Let's use the last available exchange rate for that symbol.
    latest_fx = df.sort_values('Fecha').groupby('Simbolo')['EURO_DIVISA_BCE'].last().to_dict()

    for symbol, state in portfolio_state.items():
        qty = state['quantity']
        if qty > 0:
            avg_cost = state['total_cost_eur'] / qty
            
            # Current Price Logic
            current_price_raw = latest_prices.get(symbol, 0.0)
            fx_rate = latest_fx.get(symbol, 1.0)
            
            # Check currency from last transaction
            last_txn = df[df['Simbolo'] == symbol].iloc[-1]
            currency = last_txn['Divisa']
            
            # If price is in USD, convert to EUR for value calculation
            # Note: The CSV has 'Cotizacion' which seems to be in original currency
            current_price_eur = current_price_raw * fx_rate if currency != 'EUR' else current_price_raw
            
            market_value = qty * current_price_eur
            unrealized_pl = market_value - state['total_cost_eur']
            unrealized_pl_pct = (unrealized_pl / state['total_cost_eur']) * 100 if state['total_cost_eur'] != 0 else 0
            
            h = Holding(
                symbol=symbol,
                quantity=qty,
                average_price=avg_cost,
                current_price=current_price_raw, # Display in original currency
                market_value=market_value,
                unrealized_pl=unrealized_pl,
                unrealized_pl_percentage=unrealized_pl_pct,
                realized_pl=0.0, # Per holding realized P&L is tricky to track in this simple view, keeping 0 for now or we can aggregate from transactions
                currency=currency
            )
            final_holdings.append(h)
            
            total_value_eur += market_value
            total_unrealized_pl_eur += unrealized_pl
            total_invested_eur += state['total_cost_eur']
            
            # Add current value as a "cash flow" for IRR calculation (as if we sold everything today)
            cash_flows.append((date.today(), market_value))

    # Calculate IRR (XIRR)
    irr = 0.0
    if cash_flows:
        # npf.xirr expects dates and values. 
        # We need to filter out today's date if it duplicates a transaction date? No, XIRR handles it.
        # However, we summed up all current market values. We should add them as one big positive flow at the end?
        # Actually, we added them per holding loop. Let's correct that.
        # We should add the TOTAL portfolio value as a positive cash flow at the end date.
        
        # Reset cash flows to just transactions first
        irr_flows = []
        for _, row in df.iterrows():
            op_type = row['Operacion'].lower()
            amount_eur = row['Cantidad'] * row['Precio_Compra_EUR']
            d = row['Fecha']
            if 'compra' in op_type:
                irr_flows.append((d, -amount_eur))
            elif 'venta' in op_type:
                irr_flows.append((d, amount_eur))
        
        # Add final value
        if total_value_eur > 0:
            irr_flows.append((date.today(), total_value_eur))
            
        try:
            dates = [f[0] for f in irr_flows]
            amounts = [f[1] for f in irr_flows]
            irr = npf.xirr(amounts, dates)
        except:
            irr = 0.0

    # ... (previous code)
    
    # Track ignored operations for debugging
    ignored_ops = {}
    
    for _, row in df.iterrows():
        # Handle potential NaN in Operacion
        if pd.isna(row['Operacion']):
            continue
            
        op_type = str(row['Operacion']).lower()
        # ... (existing logic)
        
        if 'compra' in op_type:
            # ... (existing buy logic)
            pass
        elif 'venta' in op_type:
            # ... (existing sell logic)
            pass
        else:
            if op_type not in ignored_ops:
                ignored_ops[op_type] = 0
            ignored_ops[op_type] += 1

    # ... (rest of calculation)

    return PortfolioSummary(
        total_value_eur=total_value_eur,
        total_invested_eur=total_invested_eur,
        total_unrealized_pl_eur=total_unrealized_pl_eur,
        total_realized_pl_eur=total_realized_pl_eur,
        irr=irr if not np.isnan(irr) else 0.0,
        holdings=final_holdings,
        debug_info={"ignored_operations": ignored_ops, "total_rows": len(df)}
    )
