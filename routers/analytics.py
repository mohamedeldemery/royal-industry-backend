# backend/routers/analytics.py
from fastapi import APIRouter, HTTPException, Depends
import asyncpg
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# your old auth guard
from routers.employees import admin_or_manager, TokenData

DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ────────────────────────────────────────────────
#  Simple in-memory cache with 15 s TTL
# ────────────────────────────────────────────────
_cache: Dict[str, Dict[str, Any]] = {}
_TTL = timedelta(seconds=15)

async def _get_cached(key: str, fetch_fn):
    now = datetime.utcnow()
    entry = _cache.get(key)
    if entry and (now - entry["ts"] < _TTL):
        return entry["val"]
    val = await fetch_fn()
    _cache[key] = {"val": val, "ts": now}
    return val


# ────────────────────────────────────────────────
# 1) Your existing KPI endpoint with caching
# ────────────────────────────────────────────────
@router.get("/inventory/kpi", dependencies=[Depends(admin_or_manager)])
async def inv_kpi():
    async def _fetch():
        q = """
          SELECT material_type,
                 SUM(weight)          AS on_hand_kg,
                 MIN((weight/NULLIF(quantity,0))) AS kg_per_batch,
                 SUM(quantity)        AS batches,
                 ROUND(AVG(density)::numeric, 2) AS avg_density
          FROM inventory
          WHERE status = 'available'
          GROUP BY material_type
        """
        conn = await connect_to_db()
        rows = await conn.fetch(q)
        await conn.close()
        return [dict(r) for r in rows]
        
    return await _get_cached("inv_kpi", _fetch)

# ────────────────────────────────────────────────
# 2) Your existing aging view with caching
# ────────────────────────────────────────────────
@router.get("/inventory/aging", dependencies=[Depends(admin_or_manager)])
async def inv_age():
    async def _fetch():
        conn = await connect_to_db()
        rows = await conn.fetch("SELECT * FROM v_inv_aging")
        await conn.close()
        return [dict(r) for r in rows]
        
    return await _get_cached("inv_aging", _fetch)


# ────────────────────────────────────────────────
# 3) Flow daily with adaptation for your schema
# ────────────────────────────────────────────────
@router.get("/inventory/flow_daily", dependencies=[Depends(admin_or_manager)])
async def inv_flow_daily():
    async def _fetch():
        conn = await connect_to_db()
        
        # Check if materialized view exists, if not create it based on inventory status changes
        view_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM pg_matviews WHERE matviewname = 'mv_inv_flow_daily')"
        )
        
        if not view_exists:
            # Create a version of the view adapted to your schema
            await conn.execute("""
                CREATE MATERIALIZED VIEW mv_inv_flow_daily AS
                WITH movements AS (
                    /*  all incoming weight  */
                    SELECT
                        received_date::date         AS day,
                        weight                      AS qty          -- positive
                    FROM inventory
                    WHERE received_date IS NOT NULL

                    UNION ALL

                    /*  all outgoing weight (negative)  */
                    SELECT
                        j.start_time::date          AS day,
                        -i.weight                   AS qty          -- negative
                    FROM inventory i
                    JOIN job_orders j ON i.job_order_id = j.id
                    WHERE i.status = 'used' AND j.start_time IS NOT NULL
                )

                SELECT
                    day,
                    SUM(CASE WHEN qty > 0 THEN qty ELSE 0 END) AS total_receipts,
                    SUM(CASE WHEN qty < 0 THEN -qty ELSE 0 END) AS total_withdrawals
                FROM movements
                GROUP BY day
                ORDER BY day;
            """)
        
        rows = await conn.fetch("SELECT * FROM mv_inv_flow_daily ORDER BY day")
        await conn.close()
        return [dict(r) for r in rows]
        
    return await _get_cached("inv_flow_daily", _fetch)


# ────────────────────────────────────────────────
# 4) Stock balances endpoint (with improved caching)
# ────────────────────────────────────────────────
@router.get("/inventory/stock", dependencies=[Depends(admin_or_manager)])
async def inv_stock():
    async def _fetch():
        q = """
            SELECT category, material_type, 
                   SUM(weight) as total_weight, 
                   COUNT(*) as total_quantity
            FROM inventory
            WHERE status = 'available'
            GROUP BY category, material_type
            ORDER BY category, material_type
        """
        conn = await connect_to_db()
        rows = await conn.fetch(q)
        await conn.close()
        return [dict(r) for r in rows]

    return await _get_cached("inv_stock", _fetch)


# ────────────────────────────────────────────────
# 5) Daily inventory flow with date range
# ────────────────────────────────────────────────
@router.get("/inventory/flow", dependencies=[Depends(admin_or_manager)])
async def inv_flow(days: int = 30):
    async def _fetch():
        q = """
            SELECT day, total_receipts, total_withdrawals
            FROM mv_inv_flow_daily
            WHERE day >= CURRENT_DATE - $1::int
            ORDER BY day
        """
        conn = await connect_to_db()
        rows = await conn.fetch(q, days)
        await conn.close()
        return [dict(r) for r in rows]

    return await _get_cached(f"inv_flow_{days}", _fetch)


# ────────────────────────────────────────────────
# 6) NEW: Forecasting endpoint adapted to your schema
# ────────────────────────────────────────────────
class ForecastResponse(BaseModel):
    material_type: str
    current_stock: float
    forecasted_usage: float
    days_until_stockout: int
    reorder_recommendation: bool

@router.get("/inventory/forecast", dependencies=[Depends(admin_or_manager)], response_model=List[ForecastResponse])
async def inv_forecast(days: int = 30):
    """Forecasts inventory levels based on historical usage patterns"""
    conn = await connect_to_db()
    try:
        # Get current stock
        current_stock = await conn.fetch("""
            SELECT material_type, SUM(weight)::numeric as current_stock
            FROM inventory 
            WHERE status = 'available'
            GROUP BY material_type
        """)
        
        # Get usage data for last 90 days to calculate average daily usage
        usage_data = await conn.fetch("""
            SELECT 
                i.material_type, 
                SUM(i.weight)::numeric as total_usage,
                GREATEST(1, (CURRENT_DATE - MIN(j.start_time::date)))::numeric as days_period
            FROM inventory i
            JOIN job_orders j ON i.job_order_id = j.id
            WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 90
            GROUP BY i.material_type
        """)
        
        # Calculate forecast
        forecast_results = []
        for stock in current_stock:
            material = stock['material_type']
            current = float(stock['current_stock']) if stock['current_stock'] is not None else 0.0
            
            # Find usage rate for this material
            usage_rate = 0.0
            for usage in usage_data:
                if usage['material_type'] == material:
                    days = float(usage['days_period'])
                    usage_rate = float(usage['total_usage']) / days
                    break
            
            # Calculate forecast
            forecasted_usage = usage_rate * float(days)
            
            # Calculate days until stockout (avoid division by zero)
            if usage_rate > 0.001:
                days_until_stockout = int(current / usage_rate)
            else:
                days_until_stockout = 9999  # Very large number to indicate essentially "never"
            
            # Determine if reorder is recommended (if stock will last less than 30 days)
            reorder_recommendation = days_until_stockout < 30
            
            forecast_results.append({
                "material_type": material,
                "current_stock": current,
                "forecasted_usage": forecasted_usage,
                "days_until_stockout": days_until_stockout,
                "reorder_recommendation": reorder_recommendation
            })
        
        return forecast_results
    finally:
        await conn.close()


# # ────────────────────────────────────────────────
# # 7) NEW: Reorder Points Analysis
# # ────────────────────────────────────────────────
# @router.get("/inventory/reorder_points", dependencies=[Depends(admin_or_manager)])
# async def inv_reorder_points():
#     """Calculates reorder points for materials based on usage patterns and lead times"""
#     conn = await connect_to_db()
#     try:
#         # Adapted to use your schema with inventory and job_orders
#         result = await conn.fetch("""
#             WITH usage_stats AS (
#                 SELECT 
#                     i.material_type,
#                     SUM(i.weight)::numeric as total_used,
#                     COUNT(DISTINCT DATE(j.start_time)) as active_days,
#                     (CURRENT_DATE - MIN(j.start_time::date)) as days_span
#                 FROM inventory i
#                 JOIN job_orders j ON i.job_order_id = j.id
#                 WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 180
#                 GROUP BY i.material_type
#             ),
#             lead_times AS (
#                 SELECT 
#                     supplier,
#                     AVG((received_date - order_date))::numeric as avg_lead_time_days
#                 FROM inventory
#                 WHERE order_date IS NOT NULL AND received_date IS NOT NULL
#                 GROUP BY supplier
#             ),
#             inventory_with_supplier AS (
#                 SELECT 
#                     i.material_type,
#                     i.supplier,
#                     SUM(i.weight)::numeric as current_stock
#                 FROM inventory i
#                 WHERE i.status = 'available'
#                 GROUP BY i.material_type, i.supplier
#             )
            
#             SELECT 
#                 i.material_type,
#                 i.current_stock,
#                 i.supplier,
#                 COALESCE(l.avg_lead_time_days, 14)::numeric as lead_time_days,
#                 COALESCE(u.total_used, 0)::numeric as total_usage_180d,
#                 COALESCE(u.active_days, 1)::numeric as active_days,
#                 COALESCE(u.total_used / GREATEST(u.active_days, 1)::numeric, 0)::numeric as daily_usage,
#                 COALESCE(u.total_used / GREATEST(u.active_days, 1)::numeric, 0)::numeric * 
#                     COALESCE(l.avg_lead_time_days, 14)::numeric as lead_time_demand,
#                 COALESCE(u.total_used / GREATEST(u.active_days, 1)::numeric, 0)::numeric * 
#                     COALESCE(l.avg_lead_time_days, 14)::numeric * 1.5 as reorder_point
#             FROM inventory_with_supplier i
#             LEFT JOIN usage_stats u ON i.material_type = u.material_type
#             LEFT JOIN lead_times l ON i.supplier = l.supplier
#         """)
        
#         return [dict(r) for r in result]
#     finally:
#         await conn.close()


# # ────────────────────────────────────────────────
# # 8) NEW: Seasonality Analysis
# # ────────────────────────────────────────────────
# @router.get("/inventory/seasonality", dependencies=[Depends(admin_or_manager)])
# async def inv_seasonality():
#     """Analyzes historical data to detect seasonal patterns in material usage"""
#     conn = await connect_to_db()
#     try:
#         # Adapted to use your schema with inventory and job_orders for used materials
#         result = await conn.fetch("""
#             WITH monthly_usage AS (
#                 SELECT 
#                     i.material_type,
#                     DATE_TRUNC('month', j.start_time) as month,
#                     SUM(i.weight) as monthly_usage
#                 FROM inventory i
#                 JOIN job_orders j ON i.job_order_id = j.id
#                 WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - INTERVAL '2 years'
#                 GROUP BY i.material_type, DATE_TRUNC('month', j.start_time)
#             ),
            
#             monthly_avg AS (
#                 SELECT 
#                     material_type,
#                     AVG(monthly_usage) as avg_monthly_usage
#                 FROM monthly_usage
#                 GROUP BY material_type
#             )
            
#             SELECT 
#                 m.material_type,
#                 TO_CHAR(m.month, 'YYYY-MM') as month,
#                 m.monthly_usage,
#                 a.avg_monthly_usage,
#                 CASE WHEN a.avg_monthly_usage > 0 
#                      THEN m.monthly_usage / a.avg_monthly_usage 
#                      ELSE 1 END as seasonality_factor
#             FROM monthly_usage m
#             JOIN monthly_avg a ON m.material_type = a.material_type
#             ORDER BY m.material_type, m.month
#         """)
        
#         return [dict(r) for r in result]
#     finally:
#         await conn.close()


# # ────────────────────────────────────────────────
# # 9) NEW: Risk Analysis
# # ────────────────────────────────────────────────
# @router.get("/inventory/risk_analysis", dependencies=[Depends(admin_or_manager)])
# async def inv_risk_analysis():
#     """Identifies high-risk inventory items (potential stockouts, aging stock)"""
#     conn = await connect_to_db()
#     try:
#         # Adapted to use your schema with inventory status and job_orders
#         result = await conn.fetch("""
#             WITH usage_rates AS (
#                 SELECT 
#                     i.material_type,
#                     SUM(i.weight) / GREATEST(EXTRACT(DAY FROM (CURRENT_DATE - MIN(j.start_time::date))), 1) as daily_usage
#                 FROM inventory i
#                 JOIN job_orders j ON i.job_order_id = j.id
#                 WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 90
#                 GROUP BY i.material_type
#             ),
            
#             inventory_age AS (
#                 SELECT 
#                     material_type,
#                     AVG(EXTRACT(DAY FROM (CURRENT_DATE - received_date))) as avg_age_days
#                 FROM inventory
#                 WHERE status = 'available'
#                 GROUP BY material_type
#             ),
            
#             current_stock AS (
#                 SELECT 
#                     material_type,
#                     SUM(weight) as total_weight
#                 FROM inventory
#                 WHERE status = 'available'
#                 GROUP BY material_type
#             )
            
#             SELECT 
#                 c.material_type,
#                 c.total_weight as current_stock,
#                 COALESCE(u.daily_usage, 0) as daily_usage,
#                 CASE 
#                     WHEN u.daily_usage > 0 THEN c.total_weight / u.daily_usage
#                     ELSE NULL
#                 END as days_of_supply,
#                 COALESCE(a.avg_age_days, 0) as avg_age_days,
                
#                 -- Stockout risk (0-1)
#                 CASE 
#                     WHEN u.daily_usage > 0 AND c.total_weight / u.daily_usage < 15 THEN 
#                         GREATEST(0, 1 - ((c.total_weight / u.daily_usage) / 15))
#                     ELSE 0
#                 END as stockout_risk,
                
#                 -- Aging risk (0-1)
#                 CASE 
#                     WHEN a.avg_age_days > 90 THEN 
#                         LEAST(1, (a.avg_age_days - 90) / 180)
#                     ELSE 0
#                 END as aging_risk,
                
#                 -- Overall risk score (0-10)
#                 CASE 
#                     WHEN u.daily_usage > 0 AND c.total_weight / u.daily_usage < 15 THEN 
#                         GREATEST(0, 1 - ((c.total_weight / u.daily_usage) / 15)) * 5
#                     ELSE 0
#                 END +
#                 CASE 
#                     WHEN a.avg_age_days > 90 THEN 
#                         LEAST(1, (a.avg_age_days - 90) / 180) * 5
#                     ELSE 0
#                 END as overall_risk_score
                
#             FROM current_stock c
#             LEFT JOIN usage_rates u ON c.material_type = u.material_type
#             LEFT JOIN inventory_age a ON c.material_type = a.material_type
#             ORDER BY overall_risk_score DESC
#         """)
        
#         return [dict(r) for r in result]
#     finally:
#         await conn.close()


# # ────────────────────────────────────────────────
# # 10) NEW: Cost Analysis
# # ────────────────────────────────────────────────
# @router.get("/inventory/cost_analysis", dependencies=[Depends(admin_or_manager)])
# async def inv_cost_analysis():
#     """Analyzes inventory carrying costs and cost reduction opportunities"""
#     conn = await connect_to_db()
#     try:
#         # Adapted to work with your schema - assumes cost_per_kg column exists or will be added
#         result = await conn.fetch("""
#             WITH inventory_valuation AS (
#                 SELECT 
#                     material_type,
#                     category,
#                     COUNT(*) as batch_count,
#                     SUM(weight) as total_weight,
#                     AVG(EXTRACT(DAY FROM (CURRENT_DATE - received_date))) as avg_age_days,
#                     -- Assume holding cost is 15% of inventory value annually
#                     -- and that we have a cost_per_kg column or can estimate it
#                     SUM(weight * COALESCE(cost_per_kg, 
#                         CASE 
#                             WHEN category = '1st Degree' THEN 5 -- Estimated cost if not available
#                             ELSE 3
#                         END)) as total_value,
#                     -- Calculate holding cost based on how long items have been held
#                     SUM(weight * COALESCE(cost_per_kg, 
#                         CASE 
#                             WHEN category = '1st Degree' THEN 5
#                             ELSE 3
#                         END) * 
#                         (EXTRACT(DAY FROM (CURRENT_DATE - received_date)) / 365) * 0.15) as holding_cost
#                 FROM inventory
#                 WHERE status = 'available'
#                 GROUP BY material_type, category
#             ),
            
#             -- Calculate material usage from your inventory schema
#             material_usage AS (
#                 SELECT 
#                     i.material_type,
#                     SUM(i.weight) as annual_usage
#                 FROM inventory i
#                 JOIN job_orders j ON i.job_order_id = j.id
#                 WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 365
#                 GROUP BY i.material_type
#             )
            
#             SELECT 
#                 iv.material_type,
#                 iv.category,
#                 iv.batch_count,
#                 iv.total_weight,
#                 iv.avg_age_days,
#                 iv.total_value,
#                 iv.holding_cost,
#                 -- Opportunity metrics
#                 CASE 
#                     WHEN iv.avg_age_days > 180 THEN iv.holding_cost * 0.8
#                     WHEN iv.avg_age_days > 90 THEN iv.holding_cost * 0.4
#                     ELSE 0
#                 END as potential_savings,
#                 -- EOQ recommendation (if you have order cost data)
#                 SQRT((2 * 100 * COALESCE(mu.annual_usage, 1)) / 
#                      (0.15 * CASE WHEN iv.total_value > 0 AND iv.total_weight > 0 
#                              THEN iv.total_value/iv.total_weight ELSE 1 END)
#                 ) as economic_order_qty
#             FROM inventory_valuation iv
#             LEFT JOIN material_usage mu ON iv.material_type = mu.material_type
#             ORDER BY iv.holding_cost DESC
#         """)
        
#         # Note: This query assumes you have or will add cost_per_kg to your inventory table
#         # If you don't have that column, you'll need to adjust the query
        
#         return [dict(r) for r in result]
#     finally:
#         await conn.close()


# # ────────────────────────────────────────────────
# # 11) NEW: Dashboard Data
# # ────────────────────────────────────────────────
# @router.get("/inventory/dashboard", dependencies=[Depends(admin_or_manager)])
# async def inv_dashboard():
#     """Returns unified KPIs for inventory dashboard"""
#     async def _fetch():
#         conn = await connect_to_db()
#         try:
#             # Get overall inventory stats
#             inventory_stats = await conn.fetchrow("""
#                 SELECT 
#                     COUNT(DISTINCT material_type) as unique_materials,
#                     SUM(weight) as total_weight,
#                     SUM(CASE WHEN status = 'available' THEN weight ELSE 0 END) as available_weight,
#                     COUNT(*) as total_batches,
#                     COUNT(CASE WHEN status = 'available' THEN 1 ELSE NULL END) as available_batches,
#                     AVG(EXTRACT(DAY FROM (CURRENT_DATE - received_date))) as avg_age_days
#                 FROM inventory
#             """)
            
#             # Get top 5 materials by weight
#             top_materials = await conn.fetch("""
#                 SELECT 
#                     material_type,
#                     SUM(weight) as total_weight
#                 FROM inventory
#                 WHERE status = 'available'
#                 GROUP BY material_type
#                 ORDER BY total_weight DESC
#                 LIMIT 5
#             """)
            
#             # Get aging inventory breakdown
#             aging_breakdown = await conn.fetch("""
#                 SELECT 
#                     CASE 
#                         WHEN EXTRACT(DAY FROM (CURRENT_DATE - received_date)) <= 30 THEN '0-30 days'
#                         WHEN EXTRACT(DAY FROM (CURRENT_DATE - received_date)) <= 60 THEN '31-60 days'
#                         WHEN EXTRACT(DAY FROM (CURRENT_DATE - received_date)) <= 90 THEN '61-90 days'
#                         WHEN EXTRACT(DAY FROM (CURRENT_DATE - received_date)) <= 180 THEN '91-180 days'
#                         ELSE 'Over 180 days'
#                     END as age_group,
#                     COUNT(*) as batch_count,
#                     SUM(weight) as total_weight
#                 FROM inventory
#                 WHERE status = 'available'
#                 GROUP BY age_group
#                 ORDER BY age_group
#             """)
            
#             # Get recent flow data (last 7 days) - assuming mv_inv_flow_daily is created
#             recent_flow = await conn.fetch("""
#                 SELECT day, total_receipts, total_withdrawals
#                 FROM mv_inv_flow_daily
#                 WHERE day >= CURRENT_DATE - 7
#                 ORDER BY day
#             """)
            
#             # Get usage by category
#             usage_by_category = await conn.fetch("""
#                 SELECT 
#                     i.category,
#                     SUM(i.weight) as used_weight
#                 FROM inventory i
#                 JOIN job_orders j ON i.job_order_id = j.id
#                 WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 30
#                 GROUP BY i.category
#                 ORDER BY used_weight DESC
#             """)
            
#             # Compile all data for dashboard
#             dashboard_data = {
#                 "inventory_stats": dict(inventory_stats),
#                 "top_materials": [dict(r) for r in top_materials],
#                 "aging_breakdown": [dict(r) for r in aging_breakdown],
#                 "recent_flow": [dict(r) for r in recent_flow],
#                 "usage_by_category": [dict(r) for r in usage_by_category],
#                 "timestamp": datetime.now().isoformat()
#             }
            
#             return dashboard_data
            
#         finally:
#             await conn.close()
            
#     return await _get_cached("dashboard", _fetch)


# # ────────────────────────────────────────────────
# # 12) NEW: Historical Data Capture
# # ────────────────────────────────────────────────
# @router.post("/inventory/snapshot", dependencies=[Depends(admin_or_manager)])
# async def capture_inventory_snapshot():
#     """
#     Creates a snapshot of current inventory metrics and stores them in the analytics schema
#     This should be scheduled to run daily or weekly
#     """
#     conn = await connect_to_db()
#     try:
#         # Capture KPI history
#         await conn.execute("""
#             INSERT INTO analytics.inv_kpi_history (
#                 snapshot_date, material_type, on_hand_kg, kg_per_batch, batches, avg_density
#             )
#             SELECT 
#                 CURRENT_DATE,
#                 material_type,
#                 SUM(weight) AS on_hand_kg,
#                 MIN((weight/NULLIF(quantity,0))) AS kg_per_batch,
#                 SUM(quantity) AS batches,
#                 ROUND(AVG(density),2) AS avg_density
#             FROM inventory
#             WHERE status = 'available'
#             GROUP BY material_type
#         """)
        
#         # Update risk assessment - adjusted for your schema
#         await conn.execute("""
#             INSERT INTO analytics.inv_risk_assessment (
#                 material_type, assessment_date, stockout_risk, excess_stock_risk, aging_risk, cost_opportunity
#             )
#             WITH usage_rates AS (
#                 SELECT 
#                     i.material_type,
#                     SUM(i.weight) / GREATEST(EXTRACT(DAY FROM (CURRENT_DATE - MIN(j.start_time::date))), 1) as daily_usage
#                 FROM inventory i
#                 JOIN job_orders j ON i.job_order_id = j.id
#                 WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 90
#                 GROUP BY i.material_type
#             ),
            
#             inventory_age AS (
#                 SELECT 
#                     material_type,
#                     AVG(EXTRACT(DAY FROM (CURRENT_DATE - received_date))) as avg_age_days
#                 FROM inventory
#                 WHERE status = 'available'
#                 GROUP BY material_type
#             ),
            
#             current_stock AS (
#                 SELECT 
#                     material_type,
#                     SUM(weight) as total_weight
#                 FROM inventory
#                 WHERE status = 'available'
#                 GROUP BY material_type
#             )
            
#             SELECT 
#                 c.material_type,
#                 CURRENT_DATE,
#                 -- Stockout risk (0-1)
#                 CASE 
#                     WHEN u.daily_usage > 0 AND c.total_weight / u.daily_usage < 15 THEN 
#                         GREATEST(0, 1 - ((c.total_weight / u.daily_usage) / 15))
#                     ELSE 0
#                 END as stockout_risk,
                
#                 -- Excess stock risk
#                 CASE
#                     WHEN u.daily_usage > 0 AND c.total_weight / u.daily_usage > 90 THEN
#                         LEAST(1, ((c.total_weight / u.daily_usage) - 90) / 180)
#                     ELSE 0
#                 END as excess_stock_risk,
                
#                 -- Aging risk (0-1)
#                 CASE 
#                     WHEN a.avg_age_days > 90 THEN 
#                         LEAST(1, (a.avg_age_days - 90) / 180)
#                     ELSE 0
#                 END as aging_risk,
                
#                 -- Cost opportunity
#                 CASE
#                     WHEN a.avg_age_days > 90 OR (u.daily_usage > 0 AND c.total_weight / u.daily_usage > 90) THEN
#                         c.total_weight * 0.05 -- 5% of inventory value can be freed up
#                     ELSE 0
#                 END as cost_opportunity
                
#             FROM current_stock c
#             LEFT JOIN usage_rates u ON c.material_type = u.material_type
#             LEFT JOIN inventory_age a ON c.material_type = a.material_type
#         """)
        
#         # Update seasonality analysis (if month end) - adjusted for your schema
#         if datetime.now().day == 1 or (datetime.now() + timedelta(days=1)).day == 1:
#             await conn.execute("""
#                 -- Find any existing records for this month to update
#                 WITH monthly_data AS (
#                     SELECT 
#                         i.material_type,
#                         EXTRACT(MONTH FROM CURRENT_DATE - INTERVAL '1 month') as month,
#                         SUM(i.weight) as monthly_usage
#                     FROM inventory i
#                     JOIN job_orders j ON i.job_order_id = j.id
#                     WHERE 
#                         i.status = 'used'
#                         AND EXTRACT(MONTH FROM j.start_time) = EXTRACT(MONTH FROM CURRENT_DATE - INTERVAL '1 month')
#                         AND EXTRACT(YEAR FROM j.start_time) = EXTRACT(YEAR FROM CURRENT_DATE - INTERVAL '1 month')
#                     GROUP BY i.material_type
#                 ),
                
#                 avg_usage AS (
#                     SELECT 
#                         i.material_type,
#                         AVG(monthly_usage) as avg_monthly_usage
#                     FROM (
#                         SELECT 
#                             i.material_type,
#                             EXTRACT(MONTH FROM j.start_time) as month,
#                             EXTRACT(YEAR FROM j.start_time) as year,
#                             SUM(i.weight) as monthly_usage
#                         FROM inventory i
#                         JOIN job_orders j ON i.job_order_id = j.id
#                         WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - INTERVAL '2 years'
#                         GROUP BY i.material_type, EXTRACT(MONTH FROM j.start_time), EXTRACT(YEAR FROM j.start_time)
#                     ) monthly_usage
#                     GROUP BY i.material_type
#                 )
                
#                 INSERT INTO analytics.inv_seasonality (
#                     material_type, month, seasonal_factor, confidence_level
#                 )
#                 SELECT 
#                     m.material_type,
#                     m.month::integer,
#                     CASE WHEN a.avg_monthly_usage > 0 
#                          THEN m.monthly_usage / a.avg_monthly_usage 
#                          ELSE 1 END as seasonal_factor,
#                     0.8 as confidence_level  -- Set default confidence level
#                 FROM monthly_data m
#                 JOIN avg_usage a ON m.material_type = a.material_type
#                 ON CONFLICT (material_type, month) DO UPDATE
#                 SET 
#                     seasonal_factor = EXCLUDED.seasonal_factor,
#                     confidence_level = (analytics.inv_seasonality.confidence_level + EXCLUDED.confidence_level) / 2
#             """)
        
#         return {"status": "success", "message": "Analytics snapshot captured successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error capturing analytics snapshot: {str(e)}")
#     finally:
#         await conn.close()

# # ────────────────────────────────────────────────
# # 13) NEW: Material Usage By Job Type
# # ────────────────────────────────────────────────
# @router.get("/inventory/usage_by_job", dependencies=[Depends(admin_or_manager)])
# async def usage_by_job(days: int = 90):
#    """Analyzes how materials are being used across different job types"""
#    conn = await connect_to_db()
#    try:
#        result = await conn.fetch("""
#            SELECT 
#                j.job_type,
#                i.material_type,
#                SUM(i.weight) as total_used,
#                COUNT(DISTINCT j.id) as job_count,
#                SUM(i.weight) / COUNT(DISTINCT j.id) as avg_usage_per_job
#            FROM inventory i
#            JOIN job_orders j ON i.job_order_id = j.id
#            WHERE 
#                i.status = 'used' 
#                AND j.start_time >= CURRENT_DATE - $1::int
#            GROUP BY j.job_type, i.material_type
#            ORDER BY j.job_type, total_used DESC
#        """, days)
       
#        return [dict(r) for r in result]
#    finally:
#        await conn.close()


# # ────────────────────────────────────────────────
# # 14) NEW: Supplier Performance Analysis
# # ────────────────────────────────────────────────
# @router.get("/inventory/supplier_performance", dependencies=[Depends(admin_or_manager)])
# async def supplier_performance():
#    """Analyzes supplier performance metrics such as lead times and quality"""
#    conn = await connect_to_db()
#    try:
#        result = await conn.fetch("""
#            WITH supplier_metrics AS (
#                SELECT 
#                    supplier,
#                    COUNT(*) as delivery_count,
#                    AVG(EXTRACT(DAY FROM (received_date - order_date))) as avg_lead_time,
#                    STDDEV(EXTRACT(DAY FROM (received_date - order_date))) as lead_time_stddev,
#                    COUNT(CASE WHEN grade IN ('A', 'Premium') THEN 1 ELSE NULL END) * 100.0 / COUNT(*) as premium_quality_pct,
#                    SUM(weight) as total_weight_delivered,
#                    SUM(weight * COALESCE(cost_per_kg, 
#                        CASE 
#                            WHEN category = '1st Degree' THEN 5
#                            ELSE 3
#                        END)) as total_value
#                FROM inventory
#                WHERE order_date IS NOT NULL AND received_date IS NOT NULL
#                GROUP BY supplier
#            )
           
#            SELECT 
#                supplier,
#                delivery_count,
#                ROUND(avg_lead_time::numeric, 1) as avg_lead_time_days,
#                ROUND(lead_time_stddev::numeric, 1) as lead_time_consistency,
#                ROUND(premium_quality_pct::numeric, 1) as quality_score,
#                total_weight_delivered,
#                total_value,
#                -- Overall reliability score (0-10)
#                ROUND(((10 - LEAST(avg_lead_time, 30) / 3) * 0.4 +  -- Lower lead time is better (max 10 points)
#                     (10 - LEAST(lead_time_stddev, 10)) * 0.2 +     -- Consistent lead times (max 10 points)
#                     (premium_quality_pct / 10) * 0.4)::numeric, 1) -- Quality percentage (max 10 points)
#                as reliability_score
#            FROM supplier_metrics
#            ORDER BY reliability_score DESC
#        """)
       
#        return [dict(r) for r in result]
#    finally:
#        await conn.close()


# # ────────────────────────────────────────────────
# # 15) NEW: Inventory Efficiency Metrics
# # ────────────────────────────────────────────────
# @router.get("/inventory/efficiency", dependencies=[Depends(admin_or_manager)])
# async def inventory_efficiency():
#    """Calculates key inventory efficiency metrics like turnover rate"""
#    conn = await connect_to_db()
#    try:
#        result = await conn.fetchrow("""
#            WITH inventory_avg AS (
#                -- Calculate average inventory over time using snapshots
#                -- If you don't have historical snapshots, use current inventory as an approximation
#                SELECT 
#                    SUM(weight) as avg_inventory_value
#                FROM inventory
#                WHERE status = 'available'
#            ),
           
#            material_usage AS (
#                -- Calculate material used in the last 365 days
#                SELECT 
#                    SUM(i.weight) as annual_usage
#                FROM inventory i
#                JOIN job_orders j ON i.job_order_id = j.id
#                WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 365
#            ),
           
#            days_of_supply AS (
#                -- Calculate how many days current inventory would last
#                SELECT 
#                    (SELECT SUM(weight) FROM inventory WHERE status = 'available') /
#                    NULLIF((SELECT SUM(i.weight) / 365 
#                           FROM inventory i 
#                           JOIN job_orders j ON i.job_order_id = j.id
#                           WHERE i.status = 'used' AND j.start_time >= CURRENT_DATE - 365), 0) as days
#            ),
           
#            aging_stats AS (
#                -- Calculate aging statistics
#                SELECT 
#                    AVG(EXTRACT(DAY FROM (CURRENT_DATE - received_date))) as avg_age_days,
#                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(DAY FROM (CURRENT_DATE - received_date))) as median_age_days,
#                    MAX(EXTRACT(DAY FROM (CURRENT_DATE - received_date))) as oldest_item_days
#                FROM inventory
#                WHERE status = 'available'
#            )
           
#            SELECT 
#                -- Inventory Turnover Rate = Annual Usage / Average Inventory Value
#                COALESCE(m.annual_usage / NULLIF(i.avg_inventory_value, 0), 0) as inventory_turnover_rate,
               
#                -- Days of Supply
#                COALESCE(d.days, 0) as days_of_supply,
               
#                -- Aging Statistics
#                COALESCE(a.avg_age_days, 0) as avg_age_days,
#                COALESCE(a.median_age_days, 0) as median_age_days,
#                COALESCE(a.oldest_item_days, 0) as oldest_item_days,
               
#                -- Efficiency Score (0-10)
#                CASE 
#                    WHEN m.annual_usage / NULLIF(i.avg_inventory_value, 0) BETWEEN 3 AND 6 THEN 10  -- Ideal turnover
#                    WHEN m.annual_usage / NULLIF(i.avg_inventory_value, 0) BETWEEN 2 AND 8 THEN 8   -- Good turnover
#                    WHEN m.annual_usage / NULLIF(i.avg_inventory_value, 0) BETWEEN 1 AND 10 THEN 6  -- Acceptable turnover
#                    ELSE 4  -- Too low or too high turnover
#                END -
#                CASE
#                    WHEN a.avg_age_days > 180 THEN 3  -- Significant aging issues
#                    WHEN a.avg_age_days > 90 THEN 1   -- Some aging issues
#                    ELSE 0
#                END as efficiency_score
               
#            FROM inventory_avg i, material_usage m, days_of_supply d, aging_stats a
#        """)
       
#        return dict(result)
#    finally:
#        await conn.close()


# # ────────────────────────────────────────────────
# # 16) NEW: Material Trends Analysis
# # ────────────────────────────────────────────────
# @router.get("/inventory/material_trends", dependencies=[Depends(admin_or_manager)])
# async def material_trends(days: int = 180):
#    """Analyzes trends in material usage over time periods"""
#    conn = await connect_to_db()
#    try:
#        # This query calculates monthly trends for materials
#        result = await conn.fetch("""
#            WITH monthly_usage AS (
#                SELECT 
#                    i.material_type,
#                    DATE_TRUNC('month', j.start_time) as month,
#                    SUM(i.weight) as usage
#                FROM inventory i
#                JOIN job_orders j ON i.job_order_id = j.id
#                WHERE 
#                    i.status = 'used' 
#                    AND j.start_time >= CURRENT_DATE - ($1::int || ' days')::interval
#                GROUP BY i.material_type, DATE_TRUNC('month', j.start_time)
#                ORDER BY month
#            ),
           
#            -- Calculate the trend (average month-over-month change)
#            trend_calc AS (
#                SELECT 
#                    material_type,
#                    REGR_SLOPE(usage, EXTRACT(EPOCH FROM month) / (60*60*24*30)) as trend_slope,
#                    AVG(usage) as avg_usage
#                FROM monthly_usage
#                GROUP BY material_type
#            )
           
#            SELECT 
#                t.material_type,
#                t.avg_usage,
#                t.trend_slope,
#                -- Trend as percentage
#                CASE 
#                    WHEN t.avg_usage > 0 THEN
#                        ROUND((t.trend_slope / t.avg_usage * 100)::numeric, 1)
#                    ELSE 0
#                END as monthly_trend_pct,
#                -- Trend direction
#                CASE 
#                    WHEN t.trend_slope > 0 THEN 'increasing'
#                    WHEN t.trend_slope < 0 THEN 'decreasing'
#                    ELSE 'stable'
#                END as trend_direction,
#                -- Current stock
#                (SELECT SUM(weight) FROM inventory 
#                 WHERE status = 'available' AND material_type = t.material_type) as current_stock
#            FROM trend_calc t
#            ORDER BY ABS(t.trend_slope) DESC
#        """, days)
       
#        return [dict(r) for r in result]
#    finally:
#        await conn.close()


# # ────────────────────────────────────────────────
# # 17) NEW: API to refresh materialized views
# # ────────────────────────────────────────────────
# @router.post("/refresh_views", dependencies=[Depends(admin_or_manager)])
# async def refresh_materialized_views():
#     """Refreshes all materialized views used for analytics"""
#     conn = await connect_to_db()
#     try:
#         # Check if the materialized view exists
#         view_exists = await conn.fetchval(
#             "SELECT EXISTS (SELECT FROM pg_matviews WHERE matviewname = 'mv_inv_flow_daily')"
#         )
        
#         if view_exists:
#             # Drop the view if it exists
#             await conn.execute("DROP MATERIALIZED VIEW mv_inv_flow_daily")
        
#         # Create the materialized view using only job_orders.start_time
#         await conn.execute("""
#             CREATE MATERIALIZED VIEW mv_inv_flow_daily AS
#             WITH movements AS (
#                 /*  all incoming weight  */
#                 SELECT
#                     received_date::date AS day,
#                     weight::numeric AS qty          -- positive
#                 FROM inventory
#                 WHERE received_date IS NOT NULL

#                 UNION ALL

#                 /*  all outgoing weight (negative)  */
#                 SELECT
#                     j.start_time::date AS day,
#                     -i.weight::numeric AS qty          -- negative
#                 FROM inventory i
#                 JOIN job_orders j ON i.job_order_id = j.id
#                 WHERE i.status = 'used' AND j.start_time IS NOT NULL
#             )

#             SELECT
#                 day,
#                 SUM(CASE WHEN qty > 0 THEN qty ELSE 0 END) AS total_receipts,
#                 SUM(CASE WHEN qty < 0 THEN -qty ELSE 0 END) AS total_withdrawals
#             FROM movements
#             GROUP BY day
#             ORDER BY day;
#         """)
        
#         return {"status": "success", "message": "All materialized views refreshed successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error refreshing materialized views: {str(e)}")
#     finally:
#         await conn.close()