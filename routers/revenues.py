import os
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, field_validator, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import asyncpg
from decimal import Decimal
from enum import Enum
import json
import csv
import io
from typing import List, Optional, Dict, Any, Union

# Import authentication from your existing system
from routers.employees import admin_or_manager, TokenData

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# Initialize router
router = APIRouter(prefix="/revenues", tags=["Revenues"])

# Enums and Models
class PeriodType(str, Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"
    custom = "custom"

class RevenueRequest(BaseModel):
    period_type: PeriodType
    year: Optional[int] = None
    month: Optional[int] = None
    quarter: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator('month')
    def validate_month(cls, v):
        # Convert 0 to None (not provided)
        if v == 0:
            return None
        if v is not None and (v < 1 or v > 12):
            raise ValueError('Month must be between 1 and 12')
        return v

    @field_validator('quarter')
    def validate_quarter(cls, v):
        # Convert 0 to None (not provided)
        if v == 0:
            return None
        if v is not None and (v < 1 or v > 4):
            raise ValueError('Quarter must be between 1 and 4')
        return v

    @field_validator('year')
    def validate_year(cls, v):
        # Convert 0 to None (not provided)
        if v == 0:
            return None
        return v

class InvoiceData(BaseModel):
    id: int
    client_name: str
    job_order_id: int
    invoice_date: date
    invoice_number: str
    subtotal: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    outstanding_balance: Decimal
    product: Optional[str] = None
    model: Optional[str] = None
    unit_price: Optional[Decimal] = None
    order_quantity: Optional[int] = None

class CostData(BaseModel):
    title: str
    cost: Decimal
    currency: str

class RevenueReport(BaseModel):
    id: Optional[int] = None
    report_name: str
    period_info: Dict[str, Any]
    total_revenue: Decimal
    invoices: List[InvoiceData]
    costs: Dict[str, List[CostData]]
    profit: Decimal
    net_profit: Decimal
    summary: Dict[str, Decimal]
    generated_at: Optional[datetime] = None

class ProductRevenueData(BaseModel):
    product: str
    model: str
    total_revenue: Decimal
    total_invoices: int
    total_quantity: int
    average_unit_price: Decimal
    clients: List[str]
    invoices: List[InvoiceData]

class ProductRevenueReport(BaseModel):
    period_info: Dict[str, Any]
    products: List[ProductRevenueData]
    total_costs: Dict[str, Decimal]
    total_revenue: Decimal
    profit: Decimal
    net_profit: Decimal

class CustomerRevenueData(BaseModel):
    client_name: str
    total_revenue: Decimal
    total_invoices: int
    total_orders: int
    outstanding_balance: Decimal
    products: List[str]
    invoices: List[InvoiceData]

class CustomerRevenueReport(BaseModel):
    period_info: Dict[str, Any]
    customers: List[CustomerRevenueData]
    total_costs: Dict[str, Decimal]
    total_revenue: Decimal
    profit: Decimal
    net_profit: Decimal

# Helper Functions
def get_date_range(period_type: PeriodType, year: int = None, month: int = None, 
                   quarter: int = None, start_date: date = None, end_date: date = None) -> tuple:
    """Get start and end dates based on period type"""
    
    current_date = datetime.now().date()
    
    if period_type == PeriodType.monthly:
        current_year = year if year else current_date.year
        current_month = month if month else current_date.month
        
        start = date(current_year, current_month, 1)
        if current_month == 12:
            end = date(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(current_year, current_month + 1, 1) - timedelta(days=1)
    
    elif period_type == PeriodType.quarterly:
        current_year = year if year else current_date.year
        current_quarter = quarter if quarter else ((current_date.month - 1) // 3) + 1
        
        quarter_months = {
            1: (1, 3),
            2: (4, 6),
            3: (7, 9),
            4: (10, 12)
        }
        start_month, end_month = quarter_months[current_quarter]
        start = date(current_year, start_month, 1)
        if end_month == 12:
            end = date(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(current_year, end_month + 1, 1) - timedelta(days=1)
    
    elif period_type == PeriodType.yearly:
        current_year = year if year else current_date.year
        start = date(current_year, 1, 1)
        end = date(current_year, 12, 31)
    
    elif period_type == PeriodType.custom:
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="Start date and end date are required for custom period")
        start = start_date
        end = end_date
    
    return start, end

async def fetch_invoices_with_orders(conn, start_date: date, end_date: date) -> List[Dict]:
    """Fetch invoices with job order details for the specified period"""
    
    query = """
    SELECT 
        i.id,
        i.client_name,
        i.job_order_id,
        i.invoice_date,
        i.invoice_number,
        i.subtotal,
        i.total_amount,
        i.amount_paid,
        i.outstanding_balance,
        jo.product,
        jo.model,
        jo.unit_price,
        jo.order_quantity
    FROM invoices i
    LEFT JOIN job_orders jo ON i.job_order_id = jo.id
    WHERE i.invoice_date >= $1 AND i.invoice_date <= $2
    ORDER BY i.invoice_date DESC
    """
    
    rows = await conn.fetch(query, start_date, end_date)
    return [dict(row) for row in rows]

async def fetch_costs_by_period(conn, table_name: str, start_date: date, end_date: date) -> List[Dict]:
    """Fetch costs from specified table for the given period"""
    
    query = f"""
    SELECT title, cost, currency
    FROM {table_name}
    WHERE submission_date >= $1 AND submission_date <= $2
    """
    
    rows = await conn.fetch(query, start_date, end_date)
    return [dict(row) for row in rows]

class SavedRevenueReport(BaseModel):
    id: int
    report_name: str
    period_type: str
    period_start_date: date
    period_end_date: date
    total_revenue: Decimal
    profit: Decimal
    net_profit: Decimal
    profit_margin: Decimal
    net_profit_margin: Decimal
    generated_at: datetime
    status: str

async def fetch_revenue_by_product(conn, start_date: date, end_date: date) -> List[Dict]:
    """Fetch revenue data grouped by product type"""
    
    query = """
    SELECT 
        jo.product,
        jo.model,
        COUNT(DISTINCT i.id) as total_invoices,
        SUM(i.amount_paid) as total_revenue,
        SUM(jo.order_quantity) as total_quantity,
        AVG(jo.unit_price) as average_unit_price,
        ARRAY_AGG(DISTINCT i.client_name) as clients,
        JSON_AGG(
            JSON_BUILD_OBJECT(
                'id', i.id,
                'client_name', i.client_name,
                'job_order_id', i.job_order_id,
                'invoice_date', i.invoice_date,
                'invoice_number', i.invoice_number,
                'subtotal', i.subtotal,
                'total_amount', i.total_amount,
                'amount_paid', i.amount_paid,
                'outstanding_balance', i.outstanding_balance,
                'product', jo.product,
                'model', jo.model,
                'unit_price', jo.unit_price,
                'order_quantity', jo.order_quantity
            )
        ) as invoices
    FROM invoices i
    INNER JOIN job_orders jo ON i.job_order_id = jo.id
    WHERE i.invoice_date >= $1 AND i.invoice_date <= $2
    GROUP BY jo.product, jo.model
    ORDER BY total_revenue DESC
    """
    
    rows = await conn.fetch(query, start_date, end_date)
    return [dict(row) for row in rows]

async def fetch_revenue_by_customer(conn, start_date: date, end_date: date) -> List[Dict]:
    """Fetch revenue data grouped by customer (case insensitive)"""
    
    query = """
    SELECT 
        TRIM(UPPER(i.client_name)) as normalized_client_name,
        STRING_AGG(DISTINCT i.client_name, ', ') as client_name_variants,
        COUNT(DISTINCT i.id) as total_invoices,
        COUNT(DISTINCT i.job_order_id) as total_orders,
        SUM(i.amount_paid) as total_revenue,
        SUM(i.outstanding_balance) as outstanding_balance,
        ARRAY_AGG(DISTINCT CONCAT(jo.product, ' - ', jo.model)) as products,
        JSON_AGG(
            JSON_BUILD_OBJECT(
                'id', i.id,
                'client_name', i.client_name,
                'job_order_id', i.job_order_id,
                'invoice_date', i.invoice_date,
                'invoice_number', i.invoice_number,
                'subtotal', i.subtotal,
                'total_amount', i.total_amount,
                'amount_paid', i.amount_paid,
                'outstanding_balance', i.outstanding_balance,
                'product', jo.product,
                'model', jo.model,
                'unit_price', jo.unit_price,
                'order_quantity', jo.order_quantity
            )
        ) as invoices
    FROM invoices i
    INNER JOIN job_orders jo ON i.job_order_id = jo.id
    WHERE i.invoice_date >= $1 AND i.invoice_date <= $2
    GROUP BY TRIM(UPPER(i.client_name))
    ORDER BY total_revenue DESC
    """
    
    rows = await conn.fetch(query, start_date, end_date)
    return [dict(row) for row in rows]
    """Save revenue report to database and return report ID"""
    
    # Insert main revenue record
    revenue_query = """
    INSERT INTO revenues (
        report_name, period_type, period_start_date, period_end_date,
        year, month, quarter, total_revenue, total_invoices,
        raw_materials_costs, operational_costs, general_costs,
        depreciation_costs, unexpected_costs, total_costs,
        profit, net_profit, profit_margin, net_profit_margin
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
    RETURNING id
    """
    
    period_info = report_data['period_info']
    summary = report_data['summary']
    
    # Calculate margins
    profit_margin = (summary['profit'] / summary['total_revenue'] * 100) if summary['total_revenue'] > 0 else 0
    net_profit_margin = (summary['net_profit'] / summary['total_revenue'] * 100) if summary['total_revenue'] > 0 else 0
    
    revenue_id = await conn.fetchval(
        revenue_query,
        report_data['report_name'],
        period_info['period_type'],
        start_date,  # Use actual date object
        end_date,    # Use actual date object
        period_info.get('year'),
        period_info.get('month'),
        period_info.get('quarter'),
        summary['total_revenue'],
        len(report_data['invoices']),
        summary['total_raw_materials_costs'],
        summary['total_operational_costs'],
        summary['total_general_costs'],
        summary['total_depreciation_costs'],
        summary['total_unexpected_costs'],
        summary['total_raw_materials_costs'] + summary['total_operational_costs'] + 
        summary['total_general_costs'] + summary['total_depreciation_costs'] + summary['total_unexpected_costs'],
        summary['profit'],
        summary['net_profit'],
        profit_margin,
        net_profit_margin
    )
    
    # Insert revenue details
    if report_data['invoices']:
        detail_values = []
        for invoice in report_data['invoices']:
            detail_values.extend([
                revenue_id, invoice['id'], invoice['client_name'], invoice['job_order_id'],
                invoice['invoice_date'], invoice['invoice_number'], invoice['subtotal'],
                invoice['total_amount'], invoice['amount_paid'], invoice['outstanding_balance'],
                invoice.get('product'), invoice.get('model'), invoice.get('unit_price'), invoice.get('order_quantity')
            ])
        
        detail_query = """
        INSERT INTO revenue_details (
            revenue_id, invoice_id, client_name, job_order_id, invoice_date,
            invoice_number, subtotal, total_amount, amount_paid, outstanding_balance,
            product, model, unit_price, order_quantity
        ) VALUES """ + ",".join([f"(${i*14+1}, ${i*14+2}, ${i*14+3}, ${i*14+4}, ${i*14+5}, ${i*14+6}, ${i*14+7}, ${i*14+8}, ${i*14+9}, ${i*14+10}, ${i*14+11}, ${i*14+12}, ${i*14+13}, ${i*14+14})" for i in range(len(report_data['invoices']))])
        
        await conn.execute(detail_query, *detail_values)
    
    return revenue_id

async def save_revenue_report(conn, report_data: Dict, start_date: date, end_date: date) -> int:
    """Save revenue report to database and return report ID"""
    
    # Insert main revenue record
    revenue_query = """
    INSERT INTO revenues (
        report_name, period_type, period_start_date, period_end_date,
        year, month, quarter, total_revenue, total_invoices,
        raw_materials_costs, operational_costs, general_costs,
        depreciation_costs, unexpected_costs, total_costs,
        profit, net_profit, profit_margin, net_profit_margin
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
    RETURNING id
    """
    
    period_info = report_data['period_info']
    summary = report_data['summary']
    
    # Calculate margins
    profit_margin = (summary['profit'] / summary['total_revenue'] * 100) if summary['total_revenue'] > 0 else 0
    net_profit_margin = (summary['net_profit'] / summary['total_revenue'] * 100) if summary['total_revenue'] > 0 else 0
    
    revenue_id = await conn.fetchval(
        revenue_query,
        report_data['report_name'],
        period_info['period_type'],
        start_date,  # Use actual date object
        end_date,    # Use actual date object
        period_info.get('year'),
        period_info.get('month'),
        period_info.get('quarter'),
        summary['total_revenue'],
        len(report_data['invoices']),
        summary['total_raw_materials_costs'],
        summary['total_operational_costs'],
        summary['total_general_costs'],
        summary['total_depreciation_costs'],
        summary['total_unexpected_costs'],
        summary['total_raw_materials_costs'] + summary['total_operational_costs'] + 
        summary['total_general_costs'] + summary['total_depreciation_costs'] + summary['total_unexpected_costs'],
        summary['profit'],
        summary['net_profit'],
        profit_margin,
        net_profit_margin
    )
    
    # Insert revenue details
    if report_data['invoices']:
        detail_values = []
        for invoice in report_data['invoices']:
            detail_values.extend([
                revenue_id, invoice['id'], invoice['client_name'], invoice['job_order_id'],
                invoice['invoice_date'], invoice['invoice_number'], invoice['subtotal'],
                invoice['total_amount'], invoice['amount_paid'], invoice['outstanding_balance'],
                invoice.get('product'), invoice.get('model'), invoice.get('unit_price'), invoice.get('order_quantity')
            ])
        
        detail_query = """
        INSERT INTO revenue_details (
            revenue_id, invoice_id, client_name, job_order_id, invoice_date,
            invoice_number, subtotal, total_amount, amount_paid, outstanding_balance,
            product, model, unit_price, order_quantity
        ) VALUES """ + ",".join([f"(${i*14+1}, ${i*14+2}, ${i*14+3}, ${i*14+4}, ${i*14+5}, ${i*14+6}, ${i*14+7}, ${i*14+8}, ${i*14+9}, ${i*14+10}, ${i*14+11}, ${i*14+12}, ${i*14+13}, ${i*14+14})" for i in range(len(report_data['invoices']))])
        
        await conn.execute(detail_query, *detail_values)
    
    return revenue_id

def calculate_total_costs(costs: List[Dict]) -> Decimal:
    """Calculate total costs (assuming USD currency for simplicity)"""
    total = Decimal('0.00')
    for cost in costs:
        # In a real implementation, you'd handle currency conversion here
        total += Decimal(str(cost['cost']))
    return total

@router.get("/reports/by-product", response_model=ProductRevenueReport)
async def get_revenue_report_by_product(
    period_type: PeriodType = Query(...),
    product_name: str = Query(..., description="Product name to filter by"),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    model: Optional[str] = Query(None, description="Optional model filter"),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Generate revenue report for specific product type in specified period"""
    
    try:
        # Get date range
        start_date, end_date = get_date_range(period_type, year, month, quarter, start_date, end_date)
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            # Modified query to filter by specific product
            base_query = """
            SELECT 
                jo.product,
                jo.model,
                COUNT(DISTINCT i.id) as total_invoices,
                SUM(i.amount_paid) as total_revenue,
                SUM(jo.order_quantity) as total_quantity,
                AVG(jo.unit_price) as average_unit_price,
                ARRAY_AGG(DISTINCT i.client_name) as clients,
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'id', i.id,
                        'client_name', i.client_name,
                        'job_order_id', i.job_order_id,
                        'invoice_date', i.invoice_date,
                        'invoice_number', i.invoice_number,
                        'subtotal', i.subtotal,
                        'total_amount', i.total_amount,
                        'amount_paid', i.amount_paid,
                        'outstanding_balance', i.outstanding_balance,
                        'product', jo.product,
                        'model', jo.model,
                        'unit_price', jo.unit_price,
                        'order_quantity', jo.order_quantity
                    )
                ) as invoices
            FROM invoices i
            INNER JOIN job_orders jo ON i.job_order_id = jo.id
            WHERE i.invoice_date >= $1 AND i.invoice_date <= $2
            AND UPPER(jo.product) LIKE UPPER($3)
            """
            
            params = [start_date, end_date, f"%{product_name}%"]
            
            if model:
                base_query += " AND UPPER(jo.model) LIKE UPPER($4)"
                params.append(f"%{model}%")
                base_query += " GROUP BY jo.product, jo.model ORDER BY total_revenue DESC"
            else:
                base_query += " GROUP BY jo.product, jo.model ORDER BY total_revenue DESC"
            
            product_data = await conn.fetch(base_query, *params)
            
            if not product_data:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No revenue data found for product '{product_name}' in the specified period"
                )
            
            # Fetch all cost types for the period
            raw_materials = await fetch_costs_by_period(conn, 'raw_materials_costs', start_date, end_date)
            operational_costs = await fetch_costs_by_period(conn, 'operational_costs', start_date, end_date)
            general_costs = await fetch_costs_by_period(conn, 'general_costs', start_date, end_date)
            depreciation_costs = await fetch_costs_by_period(conn, 'depreciation_costs', start_date, end_date)
            unexpected_costs = await fetch_costs_by_period(conn, 'unexpected_costs', start_date, end_date)
            
            # Calculate total costs
            total_raw_materials = calculate_total_costs(raw_materials)
            total_operational = calculate_total_costs(operational_costs)
            total_general = calculate_total_costs(general_costs)
            total_depreciation = calculate_total_costs(depreciation_costs)
            total_unexpected = calculate_total_costs(unexpected_costs)
            
            # Calculate totals
            total_revenue = sum(Decimal(str(product['total_revenue'])) for product in product_data)
            
            # Calculate profit and net profit
            profit = total_revenue - (total_raw_materials + total_operational)
            net_profit = profit - (total_general + total_depreciation + total_unexpected)
            
            # Prepare product data
            products = []
            for product in product_data:
                invoices_list = []
                # Parse JSON data if it's a string
                invoices_data = product['invoices']
                if isinstance(invoices_data, str):
                    invoices_data = json.loads(invoices_data)
                
                for invoice_data in invoices_data:
                    invoices_list.append(InvoiceData(**invoice_data))
                
                products.append(ProductRevenueData(
                    product=product['product'],
                    model=product['model'],
                    total_revenue=Decimal(str(product['total_revenue'])),
                    total_invoices=product['total_invoices'],
                    total_quantity=product['total_quantity'],
                    average_unit_price=Decimal(str(product['average_unit_price'])),
                    clients=product['clients'],
                    invoices=invoices_list
                ))
            
            # Prepare response
            report = ProductRevenueReport(
                period_info={
                    "period_type": period_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "year": year,
                    "month": month,
                    "quarter": quarter,
                    "product_filter": product_name,
                    "model_filter": model
                },
                products=products,
                total_costs={
                    "raw_materials": total_raw_materials,
                    "operational": total_operational,
                    "general": total_general,
                    "depreciation": total_depreciation,
                    "unexpected": total_unexpected
                },
                total_revenue=total_revenue,
                profit=profit,
                net_profit=net_profit
            )
            
            return report
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating product revenue report: {str(e)}")

@router.get("/reports/by-customer", response_model=CustomerRevenueReport)
async def get_revenue_report_by_customer(
    period_type: PeriodType = Query(...),
    client_name: str = Query(..., description="Client name to filter by"),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Generate revenue report for specific customer in specified period"""
    
    try:
        # Get date range
        start_date, end_date = get_date_range(period_type, year, month, quarter, start_date, end_date)
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            # Modified query to filter by specific customer (case insensitive)
            query = """
            SELECT 
                TRIM(UPPER(i.client_name)) as normalized_client_name,
                STRING_AGG(DISTINCT i.client_name, ', ') as client_name_variants,
                COUNT(DISTINCT i.id) as total_invoices,
                COUNT(DISTINCT i.job_order_id) as total_orders,
                SUM(i.amount_paid) as total_revenue,
                SUM(i.outstanding_balance) as outstanding_balance,
                ARRAY_AGG(DISTINCT CONCAT(jo.product, ' - ', jo.model)) as products,
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'id', i.id,
                        'client_name', i.client_name,
                        'job_order_id', i.job_order_id,
                        'invoice_date', i.invoice_date,
                        'invoice_number', i.invoice_number,
                        'subtotal', i.subtotal,
                        'total_amount', i.total_amount,
                        'amount_paid', i.amount_paid,
                        'outstanding_balance', i.outstanding_balance,
                        'product', jo.product,
                        'model', jo.model,
                        'unit_price', jo.unit_price,
                        'order_quantity', jo.order_quantity
                    )
                ) as invoices
            FROM invoices i
            INNER JOIN job_orders jo ON i.job_order_id = jo.id
            WHERE i.invoice_date >= $1 AND i.invoice_date <= $2
            AND UPPER(i.client_name) LIKE UPPER($3)
            GROUP BY TRIM(UPPER(i.client_name))
            ORDER BY total_revenue DESC
            """
            
            search_pattern = f"%{client_name}%"
            customer_data = await conn.fetch(query, start_date, end_date, search_pattern)
            
            if not customer_data:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No revenue data found for client '{client_name}' in the specified period"
                )
            
            # Fetch all cost types for the period
            raw_materials = await fetch_costs_by_period(conn, 'raw_materials_costs', start_date, end_date)
            operational_costs = await fetch_costs_by_period(conn, 'operational_costs', start_date, end_date)
            general_costs = await fetch_costs_by_period(conn, 'general_costs', start_date, end_date)
            depreciation_costs = await fetch_costs_by_period(conn, 'depreciation_costs', start_date, end_date)
            unexpected_costs = await fetch_costs_by_period(conn, 'unexpected_costs', start_date, end_date)
            
            # Calculate total costs
            total_raw_materials = calculate_total_costs(raw_materials)
            total_operational = calculate_total_costs(operational_costs)
            total_general = calculate_total_costs(general_costs)
            total_depreciation = calculate_total_costs(depreciation_costs)
            total_unexpected = calculate_total_costs(unexpected_costs)
            
            # Calculate totals
            total_revenue = sum(Decimal(str(customer['total_revenue'])) for customer in customer_data)
            
            # Calculate profit and net profit
            profit = total_revenue - (total_raw_materials + total_operational)
            net_profit = profit - (total_general + total_depreciation + total_unexpected)
            
            # Prepare customer data
            customers = []
            for customer in customer_data:
                invoices_list = []
                # Parse JSON data if it's a string
                invoices_data = customer['invoices']
                if isinstance(invoices_data, str):
                    invoices_data = json.loads(invoices_data)
                
                for invoice_data in invoices_data:
                    invoices_list.append(InvoiceData(**invoice_data))
                
                # Use the first variant of client name for display
                display_name = customer['client_name_variants'].split(', ')[0]
                
                customers.append(CustomerRevenueData(
                    client_name=display_name,
                    total_revenue=Decimal(str(customer['total_revenue'])),
                    total_invoices=customer['total_invoices'],
                    total_orders=customer['total_orders'],
                    outstanding_balance=Decimal(str(customer['outstanding_balance'])),
                    products=customer['products'],
                    invoices=invoices_list
                ))
            
            # Prepare response
            report = CustomerRevenueReport(
                period_info={
                    "period_type": period_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "year": year,
                    "month": month,
                    "quarter": quarter,
                    "client_filter": client_name
                },
                customers=customers,
                total_costs={
                    "raw_materials": total_raw_materials,
                    "operational": total_operational,
                    "general": total_general,
                    "depreciation": total_depreciation,
                    "unexpected": total_unexpected
                },
                total_revenue=total_revenue,
                profit=profit,
                net_profit=net_profit
            )
            
            return report
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating customer revenue report: {str(e)}")

@router.get("/reports/customer-search")
async def search_customers(
    search_term: str = Query(..., min_length=2, description="Search term for customer names"),
    period_type: PeriodType = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(10, le=50),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Search for customers by name (case insensitive) within a specific period"""
    
    try:
        # Get date range
        start_date, end_date = get_date_range(period_type, year, month, quarter, start_date, end_date)
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            query = """
            SELECT 
                TRIM(UPPER(i.client_name)) as normalized_client_name,
                STRING_AGG(DISTINCT i.client_name, ', ') as client_name_variants,
                COUNT(DISTINCT i.id) as total_invoices,
                SUM(i.amount_paid) as total_revenue
            FROM invoices i
            WHERE i.invoice_date >= $1 AND i.invoice_date <= $2
            AND UPPER(i.client_name) LIKE UPPER($3)
            GROUP BY TRIM(UPPER(i.client_name))
            ORDER BY total_revenue DESC
            LIMIT $4
            """
            
            search_pattern = f"%{search_term}%"
            rows = await conn.fetch(query, start_date, end_date, search_pattern, limit)
            
            customers = []
            for row in rows:
                customers.append({
                    "client_name": row['client_name_variants'].split(', ')[0],
                    "name_variants": row['client_name_variants'].split(', '),
                    "total_invoices": row['total_invoices'],
                    "total_revenue": row['total_revenue']
                })
            
            return {
                "search_term": search_term,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "customers": customers,
                "total_found": len(customers)
            }
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching customers: {str(e)}")
    """Calculate total costs (assuming USD currency for simplicity)"""
    total = Decimal('0.00')
    for cost in costs:
        # In a real implementation, you'd handle currency conversion here
        total += Decimal(str(cost['cost']))
    return total

# API Endpoints

@router.post("/generate-and-save", response_model=Dict)
async def generate_and_save_revenue_report(
    request: RevenueRequest,
    report_name: str = Query(..., description="Name for the revenue report"),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Generate and save revenue report to database"""
    
    try:
        # Get date range
        start_date, end_date = get_date_range(
            request.period_type, 
            request.year, 
            request.month, 
            request.quarter,
            request.start_date, 
            request.end_date
        )
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            # Check if a report already exists for this exact period
            existing_report_query = """
            SELECT id, report_name, generated_at 
            FROM revenues 
            WHERE period_start_date = $1 AND period_end_date = $2 AND status = 'active'
            ORDER BY generated_at DESC
            LIMIT 1
            """
            
            existing_report = await conn.fetchrow(existing_report_query, start_date, end_date)
            
            if existing_report:
                return {
                    "message": "Revenue report already exists for this period",
                    "existing_report": {
                        "revenue_id": existing_report['id'],
                        "report_name": existing_report['report_name'],
                        "generated_at": existing_report['generated_at'].isoformat(),
                        "period": {
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat()
                        }
                    },
                    "action": "Use existing report or delete it first to generate a new one"
                }
            
            # Fetch invoices with job order details
            invoices_data = await fetch_invoices_with_orders(conn, start_date, end_date)
            
            # Calculate total revenue
            total_revenue = sum(Decimal(str(invoice['amount_paid'])) for invoice in invoices_data)
            
            # Fetch all cost types
            raw_materials = await fetch_costs_by_period(conn, 'raw_materials_costs', start_date, end_date)
            operational_costs = await fetch_costs_by_period(conn, 'operational_costs', start_date, end_date)
            general_costs = await fetch_costs_by_period(conn, 'general_costs', start_date, end_date)
            depreciation_costs = await fetch_costs_by_period(conn, 'depreciation_costs', start_date, end_date)
            unexpected_costs = await fetch_costs_by_period(conn, 'unexpected_costs', start_date, end_date)
            
            # Calculate totals
            total_raw_materials = calculate_total_costs(raw_materials)
            total_operational = calculate_total_costs(operational_costs)
            total_general = calculate_total_costs(general_costs)
            total_depreciation = calculate_total_costs(depreciation_costs)
            total_unexpected = calculate_total_costs(unexpected_costs)
            
            # Calculate profit and net profit
            profit = total_revenue - (total_raw_materials + total_operational)
            net_profit = profit - (total_general + total_depreciation + total_unexpected)
            
            # Prepare report data
            report_data = {
                "report_name": report_name,
                "period_info": {
                    "period_type": request.period_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "year": request.year,
                    "month": request.month,
                    "quarter": request.quarter
                },
                "invoices": invoices_data,
                "summary": {
                    "total_revenue": total_revenue,
                    "total_raw_materials_costs": total_raw_materials,
                    "total_operational_costs": total_operational,
                    "total_general_costs": total_general,
                    "total_depreciation_costs": total_depreciation,
                    "total_unexpected_costs": total_unexpected,
                    "profit": profit,
                    "net_profit": net_profit
                }
            }
            
            # Save to database
            revenue_id = await save_revenue_report(conn, report_data, start_date, end_date)
            
            return {
                "message": "Revenue report generated and saved successfully",
                "revenue_id": revenue_id,
                "report_name": report_name,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "summary": {
                    "total_revenue": total_revenue,
                    "profit": profit,
                    "net_profit": net_profit,
                    "total_invoices": len(invoices_data)
                }
            }
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating and saving revenue report: {str(e)}")

@router.get("/saved-reports", response_model=List[SavedRevenueReport])
async def get_saved_revenue_reports(
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    status: str = Query("active"),
    period_type: Optional[PeriodType] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get list of saved revenue reports with optional period filtering"""
    
    try:
        conn = await connect_to_db()
        
        try:
            # Build dynamic query based on filters
            where_conditions = ["status = $1"]
            params = [status]
            param_count = 1
            
            if period_type:
                param_count += 1
                where_conditions.append(f"period_type = ${param_count}")
                params.append(period_type.value)
            
            if year:
                param_count += 1
                where_conditions.append(f"year = ${param_count}")
                params.append(year)
            
            if month:
                param_count += 1
                where_conditions.append(f"month = ${param_count}")
                params.append(month)
            
            if quarter:
                param_count += 1
                where_conditions.append(f"quarter = ${param_count}")
                params.append(quarter)
            
            if start_date and end_date:
                param_count += 1
                where_conditions.append(f"period_start_date >= ${param_count}")
                params.append(start_date)
                param_count += 1
                where_conditions.append(f"period_end_date <= ${param_count}")
                params.append(end_date)
            elif start_date:
                param_count += 1
                where_conditions.append(f"period_start_date >= ${param_count}")
                params.append(start_date)
            elif end_date:
                param_count += 1
                where_conditions.append(f"period_end_date <= ${param_count}")
                params.append(end_date)
            
            # Add limit and offset
            param_count += 1
            limit_param = param_count
            param_count += 1
            offset_param = param_count
            
            params.extend([limit, offset])
            
            query = f"""
            SELECT id, report_name, period_type, period_start_date, period_end_date,
                   total_revenue, profit, net_profit, profit_margin, net_profit_margin,
                   generated_at, status
            FROM revenues
            WHERE {' AND '.join(where_conditions)}
            ORDER BY generated_at DESC
            LIMIT ${limit_param} OFFSET ${offset_param}
            """
            
            rows = await conn.fetch(query, *params)
            
            reports = []
            for row in rows:
                reports.append(SavedRevenueReport(
                    id=row['id'],
                    report_name=row['report_name'],
                    period_type=row['period_type'],
                    period_start_date=row['period_start_date'],
                    period_end_date=row['period_end_date'],
                    total_revenue=row['total_revenue'],
                    profit=row['profit'],
                    net_profit=row['net_profit'],
                    profit_margin=row['profit_margin'],
                    net_profit_margin=row['net_profit_margin'],
                    generated_at=row['generated_at'],
                    status=row['status']
                ))
            
            return reports
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching saved reports: {str(e)}")

@router.get("/saved-reports/by-period", response_model=RevenueReport)
async def get_saved_revenue_report_by_period(
    period_type: PeriodType = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get detailed saved revenue report by period selection"""
    
    try:
        # Get date range based on period selection
        calculated_start_date, calculated_end_date = get_date_range(
            period_type, year, month, quarter, start_date, end_date
        )
        
        conn = await connect_to_db()
        
        try:
            # Find revenue report that matches the period
            revenue_query = """
            SELECT * FROM revenues 
            WHERE period_start_date = $1 AND period_end_date = $2 AND status = 'active'
            ORDER BY generated_at DESC
            LIMIT 1
            """
            revenue_row = await conn.fetchrow(revenue_query, calculated_start_date, calculated_end_date)
            
            if not revenue_row:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No revenue report found for period {calculated_start_date} to {calculated_end_date}"
                )
            
            # Get revenue details (invoices)
            details_query = """
            SELECT * FROM revenue_details WHERE revenue_id = $1
            ORDER BY invoice_date DESC
            """
            detail_rows = await conn.fetch(details_query, revenue_row['id'])
            
            # Get costs for the period
            raw_materials = await fetch_costs_by_period(conn, 'raw_materials_costs', calculated_start_date, calculated_end_date)
            operational_costs = await fetch_costs_by_period(conn, 'operational_costs', calculated_start_date, calculated_end_date)
            general_costs = await fetch_costs_by_period(conn, 'general_costs', calculated_start_date, calculated_end_date)
            depreciation_costs = await fetch_costs_by_period(conn, 'depreciation_costs', calculated_start_date, calculated_end_date)
            unexpected_costs = await fetch_costs_by_period(conn, 'unexpected_costs', calculated_start_date, calculated_end_date)
            
            # Prepare response
            invoices_data = []
            for detail in detail_rows:
                invoices_data.append(InvoiceData(
                    id=detail['invoice_id'],
                    client_name=detail['client_name'],
                    job_order_id=detail['job_order_id'],
                    invoice_date=detail['invoice_date'],
                    invoice_number=detail['invoice_number'],
                    subtotal=detail['subtotal'],
                    total_amount=detail['total_amount'],
                    amount_paid=detail['amount_paid'],
                    outstanding_balance=detail['outstanding_balance'],
                    product=detail['product'],
                    model=detail['model'],
                    unit_price=detail['unit_price'],
                    order_quantity=detail['order_quantity']
                ))
            
            report = RevenueReport(
                id=revenue_row['id'],
                report_name=revenue_row['report_name'],
                period_info={
                    "period_type": revenue_row['period_type'],
                    "start_date": calculated_start_date.isoformat(),
                    "end_date": calculated_end_date.isoformat(),
                    "year": revenue_row['year'],
                    "month": revenue_row['month'],
                    "quarter": revenue_row['quarter']
                },
                total_revenue=revenue_row['total_revenue'],
                invoices=invoices_data,
                costs={
                    "raw_materials": [CostData(**cost) for cost in raw_materials],
                    "operational": [CostData(**cost) for cost in operational_costs],
                    "general": [CostData(**cost) for cost in general_costs],
                    "depreciation": [CostData(**cost) for cost in depreciation_costs],
                    "unexpected": [CostData(**cost) for cost in unexpected_costs]
                },
                profit=revenue_row['profit'],
                net_profit=revenue_row['net_profit'],
                summary={
                    "total_revenue": revenue_row['total_revenue'],
                    "total_raw_materials_costs": revenue_row['raw_materials_costs'],
                    "total_operational_costs": revenue_row['operational_costs'],
                    "total_general_costs": revenue_row['general_costs'],
                    "total_depreciation_costs": revenue_row['depreciation_costs'],
                    "total_unexpected_costs": revenue_row['unexpected_costs'],
                    "profit": revenue_row['profit'],
                    "net_profit": revenue_row['net_profit']
                },
                generated_at=revenue_row['generated_at']
            )
            
            return report
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching saved revenue report: {str(e)}")

@router.delete("/saved-reports/{revenue_id}")
async def delete_revenue_report(
    revenue_id: int,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Delete (archive) a revenue report"""
    
    try:
        conn = await connect_to_db()
        
        try:
            # Update status to deleted instead of actually deleting
            query = """
            UPDATE revenues 
            SET status = 'deleted', updated_at = CURRENT_TIMESTAMP 
            WHERE id = $1 AND status = 'active'
            RETURNING id
            """
            
            result = await conn.fetchrow(query, revenue_id)
            
            if not result:
                raise HTTPException(status_code=404, detail="Revenue report not found")
            
            return {"message": "Revenue report deleted successfully", "revenue_id": revenue_id}
            
        finally:
            await conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting revenue report: {str(e)}")

@router.post("/report", response_model=RevenueReport)
async def generate_revenue_report(
    request: RevenueRequest,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Generate comprehensive revenue report for specified period"""
    
    try:
        # Get date range
        start_date, end_date = get_date_range(
            request.period_type, 
            request.year, 
            request.month, 
            request.quarter,
            request.start_date, 
            request.end_date
        )
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            # Fetch invoices with job order details
            invoices_data = await fetch_invoices_with_orders(conn, start_date, end_date)
            
            # Calculate total revenue
            total_revenue = sum(Decimal(str(invoice['amount_paid'])) for invoice in invoices_data)
            
            # Fetch all cost types
            raw_materials = await fetch_costs_by_period(conn, 'raw_materials_costs', start_date, end_date)
            operational_costs = await fetch_costs_by_period(conn, 'operational_costs', start_date, end_date)
            general_costs = await fetch_costs_by_period(conn, 'general_costs', start_date, end_date)
            depreciation_costs = await fetch_costs_by_period(conn, 'depreciation_costs', start_date, end_date)
            unexpected_costs = await fetch_costs_by_period(conn, 'unexpected_costs', start_date, end_date)
            
            # Calculate totals
            total_raw_materials = calculate_total_costs(raw_materials)
            total_operational = calculate_total_costs(operational_costs)
            total_general = calculate_total_costs(general_costs)
            total_depreciation = calculate_total_costs(depreciation_costs)
            total_unexpected = calculate_total_costs(unexpected_costs)
            
            # Calculate profit and net profit
            profit = total_revenue - (total_raw_materials + total_operational)
            net_profit = profit - (total_general + total_depreciation + total_unexpected)
            
            # Prepare response
            report = RevenueReport(
                period_info={
                    "period_type": request.period_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "year": request.year,
                    "month": request.month,
                    "quarter": request.quarter
                },
                total_revenue=total_revenue,
                invoices=[InvoiceData(**invoice) for invoice in invoices_data],
                costs={
                    "raw_materials": [CostData(**cost) for cost in raw_materials],
                    "operational": [CostData(**cost) for cost in operational_costs],
                    "general": [CostData(**cost) for cost in general_costs],
                    "depreciation": [CostData(**cost) for cost in depreciation_costs],
                    "unexpected": [CostData(**cost) for cost in unexpected_costs]
                },
                profit=profit,
                net_profit=net_profit,
                summary={
                    "total_revenue": total_revenue,
                    "total_raw_materials_costs": total_raw_materials,
                    "total_operational_costs": total_operational,
                    "total_general_costs": total_general,
                    "total_depreciation_costs": total_depreciation,
                    "total_unexpected_costs": total_unexpected,
                    "profit": profit,
                    "net_profit": net_profit
                }
            )
            
            return report
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating revenue report: {str(e)}")

@router.get("/summary")
async def get_revenue_summary(
    period_type: PeriodType = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get quick revenue summary without detailed data"""
    
    try:
        # Get date range
        start_date, end_date = get_date_range(period_type, year, month, quarter, start_date, end_date)
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            # Get total revenue
            revenue_query = """
            SELECT COALESCE(SUM(amount_paid), 0) as total_revenue
            FROM invoices
            WHERE invoice_date >= $1 AND invoice_date <= $2
            """
            revenue_result = await conn.fetchrow(revenue_query, start_date, end_date)
            total_revenue = Decimal(str(revenue_result['total_revenue']))
            
            # Get total costs
            cost_tables = [
                'raw_materials_costs',
                'operational_costs',
                'general_costs',
                'depreciation_costs',
                'unexpected_costs'
            ]
            
            total_costs = Decimal('0.00')
            cost_breakdown = {}
            
            for table in cost_tables:
                cost_query = f"""
                SELECT COALESCE(SUM(cost), 0) as total_cost
                FROM {table}
                WHERE submission_date >= $1 AND submission_date <= $2
                """
                cost_result = await conn.fetchrow(cost_query, start_date, end_date)
                table_total = Decimal(str(cost_result['total_cost']))
                total_costs += table_total
                cost_breakdown[table] = table_total
            
            # Separate direct costs from indirect costs
            direct_costs = cost_breakdown['raw_materials_costs'] + cost_breakdown['operational_costs']
            indirect_costs = (cost_breakdown['general_costs'] + 
                            cost_breakdown['depreciation_costs'] + 
                            cost_breakdown['unexpected_costs'])
            
            profit = total_revenue - direct_costs
            net_profit = profit - indirect_costs
            
            return {
                "period": {
                    "type": period_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "total_revenue": total_revenue,
                "total_costs": total_costs,
                "direct_costs": direct_costs,
                "indirect_costs": indirect_costs,
                "profit": profit,
                "net_profit": net_profit,
                "profit_margin": (profit / total_revenue * 100) if total_revenue > 0 else 0,
                "net_profit_margin": (net_profit / total_revenue * 100) if total_revenue > 0 else 0
            }
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting revenue summary: {str(e)}")

@router.get("/invoices")
async def get_period_invoices(
    period_type: PeriodType = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get invoices for specified period"""
    
    try:
        # Get date range
        start_date, end_date = get_date_range(period_type, year, month, quarter, start_date, end_date)
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            invoices_data = await fetch_invoices_with_orders(conn, start_date, end_date)
            
            return {
                "period": {
                    "type": period_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "invoices": invoices_data,
                "total_invoices": len(invoices_data),
                "total_revenue": sum(Decimal(str(invoice['amount_paid'])) for invoice in invoices_data)
            }
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching invoices: {str(e)}")

@router.get("/costs/{cost_type}")
async def get_period_costs(
    cost_type: str,
    period_type: PeriodType = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get costs by type for specified period"""
    
    valid_cost_types = [
        'raw_materials_costs',
        'operational_costs',
        'general_costs',
        'depreciation_costs',
        'unexpected_costs'
    ]
    
    if cost_type not in valid_cost_types:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {valid_cost_types}")
    
    try:
        # Get date range
        start_date, end_date = get_date_range(period_type, year, month, quarter, start_date, end_date)
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            costs_data = await fetch_costs_by_period(conn, cost_type, start_date, end_date)
            total_costs = calculate_total_costs(costs_data)
            
            return {
                "period": {
                    "type": period_type,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "cost_type": cost_type,
                "costs": costs_data,
                "total_costs": total_costs,
                "count": len(costs_data)
            }
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching costs: {str(e)}")

@router.get("/export/csv")
async def export_revenue_report_csv(
    period_type: PeriodType = Query(...),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Export revenue report as CSV"""
    
    try:
        # Generate report data
        request = RevenueRequest(
            period_type=period_type,
            year=year,
            month=month,
            quarter=quarter,
            start_date=start_date,
            end_date=end_date
        )
        
        # Get date range
        start_date, end_date = get_date_range(period_type, year, month, quarter, start_date, end_date)
        
        # Connect to database
        conn = await connect_to_db()
        
        try:
            invoices_data = await fetch_invoices_with_orders(conn, start_date, end_date)
            
            # Create CSV content
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow([
                'Invoice ID', 'Client Name', 'Job Order ID', 'Invoice Date',
                'Invoice Number', 'Subtotal', 'Total Amount', 'Amount Paid',
                'Outstanding Balance', 'Product', 'Model', 'Unit Price', 'Order Quantity'
            ])
            
            # Write data
            for invoice in invoices_data:
                writer.writerow([
                    invoice['id'],
                    invoice['client_name'],
                    invoice['job_order_id'],
                    invoice['invoice_date'],
                    invoice['invoice_number'],
                    invoice['subtotal'],
                    invoice['total_amount'],
                    invoice['amount_paid'],
                    invoice['outstanding_balance'],
                    invoice['product'],
                    invoice['model'],
                    invoice['unit_price'],
                    invoice['order_quantity']
                ])
            
            # Prepare response
            csv_content = output.getvalue()
            output.close()
            
            filename = f"revenue_report_{start_date}_{end_date}.csv"
            
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting CSV: {str(e)}")

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "revenue_system"}