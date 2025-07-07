from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime,  date, timedelta
from decimal import Decimal
import asyncpg
import json
from routers.employees import admin_or_manager, TokenData

from enum import Enum

import calendar



# Database connection
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# Initialize router
router = APIRouter(prefix="/factory-costs", tags=["Factory Costs"])

# Pydantic models for request/response
class CostItemBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    costs: Decimal = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=10)
    quantity: Optional[Decimal] = Field(None)
    type: Optional[str] = Field(None, max_length=100)
    
    # Customer and order integration
    client_name: str = Field(..., min_length=1, max_length=255)
    job_order_id: int = Field(..., gt=0)
    
    dynamic_fields: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @validator('costs')
    def validate_costs(cls, v):
        if v <= 0:
            raise ValueError('Costs must be greater than 0')
        return v

    @validator('currency')
    def validate_currency(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('Currency cannot be empty')
        return v.upper().strip()

    @validator('client_name')
    def validate_client_name(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('Client name cannot be empty')
        return v.strip()

class CostItemCreate(BaseModel):
    title: str
    cost: Decimal
    quantity: Optional[int] = None
    currency: str = "USD"
    type: Optional[str] = None
    dynamic_fields: Optional[Dict[str, Any]] = None
    submission_date: Optional[date] = None  # Allow custom submission date

class ReportPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"

class CostReportRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.MONTHLY
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    cost_types: Optional[List[str]] = Field(None, description="Filter by specific cost types")
    currency: Optional[str] = None
    cost_type_filter: Optional[str] = Field(None, description="Filter by specific type within cost category")
    include_breakdown: bool = Field(True, description="Include detailed breakdowns")
    include_trends: bool = Field(True, description="Include trend analysis")
    min_cost: Optional[Decimal] = None
    max_cost: Optional[Decimal] = None

class CostSummary(BaseModel):
    total_items: int
    total_costs: Decimal
    average_cost: Decimal
    min_cost: Decimal
    max_cost: Decimal
    currencies_used: int
    cost_categories_count: int
    unique_types: int

class CostBreakdown(BaseModel):
    category: str
    count: int
    total_cost: Decimal
    percentage: float
    average_cost: Decimal

class TrendData(BaseModel):
    period_label: str
    period_start: date
    period_end: date
    total_cost: Decimal
    item_count: int
    average_cost: Decimal

class CostTypeDetail(BaseModel):
    cost_type: str
    summary: CostSummary
    type_breakdown: List[CostBreakdown]
    currency_breakdown: List[CostBreakdown]
    items: List[Dict[str, Any]]

class CostReportResponse(BaseModel):
    report_metadata: Dict[str, Any]
    summary: CostSummary
    cost_type_breakdown: List[CostBreakdown]
    client_breakdown: List[CostBreakdown]
    currency_breakdown: List[CostBreakdown]
    trends: Optional[List[TrendData]] = None
    detailed_items: Optional[List[Dict[str, Any]]] = None
    insights: Dict[str, Any]

class CostItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    costs: Optional[Decimal] = Field(None, gt=0)
    currency: Optional[str] = Field(None, max_length=10)
    quantity: Optional[Decimal] = Field(None)
    type: Optional[str] = Field(None, max_length=100)
    client_name: Optional[str] = Field(None, min_length=1, max_length=255)
    job_order_id: Optional[int] = Field(None, gt=0)
    dynamic_fields: Optional[Dict[str, Any]] = None

    @validator('costs')
    def validate_costs(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Costs must be greater than 0')
        return v

    @validator('client_name')
    def validate_client_name(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError('Client name cannot be empty')
        return v.strip() if v is not None else None

class CostItemResponse(BaseModel):
    id: int
    title: str
    cost: Decimal
    quantity: Optional[int]
    currency: str
    type: Optional[str]
    dynamic_fields: Optional[Dict[str, Any]]
    submission_date: date
    created_at: datetime
    updated_at: datetime

class CostItemFilter(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    type: Optional[str] = None
    currency: Optional[str] = None
    min_cost: Optional[Decimal] = None
    max_cost: Optional[Decimal] = None

class CustomerJobOrder(BaseModel):
    job_order_id: int
    client_name: str

# Table names mapping
COST_TABLES = {
    "raw_materials": "raw_materials_costs",
    "operational": "operational_costs",
    "general": "general_costs",
    "depreciation": "depreciation_costs",
    "unexpected": "unexpected_costs"
}

# Helper functions
async def verify_customer_job_order(job_order_id: int, client_name: str):
    """Verify that the job order exists and belongs to the specified client"""
    conn = await connect_to_db()
    try:
        query = """
        SELECT ca.client_name, ca.job_order_id 
        FROM customer_accounts ca 
        WHERE ca.job_order_id = $1 AND LOWER(ca.client_name) = LOWER($2)
        """
        result = await conn.fetchrow(query, job_order_id, client_name)
        return result is not None
    finally:
        await conn.close()

async def get_customer_job_orders():
    """Get all available customer job orders"""
    conn = await connect_to_db()
    try:
        query = """
        SELECT DISTINCT client_name, job_order_id 
        FROM customer_accounts 
        ORDER BY client_name, job_order_id
        """
        results = await conn.fetch(query)
        return [{"client_name": row['client_name'], "job_order_id": row['job_order_id']} for row in results]
    finally:
        await conn.close()

def get_period_dates(period: ReportPeriod, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """Calculate start and end dates based on period type"""
    today = date.today()
    
    if period == ReportPeriod.CUSTOM:
        if not start_date or not end_date:
            raise ValueError("Custom period requires both start_date and end_date")
        return start_date, end_date
    
    elif period == ReportPeriod.DAILY:
        target_date = start_date or today
        return target_date, target_date
    
    elif period == ReportPeriod.WEEKLY:
        if start_date:
            # Start from beginning of week containing start_date
            start = start_date - timedelta(days=start_date.weekday())
        else:
            # Current week
            start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end
    
    elif period == ReportPeriod.MONTHLY:
        if start_date:
            year, month = start_date.year, start_date.month
        else:
            year, month = today.year, today.month
        
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        return start, end
    
    elif period == ReportPeriod.QUARTERLY:
        if start_date:
            year = start_date.year
            quarter = (start_date.month - 1) // 3 + 1
        else:
            year = today.year
            quarter = (today.month - 1) // 3 + 1
        
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        end = date(year, end_month, calendar.monthrange(year, end_month)[1])
        return start, end
    
    elif period == ReportPeriod.YEARLY:
        year = start_date.year if start_date else today.year
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        return start, end

def get_trend_periods(period: ReportPeriod, start_date: date, end_date: date, periods_count: int = 12):
    """Generate periods for trend analysis"""
    periods = []
    
    if period == ReportPeriod.DAILY:
        # Show daily trends for the past N days
        for i in range(periods_count):
            period_date = end_date - timedelta(days=periods_count - 1 - i)
            periods.append({
                'label': period_date.strftime('%Y-%m-%d'),
                'start': period_date,
                'end': period_date
            })
    
    elif period == ReportPeriod.WEEKLY:
        # Show weekly trends
        for i in range(periods_count):
            week_start = start_date - timedelta(weeks=periods_count - 1 - i)
            week_start = week_start - timedelta(days=week_start.weekday())  # Start of week
            week_end = week_start + timedelta(days=6)
            periods.append({
                'label': f"Week of {week_start.strftime('%Y-%m-%d')}",
                'start': week_start,
                'end': week_end
            })
    
    elif period == ReportPeriod.MONTHLY:
        # Show monthly trends
        current_date = end_date.replace(day=1)
        for i in range(periods_count):
            if i > 0:
                if current_date.month == 1:
                    current_date = current_date.replace(year=current_date.year - 1, month=12)
                else:
                    current_date = current_date.replace(month=current_date.month - 1)
            
            month_start = current_date
            month_end = date(current_date.year, current_date.month, 
                           calendar.monthrange(current_date.year, current_date.month)[1])
            periods.insert(0, {
                'label': current_date.strftime('%Y-%m'),
                'start': month_start,
                'end': month_end
            })
    
    return periods

async def generate_cost_insights(summary: CostSummary, cost_type_data: Dict, trends: List[TrendData] = None):
    """Generate insights based on cost data"""
    insights = {
        "cost_efficiency": {},
        "spending_patterns": {},
        "recommendations": []
    }
    
    # Cost efficiency insights
    if summary.total_items > 0:
        insights["cost_efficiency"]["average_cost_per_item"] = safe_float(summary.average_cost)
        insights["cost_efficiency"]["cost_variance"] = {
            "min": safe_float(summary.min_cost),
            "max": safe_float(summary.max_cost),
            "range": safe_float(summary.max_cost) - safe_float(summary.min_cost)
        }
    
    # Spending patterns
    if cost_type_data:
        highest_spending_type = max(cost_type_data.items(), key=lambda x: safe_float(x[1]['total_cost']))
        insights["spending_patterns"]["highest_cost_category"] = {
            "category": highest_spending_type[0],
            "amount": safe_float(highest_spending_type[1]['total_cost']),
            "percentage": calculate_percentage(
                highest_spending_type[1]['total_cost'], 
                summary.total_costs
            )
        }
    
    # Trend insights
    if trends and len(trends) >= 2:
        recent_change = safe_float(trends[-1].total_cost) - safe_float(trends[-2].total_cost)
        insights["spending_patterns"]["recent_trend"] = {
            "direction": "increasing" if recent_change > 0 else "decreasing" if recent_change < 0 else "stable",
            "change_amount": abs(recent_change),
            "change_percentage": calculate_percentage(
                abs(recent_change), 
                trends[-2].total_cost
            )
        }
    
    # Recommendations (simplified)
    if safe_float(summary.total_costs) > 0:
        avg_cost = safe_float(summary.average_cost)
        total_avg = safe_float(summary.total_costs) / max(1, summary.total_items)
        
        if avg_cost > total_avg * 1.5:
            insights["recommendations"].append("Consider reviewing high-cost items for potential optimization")
        
        if summary.currencies_used > 1:
            insights["recommendations"].append("Multiple currencies detected - consider currency consolidation for better tracking")
        
        # Cost distribution analysis
        if cost_type_data and len(cost_type_data) > 0:
            cost_values = [safe_float(data['total_cost']) for data in cost_type_data.values()]
            if cost_values:
                max_cost_type = max(cost_values)
                total_costs = sum(cost_values)
                if total_costs > 0 and max_cost_type / total_costs > 0.6:
                    insights["recommendations"].append("High concentration in single cost category - consider reviewing cost distribution")
    
    return insights

async def get_cost_item_by_id(table_name: str, item_id: int):
    """Get a single cost item by ID"""
    conn = await connect_to_db()
    try:
        query = f"""
        SELECT id, title, costs, currency, quantity, type, client_name, job_order_id,
               date_time, dynamic_fields, created_at, updated_at
        FROM {table_name} 
        WHERE id = $1
        """
        result = await conn.fetchrow(query, item_id)
        return result
    finally:
        await conn.close()

async def create_cost_item(table_name: str, item: CostItemCreate):
    """Create a new cost item in the specified table"""
    conn = await connect_to_db()
    try:
        query = f"""
            INSERT INTO {table_name} (
                title, cost, quantity, currency, type, dynamic_fields, submission_date
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7
            ) RETURNING *
        """
        
        # Use provided submission_date or default to today
        submission_date = item.submission_date or date.today()
        
        values = (
            item.title,
            item.cost,
            item.quantity,
            item.currency,
            item.type,
            json.dumps(item.dynamic_fields) if item.dynamic_fields else None,
            submission_date
        )
        
        result = await conn.fetchrow(query, *values)
        return result
    except Exception as e:
        print(f"Database error: {e}")
        return None
    finally:
        await conn.close()
    
async def update_cost_item(table_name: str, item_id: int, item_data: CostItemUpdate):
    """Update an existing cost item"""
    conn = await connect_to_db()
    try:
        # Build dynamic update query
        update_fields = []
        values = []
        param_count = 1
        
        if item_data.title is not None:
            update_fields.append(f"title = ${param_count}")
            values.append(item_data.title)
            param_count += 1
        
        if item_data.costs is not None:
            update_fields.append(f"costs = ${param_count}")
            values.append(item_data.costs)
            param_count += 1
        
        if item_data.currency is not None:
            update_fields.append(f"currency = ${param_count}")
            values.append(item_data.currency.upper().strip())
            param_count += 1
        
        if item_data.quantity is not None:
            update_fields.append(f"quantity = ${param_count}")
            values.append(item_data.quantity)
            param_count += 1
        
        if item_data.type is not None:
            update_fields.append(f"type = ${param_count}")
            values.append(item_data.type)
            param_count += 1
        
        if item_data.client_name is not None:
            update_fields.append(f"client_name = ${param_count}")
            values.append(item_data.client_name)
            param_count += 1
        
        if item_data.job_order_id is not None:
            update_fields.append(f"job_order_id = ${param_count}")
            values.append(item_data.job_order_id)
            param_count += 1
        
        if item_data.dynamic_fields is not None:
            update_fields.append(f"dynamic_fields = ${param_count}")
            values.append(json.dumps(item_data.dynamic_fields))
            param_count += 1
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # If updating client_name or job_order_id, verify the combination exists
        if item_data.client_name is not None or item_data.job_order_id is not None:
            # Get current values for verification
            current_item = await get_cost_item_by_id(table_name, item_id)
            if not current_item:
                raise HTTPException(status_code=404, detail="Cost item not found")
            
            verify_client = item_data.client_name if item_data.client_name is not None else current_item['client_name']
            verify_order = item_data.job_order_id if item_data.job_order_id is not None else current_item['job_order_id']
            
            if not await verify_customer_job_order(verify_order, verify_client):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Job order {verify_order} does not exist for client '{verify_client}'"
                )
        
        values.append(item_id)
        
        query = f"""
        UPDATE {table_name} 
        SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
        WHERE id = ${param_count}
        RETURNING id, title, costs, currency, quantity, type, client_name, job_order_id,
                  date_time, dynamic_fields, created_at, updated_at
        """
        
        result = await conn.fetchrow(query, *values)
        return result
    finally:
        await conn.close()

async def delete_cost_item(table_name: str, item_id: int):
    """Delete a cost item"""
    conn = await connect_to_db()
    try:
        query = f"DELETE FROM {table_name} WHERE id = $1 RETURNING id"
        result = await conn.fetchrow(query, item_id)
        return result
    finally:
        await conn.close()

async def get_cost_items_with_filters(table_name: str, filters: CostItemFilter, skip: int = 0, limit: int = 100):
    """Get cost items with filters from the specified table"""
    conn = await connect_to_db()
    try:
        conditions = []
        values = []
        param_count = 0
        
        # Build WHERE conditions
        if filters.start_date:
            param_count += 1
            conditions.append(f"submission_date >= ${param_count}")
            values.append(filters.start_date.date())
        
        if filters.end_date:
            param_count += 1
            conditions.append(f"submission_date <= ${param_count}")
            values.append(filters.end_date.date())
        
        if filters.type:
            param_count += 1
            conditions.append(f"type = ${param_count}")
            values.append(filters.type)
        
        if filters.currency:
            param_count += 1
            conditions.append(f"currency = ${param_count}")
            values.append(filters.currency)
        
        if filters.min_cost:
            param_count += 1
            conditions.append(f"cost >= ${param_count}")
            values.append(filters.min_cost)
        
        if filters.max_cost:
            param_count += 1
            conditions.append(f"cost <= ${param_count}")
            values.append(filters.max_cost)
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Count query - only pass values if there are conditions
        count_query = f"SELECT COUNT(*) FROM {table_name}{where_clause}"
        if values:
            total_count = await conn.fetchval(count_query, *values)
        else:
            total_count = await conn.fetchval(count_query)
        
        # Data query with pagination
        param_count += 1
        limit_param = f"${param_count}"
        param_count += 1
        offset_param = f"${param_count}"
        
        data_query = f"""
            SELECT * FROM {table_name}{where_clause}
            ORDER BY created_at DESC
            LIMIT {limit_param} OFFSET {offset_param}
        """
        
        # Add pagination parameters to values
        pagination_values = values + [limit, skip]
        results = await conn.fetch(data_query, *pagination_values)
        
        return results, total_count
    finally:
        await conn.close()

def format_cost_item_response(row) -> CostItemResponse:
    """Format database row to CostItemResponse"""
    return CostItemResponse(
        id=row['id'],
        title=row['title'],
        cost=row['cost'],  # Keep as Decimal for response model
        quantity=row['quantity'],
        currency=row['currency'],
        type=row['type'],
        dynamic_fields=row['dynamic_fields'],
        submission_date=row['submission_date'],
        created_at=row['created_at'],
        updated_at=row['updated_at']
    )
def safe_float(value):
    """Safely convert any numeric value to float"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def calculate_percentage(part, total):
    """Calculate percentage with safe float conversion"""
    part_val = safe_float(part)
    total_val = safe_float(total)
    
    if total_val == 0:
        return 0.0
    
    return round((part_val / total_val) * 100, 2)

def create_breakdown_item(category, count, total_cost, overall_total):
    """Create a standardized breakdown item"""
    return {
        'category': category,
        'count': int(count) if count else 0,
        'total_cost': str(safe_float(total_cost)),
        'percentage': calculate_percentage(total_cost, overall_total),
        'average_cost': str(safe_float(total_cost) / max(1, int(count or 1)))
    }

def create_summary_dict(total_items, total_costs, min_cost, max_cost, currencies_count, types_count):
    """Create a standardized summary dictionary"""
    total_items_val = int(total_items or 0)
    total_costs_val = safe_float(total_costs)
    
    return {
        'total_items': total_items_val,
        'total_costs': str(total_costs_val),
        'average_cost': str(total_costs_val / max(1, total_items_val)),
        'min_cost': str(safe_float(min_cost)),
        'max_cost': str(safe_float(max_cost)),
        'currencies_used': int(currencies_count or 0),
        'unique_types': int(types_count or 0)
    }

def create_overall_summary_dict(total_items, total_costs, min_cost, max_cost, currencies_count, types_count, categories_count):
    """Create a standardized overall summary dictionary with categories count"""
    total_items_val = int(total_items or 0)
    total_costs_val = safe_float(total_costs)
    
    return {
        'total_items': total_items_val,
        'total_costs': str(total_costs_val),
        'average_cost': str(total_costs_val / max(1, total_items_val)),
        'min_cost': str(safe_float(min_cost)),
        'max_cost': str(safe_float(max_cost)),
        'currencies_used': int(currencies_count or 0),
        'cost_categories_count': int(categories_count or 0),
        'unique_types': int(types_count or 0)
    }

# API Endpoints

# Get available customer job orders
@router.get("/customer-job-orders", response_model=List[CustomerJobOrder])
async def get_available_customer_job_orders(
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get all available customer job orders for cost assignment"""
    try:
        results = await get_customer_job_orders()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Create cost item endpoints for each table


@router.post("/{cost_type}", response_model=CostItemResponse)
async def create_cost(
    cost_type: str,
    item: CostItemCreate,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create a new cost item"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    try:
        result = await create_cost_item(COST_TABLES[cost_type], item)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create cost item")
        
        return format_cost_item_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Get cost items with simplified filters
@router.get("/{cost_type}", response_model=Dict[str, Any])
async def get_costs(
    cost_type: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    type_filter: Optional[str] = Query(None, alias="type"),
    currency: Optional[str] = None,
    min_cost: Optional[Decimal] = None,
    max_cost: Optional[Decimal] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get cost items with optional filters"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    try:
        filters = CostItemFilter(
            start_date=start_date,
            end_date=end_date,
            type=type_filter,
            currency=currency,
            min_cost=min_cost,
            max_cost=max_cost
        )
        
        results, total_count = await get_cost_items_with_filters(COST_TABLES[cost_type], filters, skip, limit)
        
        return {
            "items": [format_cost_item_response(row) for row in results],
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# You'll also need to update your CostItemCreate and CostItemFilter models:

@router.post("/reports/comprehensive", response_model=Dict[str, Any])
async def generate_comprehensive_cost_report(
    request: CostReportRequest,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Generate comprehensive cost report with analytics and insights"""
    
    # Validate cost types
    if request.cost_types:
        invalid_types = [ct for ct in request.cost_types if ct not in COST_TABLES]
        if invalid_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid cost types: {invalid_types}. Must be one of: {list(COST_TABLES.keys())}"
            )
    else:
        request.cost_types = list(COST_TABLES.keys())
    
    # Calculate period dates
    start_date, end_date = get_period_dates(request.period, request.start_date, request.end_date)
    
    conn = await connect_to_db()
    try:
        # Build base query conditions
        where_conditions = ["submission_date >= $1", "submission_date <= $2"]
        base_values = [start_date, end_date]
        param_count = 3
        
        if request.currency:
            where_conditions.append(f"currency = ${param_count}")
            base_values.append(request.currency)
            param_count += 1
        
        if request.cost_type_filter:
            where_conditions.append(f"type = ${param_count}")
            base_values.append(request.cost_type_filter)
            param_count += 1
        
        if request.min_cost:
            where_conditions.append(f"cost >= ${param_count}")
            base_values.append(request.min_cost)
            param_count += 1
        
        if request.max_cost:
            where_conditions.append(f"cost <= ${param_count}")
            base_values.append(request.max_cost)
            param_count += 1
        
        where_clause = " AND ".join(where_conditions)
        
        # Process each cost type
        cost_type_details = {}
        all_data = []
        summary_totals = {
            'total_items': 0,
            'total_costs': Decimal('0'),
            'min_cost': None,
            'max_cost': None,
            'currencies': set(),
            'types': set()
        }
        
        for cost_type in request.cost_types:
            table_name = COST_TABLES[cost_type]
            
            # Get data for this cost type
            query = f"""
            SELECT 
                id, title, cost, currency, quantity, type, 
                submission_date, dynamic_fields, created_at, updated_at
            FROM {table_name}
            WHERE {where_clause}
            ORDER BY submission_date DESC, created_at DESC
            """
            
            results = await conn.fetch(query, *base_values)
            
            # Process results for this cost type
            cost_type_items = []
            cost_type_summary = {
                'total_items': 0,
                'total_costs': Decimal('0'),
                'min_cost': None,
                'max_cost': None,
                'currencies': set(),
                'types': set()
            }
            
            for row in results:
                item_data = {
                    'cost_category': cost_type,
                    'id': row['id'],
                    'title': row['title'],
                    'cost': row['cost'],
                    'currency': row['currency'],
                    'quantity': row['quantity'],
                    'type': row['type'],
                    'submission_date': row['submission_date'],
                    'dynamic_fields': json.loads(row['dynamic_fields']) if row['dynamic_fields'] else {},
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
                
                cost_type_items.append(item_data)
                all_data.append(item_data)
                
                # Update cost type summary
                cost_type_summary['total_items'] += 1
                cost_type_summary['total_costs'] += row['cost']
                cost_type_summary['currencies'].add(row['currency'])
                if row['type']:
                    cost_type_summary['types'].add(row['type'])
                
                if cost_type_summary['min_cost'] is None or row['cost'] < cost_type_summary['min_cost']:
                    cost_type_summary['min_cost'] = row['cost']
                if cost_type_summary['max_cost'] is None or row['cost'] > cost_type_summary['max_cost']:
                    cost_type_summary['max_cost'] = row['cost']
                
                # Update overall summary
                summary_totals['total_items'] += 1
                summary_totals['total_costs'] += row['cost']
                summary_totals['currencies'].add(row['currency'])
                if row['type']:
                    summary_totals['types'].add(row['type'])
                
                if summary_totals['min_cost'] is None or row['cost'] < summary_totals['min_cost']:
                    summary_totals['min_cost'] = row['cost']
                if summary_totals['max_cost'] is None or row['cost'] > summary_totals['max_cost']:
                    summary_totals['max_cost'] = row['cost']
            
            # Generate breakdowns for this cost type
            type_breakdown = {}
            currency_breakdown = {}
            
            for item in cost_type_items:
                # Type breakdown
                item_type = item['type'] or 'Unspecified'
                if item_type not in type_breakdown:
                    type_breakdown[item_type] = {'count': 0, 'total': Decimal('0')}
                type_breakdown[item_type]['count'] += 1
                type_breakdown[item_type]['total'] += item['cost']
                
                # Currency breakdown
                currency = item['currency']
                if currency not in currency_breakdown:
                    currency_breakdown[currency] = {'count': 0, 'total': Decimal('0')}
                currency_breakdown[currency]['count'] += 1
                currency_breakdown[currency]['total'] += item['cost']
            
            # Create cost type detail
             # Create cost type detail
            cost_type_details[cost_type] = {
                'cost_type': cost_type,
                'summary': create_summary_dict(
                    cost_type_summary['total_items'],
                    cost_type_summary['total_costs'], 
                    cost_type_summary['min_cost'],
                    cost_type_summary['max_cost'],
                    len(cost_type_summary['currencies']),
                    len(cost_type_summary['types'])
                ),
                'type_breakdown': [
                    create_breakdown_item(
                        type_name, 
                        data['count'], 
                        data['total'], 
                        cost_type_summary['total_costs']
                    )
                    for type_name, data in sorted(type_breakdown.items(), key=lambda x: safe_float(x[1]['total']), reverse=True)
                ],
                'currency_breakdown': [
                    create_breakdown_item(
                        currency,
                        data['count'],
                        data['total'],
                        cost_type_summary['total_costs']
                    )
                    for currency, data in sorted(currency_breakdown.items(), key=lambda x: safe_float(x[1]['total']), reverse=True)
                ],
               'items': [
                    {
                        'id': item['id'],
                        'title': item['title'],
                        'cost': str(safe_float(item['cost'])),
                        'currency': item['currency'],
                        'quantity': str(item['quantity']) if item['quantity'] else None,
                        'type': item['type'],
                        'submission_date': item['submission_date'].isoformat(),
                        'dynamic_fields': item['dynamic_fields'],
                        'created_at': item['created_at'].isoformat(),
                        'updated_at': item['updated_at'].isoformat()
                    }
                    for item in cost_type_items
                ]
            }
        
        # Create overall summary
        overall_summary = create_overall_summary_dict(
            summary_totals['total_items'],
            summary_totals['total_costs'],
            summary_totals['min_cost'], 
            summary_totals['max_cost'],
            len(summary_totals['currencies']),
            len(summary_totals['types']),
            len(request.cost_types)
        )
        # Generate overall cost type breakdown
        cost_type_breakdown = {}
        for cost_type, details in cost_type_details.items():
            cost_type_breakdown[cost_type] = {
                'total_cost': Decimal(details['summary']['total_costs']),
                'count': details['summary']['total_items']
            }
        
        overall_cost_type_breakdown = [
            create_breakdown_item(
                cost_type,
                data['count'],
                data['total_cost'],
                summary_totals['total_costs']
            )
            for cost_type, data in sorted(cost_type_breakdown.items(), key=lambda x: safe_float(x[1]['total_cost']), reverse=True)
        ]
        
        # Generate trends if requested
        trends = []
        if request.include_trends:
            trend_periods = get_trend_periods(request.period, start_date, end_date)
            
            for period_info in trend_periods:
                period_total = Decimal('0')
                period_count = 0
                
                for item in all_data:
                    item_date = item['submission_date']
                    if period_info['start'] <= item_date <= period_info['end']:
                        period_total += item['cost']
                        period_count += 1
                
                trends.append({
                    'period_label': period_info['label'],
                    'period_start': period_info['start'].isoformat(),
                    'period_end': period_info['end'].isoformat(),
                    'total_cost': str(safe_float(period_total)),
                    'item_count': period_count,
                    'average_cost': str(safe_float(period_total) / max(1, period_count))
                })
        
        # Generate insights
        insights = await generate_cost_insights(
            CostSummary(
                total_items=summary_totals['total_items'],
                total_costs=summary_totals['total_costs'],
                average_cost=Decimal(str(safe_float(summary_totals['total_costs']) / max(1, summary_totals['total_items']))),
                min_cost=summary_totals['min_cost'] or Decimal('0'),
                max_cost=summary_totals['max_cost'] or Decimal('0'),
                currencies_used=len(summary_totals['currencies']),
                cost_categories_count=len(request.cost_types),
                unique_types=len(summary_totals['types'])
            ),
            {k: {'total_cost': safe_float(v['total_cost'])} for k, v in cost_type_breakdown.items()},
            [TrendData(
                period_label=t['period_label'],
                period_start=datetime.fromisoformat(t['period_start']).date(),
                period_end=datetime.fromisoformat(t['period_end']).date(),
                total_cost=Decimal(str(safe_float(t['total_cost']))),
                item_count=t['item_count'],
                average_cost=Decimal(str(safe_float(t['average_cost'])))
            ) for t in trends] if trends else None
        )
        
        # Prepare response
        response = {
            "report_metadata": {
                "period": request.period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "cost_types_included": request.cost_types,
                "filters_applied": {
                    "currency": request.currency,
                    "cost_type_filter": request.cost_type_filter,
                    "min_cost": str(request.min_cost) if request.min_cost else None,
                    "max_cost": str(request.max_cost) if request.max_cost else None
                },
                "generated_at": datetime.now().isoformat(),
                "total_records_analyzed": len(all_data)
            },
            "overall_summary": overall_summary,
            "cost_type_breakdown": overall_cost_type_breakdown,
            "cost_type_details": cost_type_details,
            "trends": trends if request.include_trends else None,
            "insights": insights
        }
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation error: {str(e)}")
    finally:
        await conn.close()

# Quick report endpoints for common periods
# REPLACE the generate_quick_report endpoint (around line 1050) with this:

@router.get("/reports/quick/{period}")
async def generate_quick_report(
    period: ReportPeriod,
    cost_types: Optional[str] = Query(None, description="Comma-separated cost types"),
    currency: Optional[str] = None,
    start_date: Optional[date] = Query(None, description="Start date for custom period"),
    end_date: Optional[date] = Query(None, description="End date for custom period"),
    current_user: TokenData = Depends(admin_or_manager)
):
    """Generate quick reports for common periods"""
    
    # Validate custom period dates
    if period == ReportPeriod.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400, 
                detail="Custom period requires both start_date and end_date parameters"
            )
    
    cost_types_list = cost_types.split(',') if cost_types else None
    
    request = CostReportRequest(
        period=period,
        start_date=start_date,
        end_date=end_date,
        cost_types=cost_types_list,
        currency=currency,
        include_breakdown=True,
        include_trends=period in [ReportPeriod.MONTHLY, ReportPeriod.WEEKLY]
    )
    
    return await generate_comprehensive_cost_report(request, current_user)
@router.get("/reports/cost-type/{cost_type}")
async def get_cost_type_report(
    cost_type: str,
    period: ReportPeriod = ReportPeriod.MONTHLY,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    currency: Optional[str] = None,
    type_filter: Optional[str] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get detailed report for a specific cost type"""
    
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    request = CostReportRequest(
        period=period,
        start_date=start_date,
        end_date=end_date,
        cost_types=[cost_type],
        currency=currency,
        cost_type_filter=type_filter,
        include_breakdown=True,
        include_trends=True
    )
    
    return await generate_comprehensive_cost_report(request, current_user)


# Get single cost item
@router.get("/{cost_type}/{item_id}", response_model=CostItemResponse)
async def get_cost_by_id(
    cost_type: str,
    item_id: int,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get a single cost item by ID"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    try:
        result = await get_cost_item_by_id(COST_TABLES[cost_type], item_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cost item not found")
        
        return format_cost_item_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Update cost item
@router.put("/{cost_type}/{item_id}", response_model=CostItemResponse)
async def update_cost(
    cost_type: str,
    item_id: int,
    item: CostItemUpdate,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Update an existing cost item"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    try:
        # Check if item exists
        existing_item = await get_cost_item_by_id(COST_TABLES[cost_type], item_id)
        if not existing_item:
            raise HTTPException(status_code=404, detail="Cost item not found")
        
        result = await update_cost_item(COST_TABLES[cost_type], item_id, item)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to update cost item")
        
        return format_cost_item_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Delete cost item
@router.delete("/{cost_type}/{item_id}")
async def delete_cost(
    cost_type: str,
    item_id: int,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Delete a cost item"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    try:
        result = await delete_cost_item(COST_TABLES[cost_type], item_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cost item not found")
        
        return {"message": "Cost item deleted successfully", "id": result['id']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Bulk operations
@router.post("/{cost_type}/bulk", response_model=List[CostItemResponse])
async def create_bulk_costs(
    cost_type: str,
    items: List[CostItemCreate],
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create multiple cost items at once"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    if len(items) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 items allowed per bulk operation")
    
    results = []
    errors = []
    
    for i, item in enumerate(items):
        try:
            result = await create_cost_item(COST_TABLES[cost_type], item)
            if result:
                results.append(format_cost_item_response(result))
        except Exception as e:
            errors.append(f"Item {i}: {str(e)}")
    
    if errors and not results:
        raise HTTPException(status_code=500, detail=f"All items failed: {'; '.join(errors)}")
    
    response = {"created": results}
    if errors:
        response["errors"] = errors
    
    return JSONResponse(content=response)

# Get costs by client
@router.get("/client/{client_name}/costs", response_model=Dict[str, Any])
async def get_costs_by_client(
    client_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    cost_type: Optional[str] = Query(None, description="Filter by specific cost type"),
    job_order_id: Optional[int] = Query(None, description="Filter by specific job order"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get all costs for a specific client"""
    conn = await connect_to_db()
    try:
        where_conditions = ["LOWER(client_name) = LOWER($1)"]
        values = [client_name]
        param_count = 2
        
        if job_order_id:
            where_conditions.append(f"job_order_id = ${param_count}")
            values.append(job_order_id)
            param_count += 1
        
        if start_date:
            where_conditions.append(f"date_time >= ${param_count}")
            values.append(start_date)
            param_count += 1
        
        if end_date:
            where_conditions.append(f"date_time <= ${param_count}")
            values.append(end_date)
            param_count += 1
        
        if cost_type and cost_type.lower().replace('_', ' ') in ['raw materials', 'operational', 'general', 'depreciation', 'unexpected']:
            cost_category_filter = cost_type.lower().replace('_', ' ').title()
            where_conditions.append(f"cost_category = ${param_count}")
            values.append(cost_category_filter)
            param_count += 1
        
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
        SELECT cost_category, id, title, costs, currency, quantity, type, 
               client_name, job_order_id, date_time, dynamic_fields, created_at, updated_at
        FROM all_factory_costs
        WHERE {where_clause}
        ORDER BY date_time DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        values.extend([limit, skip])
        results = await conn.fetch(query, *values)
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM all_factory_costs WHERE {where_clause}"
        total_count = await conn.fetchval(count_query, *values[:-2])
        
        return {
            "client_name": client_name,
            "items": [
                {
                    "cost_category": row['cost_category'],
                    "id": row['id'],
                    "title": row['title'],
                    "costs": str(row['costs']),
                    "currency": row['currency'],
                    "quantity": str(row['quantity']) if row['quantity'] else None,
                    "type": row['type'],
                    "client_name": row['client_name'],
                    "job_order_id": row['job_order_id'],
                    "date_time": row['date_time'].isoformat(),
                    "dynamic_fields": json.loads(row['dynamic_fields']) if row['dynamic_fields'] else {},
                    "created_at": row['created_at'].isoformat(),
                    "updated_at": row['updated_at'].isoformat()
                } for row in results
            ],
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        await conn.close()

# Get costs by job order
@router.get("/job-order/{job_order_id}/costs", response_model=Dict[str, Any])
async def get_costs_by_job_order(
    job_order_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    cost_type: Optional[str] = Query(None, description="Filter by specific cost type"),
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get all costs for a specific job order"""
    conn = await connect_to_db()
    try:
        where_conditions = ["job_order_id = $1"]
        values = [job_order_id]
        param_count = 2
        
        if cost_type and cost_type.lower().replace('_', ' ') in ['raw materials', 'operational', 'general', 'depreciation', 'unexpected']:
            cost_category_filter = cost_type.lower().replace('_', ' ').title()
            where_conditions.append(f"cost_category = ${param_count}")
            values.append(cost_category_filter)
            param_count += 1
        
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
        SELECT cost_category, id, title, costs, currency, quantity, type, 
               client_name, job_order_id, date_time, dynamic_fields, created_at, updated_at
        FROM all_factory_costs
        WHERE {where_clause}
        ORDER BY date_time DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        values.extend([limit, skip])
        results = await conn.fetch(query, *values)
        
        # Get total count and client info
        count_query = f"SELECT COUNT(*) FROM all_factory_costs WHERE {where_clause}"
        total_count = await conn.fetchval(count_query, *values[:-2])
        
        # Get client name
        client_query = "SELECT DISTINCT client_name FROM all_factory_costs WHERE job_order_id = $1 LIMIT 1"
        client_result = await conn.fetchval(client_query, job_order_id)
        
        return {
            "job_order_id": job_order_id,
            "client_name": client_result,
            "items": [
                {
                    "cost_category": row['cost_category'],
                    "id": row['id'],
                    "title": row['title'],
                    "costs": str(row['costs']),
                    "currency": row['currency'],
                    "quantity": str(row['quantity']) if row['quantity'] else None,
                    "type": row['type'],
                    "client_name": row['client_name'],
                    "job_order_id": row['job_order_id'],
                    "date_time": row['date_time'].isoformat(),
                    "dynamic_fields": json.loads(row['dynamic_fields']) if row['dynamic_fields'] else {},
                    "created_at": row['created_at'].isoformat(),
                    "updated_at": row['updated_at'].isoformat()
                } for row in results
            ],
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        await conn.close()

# Analytics endpoints
@router.get("/{cost_type}/analytics/summary")
async def get_cost_summary(
    cost_type: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    client_name: Optional[str] = None,
    job_order_id: Optional[int] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get cost summary analytics"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    conn = await connect_to_db()
    try:
        where_conditions = []
        values = []
        param_count = 1
        
        if start_date:
            where_conditions.append(f"date_time >= ${param_count}")
            values.append(start_date)
            param_count += 1
        
        if end_date:
            where_conditions.append(f"date_time <= ${param_count}")
            values.append(end_date)
            param_count += 1
        
        if client_name:
            where_conditions.append(f"LOWER(client_name) = LOWER(${param_count})")
            values.append(client_name)
            param_count += 1
        
        if job_order_id:
            where_conditions.append(f"job_order_id = ${param_count}")
            values.append(job_order_id)
            param_count += 1
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            COUNT(*) as total_items,
            SUM(costs) as total_costs,
            AVG(costs) as average_cost,
            MIN(costs) as min_cost,
            MAX(costs) as max_cost,
            COUNT(DISTINCT currency) as currencies_used,
            COUNT(DISTINCT type) as types_used,
            COUNT(DISTINCT client_name) as clients_count,
            COUNT(DISTINCT job_order_id) as job_orders_count
        FROM {COST_TABLES[cost_type]} 
        WHERE {where_clause}
        """
        
        result = await conn.fetchrow(query, *values)
        
        # Get breakdown by type
        type_query = f"""
        SELECT type, COUNT(*) as count, SUM(costs) as total_cost
        FROM {COST_TABLES[cost_type]} 
        WHERE {where_clause} AND type IS NOT NULL
        GROUP BY type
        ORDER BY total_cost DESC
        """
        
        type_breakdown = await conn.fetch(type_query, *values)
        
        # Get breakdown by client
        client_query = f"""
        SELECT client_name, COUNT(*) as count, SUM(costs) as total_cost
        FROM {COST_TABLES[cost_type]} 
        WHERE {where_clause}
        GROUP BY client_name
        ORDER BY total_cost DESC
        """
        
        client_breakdown = await conn.fetch(client_query, *values)
        
        return {
            "summary": {
                "total_items": result['total_items'],
                "total_costs": str(safe_float(result['total_costs'])),
                "average_cost": str(safe_float(result['average_cost'])),
                "min_cost": str(safe_float(result['min_cost'])),
                "max_cost": str(safe_float(result['max_cost'])),
                "currencies_used": result['currencies_used'],
                "types_used": result['types_used'],
                "clients_count": result['clients_count'],
                "job_orders_count": result['job_orders_count']
            },
            "type_breakdown": [
                {
                    "type": row['type'],
                    "count": row['count'],
                    "total_cost": str(safe_float(row['total_cost']))
                } for row in type_breakdown
            ],
            "client_breakdown": [
                {
                    "client_name": row['client_name'],
                    "count": row['count'],
                    "total_cost": str(safe_float(row['total_cost']))
                } for row in client_breakdown
            ]
        }
    finally:
        await conn.close()

# Get cost summary by client and job order
@router.get("/analytics/client-job-order-summary")
async def get_client_job_order_cost_summary(
    client_name: Optional[str] = None,
    job_order_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get cost summary grouped by client and job order"""
    conn = await connect_to_db()
    try:
        where_conditions = []
        values = []
        param_count = 1
        
        if client_name:
            where_conditions.append(f"LOWER(client_name) = LOWER(${param_count})")
            values.append(client_name)
            param_count += 1
        
        if job_order_id:
            where_conditions.append(f"job_order_id = ${param_count}")
            values.append(job_order_id)
            param_count += 1
        
        if start_date:
            where_conditions.append(f"first_cost_date >= ${param_count}")
            values.append(start_date)
            param_count += 1
        
        if end_date:
            where_conditions.append(f"last_cost_date <= ${param_count}")
            values.append(end_date)
            param_count += 1
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT * FROM total_costs_by_client_order
        WHERE {where_clause}
        ORDER BY total_costs DESC
        """
        
        results = await conn.fetch(query, *values)
        
        return {
            "cost_summary": [
                {
                    "client_name": row['client_name'],
                    "job_order_id": row['job_order_id'],
                    "total_items": row['total_items'],
                    "total_costs": str(row['total_costs']),
                    "raw_materials_total": str(row['raw_materials_total']),
                    "operational_total": str(row['operational_total']),
                    "general_total": str(row['general_total']),
                    "depreciation_total": str(row['depreciation_total']),
                    "unexpected_total": str(row['unexpected_total']),
                    "first_cost_date": row['first_cost_date'].isoformat() if row['first_cost_date'] else None,
                    "last_cost_date": row['last_cost_date'].isoformat() if row['last_cost_date'] else None
                } for row in results
            ]
        }
    finally:
        await conn.close()

# Get all cost types summary with client and job order details
@router.get("/analytics/all-costs-summary")
async def get_all_costs_summary(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    client_name: Optional[str] = None,
    job_order_id: Optional[int] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Get summary of all cost types with client and job order details"""
    conn = await connect_to_db()
    try:
        where_conditions = []
        values = []
        param_count = 1
        
        if start_date:
            where_conditions.append(f"date_time >= ${param_count}")
            values.append(start_date)
            param_count += 1
        
        if end_date:
            where_conditions.append(f"date_time <= ${param_count}")
            values.append(end_date)
            param_count += 1
        
        if client_name:
            where_conditions.append(f"LOWER(client_name) = LOWER(${param_count})")
            values.append(client_name)
            param_count += 1
        
        if job_order_id:
            where_conditions.append(f"job_order_id = ${param_count}")
            values.append(job_order_id)
            param_count += 1
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
        SELECT 
            cost_category,
            COUNT(*) as total_items,
            SUM(costs) as total_costs,
            AVG(costs) as average_cost,
            COUNT(DISTINCT client_name) as clients_count,
            COUNT(DISTINCT job_order_id) as job_orders_count
        FROM all_factory_costs
        WHERE {where_clause}
        GROUP BY cost_category
        ORDER BY total_costs DESC
        """
        
        results = await conn.fetch(query, *values)
        
        # Get grand totals
        total_query = f"""
        SELECT 
            COUNT(*) as grand_total_items,
            SUM(costs) as grand_total_costs,
            AVG(costs) as grand_average_cost,
            COUNT(DISTINCT client_name) as total_clients,
            COUNT(DISTINCT job_order_id) as total_job_orders
        FROM all_factory_costs
        WHERE {where_clause}
        """
        
        grand_total = await conn.fetchrow(total_query, *values)
        
        return {
            "cost_categories": [
                {
                    "category": row['cost_category'],
                    "total_items": row['total_items'],
                    "total_costs": str(row['total_costs']),
                    "average_cost": str(row['average_cost']),
                    "clients_count": row['clients_count'],
                    "job_orders_count": row['job_orders_count']
                } for row in results
            ],
            "grand_totals": {
                "total_items": grand_total['grand_total_items'],
                "total_costs": str(grand_total['grand_total_costs']) if grand_total['grand_total_costs'] else "0",
                "average_cost": str(grand_total['grand_average_cost']) if grand_total['grand_average_cost'] else "0",
                "total_clients": grand_total['total_clients'],
                "total_job_orders": grand_total['total_job_orders']
            }
        }
    finally:
        await conn.close()

# Export data with client and job order information
@router.get("/{cost_type}/export")
async def export_costs(
    cost_type: str,
    format: str = Query("json", regex="^(json|csv)$"),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    client_name: Optional[str] = None,
    job_order_id: Optional[int] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Export cost data in JSON or CSV format with client and job order details"""
    if cost_type not in COST_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid cost type. Must be one of: {list(COST_TABLES.keys())}")
    
    try:
        filters = CostItemFilter(
            start_date=start_date, 
            end_date=end_date,
            client_name=client_name,
            job_order_id=job_order_id
        )
        results, _ = await get_cost_items_with_filters(COST_TABLES[cost_type], filters, 0, 10000)
        
        data = [format_cost_item_response(row) for row in results]
        
        if format == "json":
            return JSONResponse(content={"data": [item.dict() for item in data]})
        
        # CSV format
        import csv
        import io
        
        output = io.StringIO()
        if data:
            fieldnames = ['id', 'title', 'costs', 'currency', 'quantity', 'type', 'client_name', 'job_order_id', 'date_time', 'dynamic_fields', 'created_at', 'updated_at']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in data:
                row = item.dict()
                row['dynamic_fields'] = json.dumps(row['dynamic_fields'])
                writer.writerow(row)
        
        response = Response(content=output.getvalue(), media_type="text/csv")
        response.headers["Content-Disposition"] = f"attachment; filename={cost_type}_costs_export.csv"
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export error: {str(e)}")


