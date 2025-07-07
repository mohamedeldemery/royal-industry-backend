from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import asyncpg
import logging
from dateutil import parser

from routers.employees import admin_or_manager, TokenData

logger = logging.getLogger(__name__)

def parse_datetime(date_string: str) -> datetime:
    """Parse datetime string handling multiple formats"""
    try:
        # First try ISO format with Z replacement
        if 'Z' in date_string:
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        
        # Try direct ISO format
        try:
            return datetime.fromisoformat(date_string)
        except ValueError:
            pass
        
        # Use dateutil parser as fallback for various formats
        return parser.parse(date_string)
        
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid date format: {date_string}. Expected ISO format like '2025-05-15T09:58:25' or '2025-05-15 09:58:25'"
        )

router = APIRouter(
    prefix="/api",
    tags=["machine_reports"],
    responses={404: {"description": "Not found"}},
)

# -------------------------------------------------------
# Database Connection
# -------------------------------------------------------
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

@router.get("/machine-reports", dependencies=[Depends(admin_or_manager)])
async def get_machine_reports(
    start_date: str = Query(..., description="Start date in ISO format"),
    end_date: str = Query(..., description="End date in ISO format"),
    period: str = Query(..., description="Period type: Daily, Weekly, Monthly, Yearly"),
    token: TokenData = Depends(admin_or_manager)
):
    """
    Get machine production reports organized by production lines and stages with timing calculations
    """
    conn = await connect_to_db()
    
    try:
        # Parse dates - handle multiple formats
        start_dt = parse_datetime(start_date)
        end_dt = parse_datetime(end_date)
        
        logger.info(f"Fetching machine reports from {start_dt} to {end_dt} for period {period}")
        
        # Get Poly Bags production data
        poly_bags_data = await _get_poly_bags_machine_data(conn, start_dt, end_dt, period)
        
        # Get Plastic Hangers production data
        plastic_hangers_data = await _get_plastic_hangers_machine_data(conn, start_dt, end_dt, period)
        
        return {
            "poly_bags": poly_bags_data,
            "plastic_hangers": plastic_hangers_data,
            "period": period,
            "date_range": {
                "start": start_date,
                "end": end_date
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching machine reports: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching machine reports: {str(e)}")
    finally:
        await conn.close()

async def _get_poly_bags_machine_data(conn: asyncpg.Connection, start_date: datetime, end_date: datetime, period: str) -> Dict[str, Any]:
    """Get production data for all Poly Bags machines with sequential timing calculations"""
    
    blowing_film_query = """
        WITH blowing_film_data AS (
            SELECT 
                mph.machine_id,
                mph.order_id,
                mph.roll_index,
                mph.production_weight_g,
                mph.waste_weight_g,
                mph.recorded_at AT TIME ZONE 'UTC' as recorded_at_utc,
                jo.start_time AT TIME ZONE 'UTC' as start_time_utc,
                -- Calculate production time with timezone-aware timestamps
                CASE 
                    WHEN mph.roll_index = 1 AND jo.start_time IS NOT NULL THEN 
                        GREATEST(0, EXTRACT(EPOCH FROM (
                            (mph.recorded_at AT TIME ZONE 'UTC') - (jo.start_time AT TIME ZONE 'UTC')
                        )) / 3600.0)
                    WHEN mph.roll_index > 1 THEN 
                        GREATEST(0, COALESCE(
                            EXTRACT(EPOCH FROM (
                                (mph.recorded_at AT TIME ZONE 'UTC') - 
                                COALESCE(
                                    LAG(mph.recorded_at AT TIME ZONE 'UTC') OVER (
                                        PARTITION BY mph.order_id, mph.machine_id 
                                        ORDER BY mph.roll_index
                                    ),
                                    jo.start_time AT TIME ZONE 'UTC'
                                )
                            )) / 3600.0, 
                            0
                         ))

                    ELSE 0
                END as production_time_hours
            FROM machine_production_history mph
            JOIN job_orders jo ON mph.order_id = jo.id
            WHERE mph.stage = 'BLOWING'
                AND jo.product IN ('AB', 'PR')
                AND mph.recorded_at BETWEEN $1 AND $2
                AND mph.recorded_at IS NOT NULL
        )
            SELECT 
            machine_id,
            COUNT(DISTINCT order_id) as order_count,
            COUNT(roll_index) as roll_count,
            COALESCE(SUM(production_weight_g), 0) as total_production_g,
            COALESCE(SUM(waste_weight_g), 0) as total_waste_g,
            CASE 
                WHEN COUNT(CASE WHEN production_time_hours > 0 THEN 1 END) > 0 THEN
                    AVG(CASE WHEN production_time_hours > 0 THEN production_time_hours END)
                ELSE 0
            END as avg_production_time_hours,
            COALESCE(SUM(production_time_hours), 0) as total_production_time_hours
        FROM blowing_film_data
        WHERE machine_id IS NOT NULL
        GROUP BY machine_id
        ORDER BY machine_id
    """
    
    # Fixed Query for Printing machines
    printing_query = """
        WITH printing_data AS (
            SELECT 
                mph.machine_id,
                mph.order_id,
                mph.roll_index,
                mph.production_weight_g,
                mph.waste_weight_g,
                mph.recorded_at,
                pr.roll_weight_ts,
                -- Calculate time from blowing completion to printing completion
                CASE 
                    WHEN pr.roll_weight_ts IS NOT NULL THEN 
                        GREATEST(0, EXTRACT(EPOCH FROM (mph.recorded_at - pr.roll_weight_ts)) / 3600.0)
                    ELSE 0
                END as production_time_hours
            FROM machine_production_history mph
            JOIN production_rolls pr ON mph.order_id = pr.order_id AND mph.roll_index = pr.tmp_index
            JOIN job_orders jo ON mph.order_id = jo.id
            WHERE mph.stage = 'PRINTING'
                AND jo.product IN ('AB', 'PR')
                AND mph.recorded_at BETWEEN $1 AND $2
                AND mph.recorded_at IS NOT NULL
        )
        SELECT 
            machine_id,
            COUNT(DISTINCT order_id) as order_count,
            COUNT(roll_index) as roll_count,
            COALESCE(SUM(production_weight_g), 0) as total_production_g,
            COALESCE(SUM(waste_weight_g), 0) as total_waste_g,
            CASE 
                WHEN COUNT(CASE WHEN production_time_hours > 0 THEN 1 END) > 0 THEN
                    AVG(CASE WHEN production_time_hours > 0 THEN production_time_hours END)
                ELSE 0
            END as avg_production_time_hours,
            COALESCE(SUM(production_time_hours), 0) as total_production_time_hours
        FROM printing_data
        WHERE machine_id IS NOT NULL
        GROUP BY machine_id
        ORDER BY machine_id
    """
    
    # Fixed Query for Cutting machines
    cutting_query = """
        WITH cutting_data AS (
            SELECT 
                mph.machine_id,
                mph.order_id,
                mph.roll_index,
                mph.production_weight_g,
                mph.waste_weight_g,
                mph.recorded_at,
                pr.printed_weight_ts,
                -- Calculate time from printing completion to cutting completion
                CASE 
                    WHEN pr.printed_weight_ts IS NOT NULL THEN 
                        GREATEST(0, EXTRACT(EPOCH FROM (mph.recorded_at - pr.printed_weight_ts)) / 3600.0)
                    ELSE 0
                END as production_time_hours
            FROM machine_production_history mph
            JOIN production_rolls pr ON mph.order_id = pr.order_id AND mph.roll_index = pr.tmp_index
            JOIN job_orders jo ON mph.order_id = jo.id
            WHERE mph.stage = 'CUTTING'
                AND jo.product IN ('AB', 'PR')
                AND mph.recorded_at BETWEEN $1 AND $2
                AND mph.recorded_at IS NOT NULL
        )
        SELECT 
            machine_id,
            COUNT(DISTINCT order_id) as order_count,
            COUNT(roll_index) as roll_count,
            COALESCE(SUM(production_weight_g), 0) as total_production_g,
            COALESCE(SUM(waste_weight_g), 0) as total_waste_g,
            CASE 
                WHEN COUNT(CASE WHEN production_time_hours > 0 THEN 1 END) > 0 THEN
                    AVG(CASE WHEN production_time_hours > 0 THEN production_time_hours END)
                ELSE 0
            END as avg_production_time_hours,
            COALESCE(SUM(production_time_hours), 0) as total_production_time_hours
        FROM cutting_data
        WHERE machine_id IS NOT NULL
        GROUP BY machine_id
        ORDER BY machine_id
    """
    
    try:
        # Execute queries
        blowing_film_result = await conn.fetch(blowing_film_query, start_date, end_date)
        printing_result = await conn.fetch(printing_query, start_date, end_date)
        cutting_result = await conn.fetch(cutting_query, start_date, end_date)
        
        # Convert results to dictionaries
        blowing_film_machines = [
            {
                "machine_id": row["machine_id"],
                "stage": "Blowing Film",
                "order_count": row["order_count"],
                "roll_count": row["roll_count"],
                "total_production_g": float(row["total_production_g"] or 0),
                "total_waste_g": float(row["total_waste_g"] or 0),
                "avg_production_time_hours": round(float(row["avg_production_time_hours"] or 0), 2),
                "total_production_time_hours": round(float(row["total_production_time_hours"] or 0), 2),
                "efficiency_percentage": calculate_efficiency(row["total_production_g"], row["total_waste_g"])
            }
            for row in blowing_film_result
        ]
        
        printing_machines = [
            {
                "machine_id": row["machine_id"],
                "stage": "Printing",
                "order_count": row["order_count"],
                "roll_count": row["roll_count"],
                "total_production_g": float(row["total_production_g"] or 0),
                "total_waste_g": float(row["total_waste_g"] or 0),
                "avg_production_time_hours": round(float(row["avg_production_time_hours"] or 0), 2),
                "total_production_time_hours": round(float(row["total_production_time_hours"] or 0), 2),
                "efficiency_percentage": calculate_efficiency(row["total_production_g"], row["total_waste_g"])
            }
            for row in printing_result
        ]
        
        cutting_machines = [
            {
                "machine_id": row["machine_id"],
                "stage": "Cutting",
                "order_count": row["order_count"],
                "roll_count": row["roll_count"],
                "total_production_g": float(row["total_production_g"] or 0),
                "total_waste_g": float(row["total_waste_g"] or 0),
                "avg_production_time_hours": round(float(row["avg_production_time_hours"] or 0), 2),
                "total_production_time_hours": round(float(row["total_production_time_hours"] or 0), 2),
                "efficiency_percentage": calculate_efficiency(row["total_production_g"], row["total_waste_g"])
            }
            for row in cutting_result
        ]
        
        return {
            "blowing_film": blowing_film_machines,
            "printing": printing_machines,
            "cutting": cutting_machines
        }
        
    except Exception as e:
        logger.error(f"Error fetching poly bags machine data: {str(e)}")
        raise

async def _get_plastic_hangers_machine_data(conn: asyncpg.Connection, start_date: datetime, end_date: datetime, period: str) -> Dict[str, Any]:
    """Get production data for all Plastic Hangers machines with sequential timing calculations"""
    
    # Fixed Query for Injection Molding machines
    injection_molding_query = """
        WITH injection_data AS (
            SELECT 
                ph.injection_machine_id as machine_id,
                ph.order_id,
                ph.batch_index,
                ph.injection_weight_g as production_weight_g,
                ph.waste_of_im_g as waste_weight_g,
                ph.injection_weight_ts as recorded_at,
                jo.start_time,
                -- Calculate production time properly
                CASE 
                    WHEN ph.batch_index = 1 AND jo.start_time IS NOT NULL THEN 
                        GREATEST(0, EXTRACT(EPOCH FROM (ph.injection_weight_ts - jo.start_time)) / 3600.0)
                    WHEN ph.batch_index > 1 THEN 
                        GREATEST(0, COALESCE(
                            EXTRACT(EPOCH FROM (
                                ph.injection_weight_ts - 
                                LAG(ph.injection_weight_ts) OVER (
                                    PARTITION BY ph.order_id 
                                    ORDER BY ph.batch_index
                                )
                            )) / 3600.0,
                            0
                        ))
                    ELSE 0
                END as production_time_hours
            FROM production_hangers ph
            JOIN job_orders jo ON ph.order_id = jo.id
            WHERE ph.injection_machine_id IS NOT NULL
                AND ph.injection_weight_g IS NOT NULL
                AND jo.product = 'PH'
                AND ph.injection_weight_ts BETWEEN $1 AND $2
                AND ph.injection_weight_ts IS NOT NULL
        )
        SELECT 
            machine_id,
            COUNT(DISTINCT order_id) as order_count,
            COUNT(batch_index) as batch_count,
            COALESCE(SUM(production_weight_g), 0) as total_production_g,
            COALESCE(SUM(waste_weight_g), 0) as total_waste_g,
            CASE 
                WHEN COUNT(CASE WHEN production_time_hours > 0 THEN 1 END) > 0 THEN
                    AVG(CASE WHEN production_time_hours > 0 THEN production_time_hours END)
                ELSE 0
            END as avg_production_time_hours,
            COALESCE(SUM(production_time_hours), 0) as total_production_time_hours
        FROM injection_data
        WHERE machine_id IS NOT NULL
        GROUP BY machine_id
        ORDER BY machine_id
    """
    
    try:
        injection_molding_result = await conn.fetch(injection_molding_query, start_date, end_date)
        
        injection_molding_machines = [
            {
                "machine_id": row["machine_id"],
                "stage": "Injection Molding",
                "order_count": row["order_count"],
                "batch_count": row["batch_count"],
                "total_production_g": float(row["total_production_g"] or 0),
                "total_waste_g": float(row["total_waste_g"] or 0),
                "avg_production_time_hours": round(float(row["avg_production_time_hours"] or 0), 2),
                "total_production_time_hours": round(float(row["total_production_time_hours"] or 0), 2),
                "efficiency_percentage": calculate_efficiency(row["total_production_g"], row["total_waste_g"])
            }
            for row in injection_molding_result
        ]
        
        return {
            "injection_molding": injection_molding_machines
        }
        
    except Exception as e:
        logger.error(f"Error fetching plastic hangers machine data: {str(e)}")
        raise

@router.get("/machine-detailed-report", dependencies=[Depends(admin_or_manager)])
async def get_machine_detailed_report(
    machine_id: str = Query(..., description="Machine ID"),
    line_type: str = Query(..., description="Line type: poly_bags or plastic_hangers"),
    start_date: str = Query(..., description="Start date in ISO format"),
    end_date: str = Query(..., description="End date in ISO format"),
    token: TokenData = Depends(admin_or_manager)
):
    """
    Get detailed production records for a specific machine with timing calculations
    """
    conn = await connect_to_db()
    
    try:
        # Parse dates - handle multiple formats
        start_dt = parse_datetime(start_date)
        end_dt = parse_datetime(end_date)
        
        logger.info(f"Fetching detailed report for machine {machine_id}, line type {line_type}")
        
        if line_type == "poly_bags":
            production_records = await _get_poly_bags_detailed_records(conn, machine_id, start_dt, end_dt)
        elif line_type == "plastic_hangers":
            production_records = await _get_plastic_hangers_detailed_records(conn, machine_id, start_dt, end_dt)
        else:
            raise HTTPException(status_code=400, detail="Invalid line_type. Must be 'poly_bags' or 'plastic_hangers'")
        
        return {
            "machine_id": machine_id,
            "line_type": line_type,
            "production_records": production_records,
            "date_range": {
                "start": start_date,
                "end": end_date
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching detailed machine report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching detailed report: {str(e)}")
    finally:
        await conn.close()


async def _get_poly_bags_detailed_records(conn: asyncpg.Connection, machine_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """Get detailed production records for poly bags machines using machine_production_history"""

    query = """
        WITH production_timing AS (
            SELECT
                mph.*,
                jo.client_name,
                jo.product,
                jo.model,
                jo.order_quantity,
                jo.length_cm,
                jo.width_cm,
                jo.micron_mm,
                jo.unit_weight,
                jo.start_time,
                pr.roll_weight_ts,
                pr.printed_weight_ts,
                pr.cut_weight_ts,
                -- Calculate timing based on stage
                CASE
                    WHEN mph.stage = 'BLOWING' THEN
                        CASE
                            WHEN mph.roll_index = 1 AND jo.start_time IS NOT NULL THEN
                                GREATEST(0, EXTRACT(EPOCH FROM (mph.recorded_at - jo.start_time)) / 3600.0)
                            WHEN mph.roll_index > 1 THEN
                                GREATEST(0, COALESCE(
                                    EXTRACT(EPOCH FROM (
                                        mph.recorded_at -
                                        LAG(mph.recorded_at) OVER (
                                            PARTITION BY mph.order_id, mph.machine_id
                                            ORDER BY mph.roll_index
                                        )
                                    )) / 3600.0,
                                    0
                                ))
                            ELSE 0
                        END
                    WHEN mph.stage = 'PRINTING' AND pr.roll_weight_ts IS NOT NULL THEN
                        GREATEST(0, EXTRACT(EPOCH FROM (mph.recorded_at - pr.roll_weight_ts)) / 3600.0)
                    WHEN mph.stage = 'CUTTING' AND pr.printed_weight_ts IS NOT NULL THEN
                        GREATEST(0, EXTRACT(EPOCH FROM (mph.recorded_at - pr.printed_weight_ts)) / 3600.0)
                    ELSE 0
                END as production_time_hours
            FROM machine_production_history mph
            JOIN job_orders jo ON mph.order_id = jo.id
            LEFT JOIN production_rolls pr ON mph.order_id = pr.order_id AND mph.roll_index = pr.tmp_index
            WHERE mph.machine_id = $1
                AND jo.product IN ('AB', 'PR')
                AND mph.recorded_at BETWEEN $2 AND $3
                AND mph.recorded_at IS NOT NULL
        )
        SELECT * FROM production_timing
        ORDER BY order_id, roll_index, recorded_at DESC
    """

    try:
        result = await conn.fetch(query, machine_id, start_date, end_date)

        # Group records by order for better organization
        orders_dict = {}
        for row in result:
            order_id = row["order_id"]
            if order_id not in orders_dict:
                orders_dict[order_id] = {
                    "order_id": order_id,
                    "client_name": row["client_name"] if row["client_name"] else "N/A",
                    "product": row["product"] if row["product"] else "N/A",
                    "model": row["model"] if row["model"] else "N/A",
                    "order_quantity": int(row["order_quantity"]) if row["order_quantity"] else 0,
                    # IMPORTANT: Keep the field names that Flutter expects
                    "length_cm": float(row["length_cm"]) if row["length_cm"] else 0,
                    "width_cm": float(row["width_cm"]) if row["width_cm"] else 0,
                    "micron_mm": float(row["micron_mm"]) if row["micron_mm"] else 0,
                    "unit_weight": float(row["unit_weight"]) if row["unit_weight"] else 0,
                    "start_time": row["start_time"].isoformat() if row["start_time"] else None,
                    "rolls": [],
                    "total_production_weight": 0,
                    "total_waste_weight": 0,
                    "total_production_time": 0
                }

            roll_data = {
                "roll_index": row["roll_index"] if row["roll_index"] is not None else 0,
                "stage": row["stage"] if row["stage"] else "Unknown",
                "production_weight_g": float(row["production_weight_g"]) if row["production_weight_g"] else 0,
                "waste_weight_g": float(row["waste_weight_g"]) if row["waste_weight_g"] else 0,
                "production_time_hours": round(float(row["production_time_hours"]) if row["production_time_hours"] else 0, 2),
                "recorded_at": row["recorded_at"].isoformat() if row["recorded_at"] else None,
                "roll_weight_ts": row["roll_weight_ts"].isoformat() if row["roll_weight_ts"] else None,
                "printed_weight_ts": row["printed_weight_ts"].isoformat() if row["printed_weight_ts"] else None,
                "cut_weight_ts": row["cut_weight_ts"].isoformat() if row["cut_weight_ts"] else None
            }

            orders_dict[order_id]["rolls"].append(roll_data)
            orders_dict[order_id]["total_production_weight"] += roll_data["production_weight_g"]
            orders_dict[order_id]["total_waste_weight"] += roll_data["waste_weight_g"]
            orders_dict[order_id]["total_production_time"] += roll_data["production_time_hours"]

        # Round totals and ensure all values are safe
        for order in orders_dict.values():
            order["total_production_time"] = round(order["total_production_time"], 2)

        return list(orders_dict.values())

    except Exception as e:
        logger.error(f"Error fetching poly bags detailed records: {str(e)}")
        raise

async def _get_plastic_hangers_detailed_records(conn: asyncpg.Connection, machine_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """Get detailed production records for plastic hangers machines with sequential timing calculations"""

    query = """
        WITH production_timing AS (
            SELECT
                ph.order_id,
                ph.batch_index,
                ph.injection_weight_g as production_weight_g,
                ph.waste_of_im_g as waste_weight_g,
                ph.injection_weight_ts as recorded_at,
                jo.client_name,
                jo.product,
                jo.model,
                jo.order_quantity,
                jo.unit_weight,
                jo.start_time,
                -- Calculate timing for injection molding
                CASE
                    WHEN ph.batch_index = 1 AND jo.start_time IS NOT NULL THEN
                        GREATEST(0, EXTRACT(EPOCH FROM (ph.injection_weight_ts - jo.start_time)) / 3600.0)
                    WHEN ph.batch_index > 1 THEN
                        GREATEST(0, COALESCE(
                            EXTRACT(EPOCH FROM (
                                ph.injection_weight_ts -
                                LAG(ph.injection_weight_ts) OVER (
                                    PARTITION BY ph.order_id
                                    ORDER BY ph.batch_index
                                )
                            )) / 3600.0,
                            0
                        ))
                    ELSE 0
                END as production_time_hours
            FROM production_hangers ph
            JOIN job_orders jo ON ph.order_id = jo.id
            WHERE ph.injection_machine_id = $1
                AND jo.product = 'PH'
                AND ph.injection_weight_ts BETWEEN $2 AND $3
                AND ph.injection_weight_ts IS NOT NULL
        )
        SELECT * FROM production_timing
        ORDER BY order_id, batch_index
    """

    try:
        result = await conn.fetch(query, machine_id, start_date, end_date)

        # Group records by order for better organization
        orders_dict = {}
        for row in result:
            order_id = row["order_id"]
            if order_id not in orders_dict:
                orders_dict[order_id] = {
                    "order_id": order_id,
                    "client_name": row["client_name"] if row["client_name"] else "N/A",
                    "product": row["product"] if row["product"] else "N/A",
                    "model": row["model"] if row["model"] else "N/A",
                    "order_quantity": int(row["order_quantity"]) if row["order_quantity"] else 0,
                    "unit_weight": float(row["unit_weight"]) if row["unit_weight"] else 0,
                    "start_time": row["start_time"].isoformat() if row["start_time"] else None,
                    "batches": [],
                    "total_production_weight": 0,
                    "total_waste_weight": 0,
                    "total_production_time": 0
                }

            batch_data = {
                "batch_index": row["batch_index"] if row["batch_index"] is not None else 0,
                "production_weight_g": float(row["production_weight_g"]) if row["production_weight_g"] else 0,
                "waste_weight_g": float(row["waste_weight_g"]) if row["waste_weight_g"] else 0,
                "production_time_hours": round(float(row["production_time_hours"]) if row["production_time_hours"] else 0, 2),
                "recorded_at": row["recorded_at"].isoformat() if row["recorded_at"] else None
            }

            orders_dict[order_id]["batches"].append(batch_data)
            orders_dict[order_id]["total_production_weight"] += batch_data["production_weight_g"]
            orders_dict[order_id]["total_waste_weight"] += batch_data["waste_weight_g"]
            orders_dict[order_id]["total_production_time"] += batch_data["production_time_hours"]

        # Round totals
        for order in orders_dict.values():
            order["total_production_time"] = round(order["total_production_time"], 2)

        return list(orders_dict.values())

    except Exception as e:
        logger.error(f"Error fetching plastic hangers detailed records: {str(e)}")
        raise

def calculate_efficiency(production_weight: float, waste_weight: float) -> float:
    """Calculate efficiency percentage"""
    if not production_weight and not waste_weight:
        return 0.0
    
    total_weight = production_weight + waste_weight
    if total_weight == 0:
        return 0.0
    
    return round((production_weight / total_weight) * 100, 2)

@router.get("/machines/summary", dependencies=[Depends(admin_or_manager)])
async def get_machines_summary(token: TokenData = Depends(admin_or_manager)):
    """
    Get summary of all registered machines grouped by production line and stage
    """
    conn = await connect_to_db()
    
    try:
        query = """
            SELECT 
                machine_id,
                production_line,
                machine_type,
                status,
                location
            FROM machines
            ORDER BY production_line, machine_type, machine_id
        """
        
        result = await conn.fetch(query)
        
        machines_summary = {
            "poly_bags": {
                "blowing_film": [],
                "printing": [],
                "cutting": []
            },
            "plastic_hangers": {
                "injection_molding": []
            }
        }
        
        for row in result:
            machine_info = {
                "machine_id": row["machine_id"],
                "production_line": row["production_line"],
                "machine_type": row["machine_type"],
                "status": row["status"],
                "location": row["location"]
            }
            
            # Categorize machines by type - match the naming from production_tracking
            if row["machine_type"] == "Blowing Film":
                machines_summary["poly_bags"]["blowing_film"].append(machine_info)
            elif row["machine_type"] == "Printing":
                machines_summary["poly_bags"]["printing"].append(machine_info)
            elif row["machine_type"] == "Cutting":
                machines_summary["poly_bags"]["cutting"].append(machine_info)
            elif row["machine_type"] == "Injection Molding":
                machines_summary["plastic_hangers"]["injection_molding"].append(machine_info)
        
        return machines_summary
        
    except Exception as e:
        logger.error(f"Error fetching machines summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching machines summary: {str(e)}")
    finally:
        await conn.close()

# Diagnostic endpoint to check timing data
@router.get("/machine-reports/diagnostic", dependencies=[Depends(admin_or_manager)])
async def diagnostic_timing_data(
    token: TokenData = Depends(admin_or_manager)
):
    """
    Diagnostic endpoint to check if timing data is being calculated correctly
    """
    conn = await connect_to_db()
    
    try:
        # Check sample data from machine_production_history
        sample_data = await conn.fetch("""
            SELECT 
                mph.*,
                jo.start_time,
                pr.roll_weight_ts,
                pr.printed_weight_ts,
                pr.cut_weight_ts,
                EXTRACT(EPOCH FROM (mph.recorded_at - jo.start_time)) / 3600.0 as hours_from_start
            FROM machine_production_history mph
            JOIN job_orders jo ON mph.order_id = jo.id
            LEFT JOIN production_rolls pr ON mph.order_id = pr.order_id AND mph.roll_index = pr.tmp_index
            ORDER BY mph.recorded_at DESC
            LIMIT 10
        """)
        
        # Check if timestamps exist
        timestamp_check = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(recorded_at) as has_recorded_at,
                COUNT(CASE WHEN recorded_at IS NOT NULL THEN 1 END) as valid_recorded_at,
                MIN(recorded_at) as earliest,
                MAX(recorded_at) as latest
            FROM machine_production_history
        """)
        
        return {
            "timestamp_check": dict(timestamp_check),
            "sample_records": [dict(row) for row in sample_data],
            "message": "Check if recorded_at timestamps are being saved properly in machine_production_history"
        }
        
    except Exception as e:
        logger.error(f"Error in diagnostic: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Diagnostic error: {str(e)}")
    finally:
        await conn.close()