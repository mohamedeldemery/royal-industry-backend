from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from typing import List, Optional
import asyncpg

DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)
from routers.employees import admin_only, admin_or_manager, TokenData

router = APIRouter(prefix="/api/waste-management", tags=["Waste Management"])
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

# Updated Models
class WasteData(BaseModel):
    machine_id: str
    job_order_id: int
    index_number: int  # Added index_number
    waste_amount_g: float
    waste_type: str
    waste_date: date

class WasteSummary(BaseModel):
    machine_id: str
    waste_date: date
    total_waste_g: float
    total_orders: int
    avg_waste_per_order_g: float

# Synchronize waste data from production tables to waste management tables
@router.post("/sync-waste-data", status_code=201)
async def sync_waste_data(current_user: TokenData = Depends(admin_or_manager)):
    """
    Synchronize waste data from production tables to waste management tables.
    This endpoint is restricted to admin and manager users.
    """
    conn = await connect_to_db()
    try:
        # Get all job_order_machines entries
        job_orders = await conn.fetch(
            "SELECT job_order_id, machine_id FROM job_order_machines"
        )
        
        waste_entries = 0
        
        for job in job_orders:
            machine_id = job['machine_id']
            job_order_id = job['job_order_id']
            
            # Process based on machine type
            if machine_id.startswith(('BF', 'P', 'C')):
                # Get data from production_rolls for ALL indices
                production_data = await conn.fetch(
                    """
                    SELECT 
                        tmp_index,
                        waste_of_blowing_g, 
                        waste_of_printing_g, 
                        waste_of_cutting_g,
                        created_at
                    FROM production_rolls 
                    WHERE order_id = $1
                    """, 
                    job_order_id
                )
                
                for roll_data in production_data:
                    tmp_index = roll_data['tmp_index']
                    waste_date = roll_data['created_at'].date()
                    
                    # Process blowing film waste
                    if machine_id.startswith('BF') and roll_data['waste_of_blowing_g']:
                        await insert_waste_data(
                            conn, machine_id, job_order_id, tmp_index,
                            roll_data['waste_of_blowing_g'], 
                            'blowing', waste_date, current_user
                        )
                        waste_entries += 1
                        
                    # Process printing waste
                    if machine_id.startswith('P') and roll_data['waste_of_printing_g']:
                        await insert_waste_data(
                            conn, machine_id, job_order_id, tmp_index,
                            roll_data['waste_of_printing_g'], 
                            'printing', waste_date, current_user
                        )
                        waste_entries += 1
                        
                    # Process cutting waste
                    if machine_id.startswith('C') and roll_data['waste_of_cutting_g']:
                        await insert_waste_data(
                            conn, machine_id, job_order_id, tmp_index,
                            roll_data['waste_of_cutting_g'], 
                            'cutting', waste_date, current_user
                        )
                        waste_entries += 1
                        
            elif machine_id.startswith('IM'):
                # Get data from production_hangers for ALL batches
                production_data = await conn.fetch(
                    """
                    SELECT 
                        batch_index,
                        waste_of_im_g,
                        created_at
                    FROM production_hangers 
                    WHERE order_id = $1
                    """, 
                    job_order_id
                )
                
                for hanger_data in production_data:
                    if hanger_data['waste_of_im_g']:
                        batch_index = hanger_data['batch_index']
                        waste_date = hanger_data['created_at'].date()
                        await insert_waste_data(
                            conn, machine_id, job_order_id, batch_index,
                            hanger_data['waste_of_im_g'], 
                            'injection_molding', waste_date, current_user
                        )
                        waste_entries += 1
                    
        await conn.close()
        return {"message": f"Successfully synchronized {waste_entries} waste records"}
    
    except Exception as e:
        await conn.close()
        raise HTTPException(status_code=500, detail=f"Error synchronizing waste data: {str(e)}")

# Updated helper function to insert waste data with index
async def insert_waste_data(conn, machine_id, job_order_id, index_number, waste_amount, waste_type, waste_date, current_user):
    """Helper function to insert waste data with conflict handling"""
    try:
        await conn.execute(
            """
            INSERT INTO machine_waste 
                (machine_id, job_order_id, index_number, waste_amount_g, waste_type, waste_date, recorded_by)
            VALUES 
                ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (machine_id, job_order_id, index_number, waste_type, waste_date) 
            DO UPDATE SET 
                waste_amount_g = $4,
                waste_timestamp = CURRENT_TIMESTAMP,
                recorded_by = $7
            """,
            machine_id, job_order_id, index_number, waste_amount, waste_type, waste_date, 
            int(current_user.sub) if hasattr(current_user, 'sub') else None
        )
    except Exception as e:
        # Log error but continue processing other records
        print(f"Error inserting waste data: {str(e)}")

# Get waste data by machine
@router.get("/machine/{machine_id}", response_model=List[WasteData])
async def get_machine_waste(
    machine_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: TokenData = Depends(admin_or_manager)
):
    """
    Get waste data for a specific machine within a date range.
    This endpoint is restricted to admin and manager users.
    """
    conn = await connect_to_db()
    try:
        query = "SELECT machine_id, job_order_id, index_number, waste_amount_g, waste_type, waste_date FROM machine_waste WHERE machine_id = $1"
        params = [machine_id]
        
        if start_date:
            query += " AND waste_date >= $" + str(len(params) + 1)
            params.append(start_date)
            
        if end_date:
            query += " AND waste_date <= $" + str(len(params) + 1)
            params.append(end_date)
            
        query += " ORDER BY waste_date DESC, waste_timestamp DESC"
        
        results = await conn.fetch(query, *params)
        await conn.close()
        
        return [
            WasteData(
                machine_id=row['machine_id'],
                job_order_id=row['job_order_id'],
                index_number=row['index_number'],
                waste_amount_g=float(row['waste_amount_g']),
                waste_type=row['waste_type'],
                waste_date=row['waste_date']
            ) for row in results
        ]
    except Exception as e:
        await conn.close()
        raise HTTPException(status_code=500, detail=f"Error retrieving machine waste data: {str(e)}")

# Get daily waste summaries (no changes needed)
@router.get("/daily-summary", response_model=List[WasteSummary])
async def get_daily_waste_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    machine_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(admin_or_manager)
):
    """
    Get daily waste summaries within a date range, optionally filtered by machine.
    This endpoint is restricted to admin and manager users.
    """
    conn = await connect_to_db()
    try:
        query = "SELECT machine_id, waste_date, total_waste_g, total_orders, avg_waste_per_order_g FROM daily_waste_summary WHERE 1=1"
        params = []
        
        if machine_id:
            query += " AND machine_id = $" + str(len(params) + 1)
            params.append(machine_id)
            
        if start_date:
            query += " AND waste_date >= $" + str(len(params) + 1)
            params.append(start_date)
            
        if end_date:
            query += " AND waste_date <= $" + str(len(params) + 1)
            params.append(end_date)
            
        query += " ORDER BY waste_date DESC, machine_id"
        
        results = await conn.fetch(query, *params)
        await conn.close()
        
        return [
            WasteSummary(
                machine_id=row['machine_id'],
                waste_date=row['waste_date'],
                total_waste_g=float(row['total_waste_g']),
                total_orders=row['total_orders'],
                avg_waste_per_order_g=float(row['avg_waste_per_order_g'])
            ) for row in results
        ]
    except Exception as e:
        await conn.close()
        raise HTTPException(status_code=500, detail=f"Error retrieving daily waste summary: {str(e)}")

# Get waste data for a specific order - updated to include index info
@router.get("/order/{job_order_id}", response_model=List[WasteData])
async def get_order_waste(
    job_order_id: int,
    current_user: TokenData = Depends(admin_or_manager)
):
    """
    Get waste data for a specific job order across all machines and indices.
    This endpoint is restricted to admin and manager users.
    """
    conn = await connect_to_db()
    try:
        query = """
        SELECT 
            machine_id, 
            job_order_id,
            index_number,
            waste_amount_g, 
            waste_type, 
            waste_date 
        FROM machine_waste 
        WHERE job_order_id = $1
        ORDER BY waste_date DESC, machine_id, index_number
        """
        
        results = await conn.fetch(query, job_order_id)
        await conn.close()
        
        return [
            WasteData(
                machine_id=row['machine_id'],
                job_order_id=row['job_order_id'],
                index_number=row['index_number'],
                waste_amount_g=float(row['waste_amount_g']),
                waste_type=row['waste_type'],
                waste_date=row['waste_date']
            ) for row in results
        ]
    except Exception as e:
        await conn.close()
        raise HTTPException(status_code=500, detail=f"Error retrieving order waste data: {str(e)}")

# New endpoint: Get waste summary by order index
@router.get("/order/{job_order_id}/indices-summary")
async def get_order_indices_summary(
    job_order_id: int,
    current_user: TokenData = Depends(admin_or_manager)
):
    """
    Get summarized waste data for each index within a specific job order.
    This endpoint is restricted to admin and manager users.
    """
    conn = await connect_to_db()
    try:
        query = """
        SELECT 
            index_number,
            SUM(waste_amount_g) AS total_waste_g,
            array_agg(DISTINCT waste_type) AS waste_types,
            COUNT(DISTINCT machine_id) AS machines_involved,
            MIN(waste_date) AS first_recorded_date,
            MAX(waste_date) AS last_recorded_date
        FROM machine_waste 
        WHERE job_order_id = $1
        GROUP BY index_number
        ORDER BY index_number
        """
        
        results = await conn.fetch(query, job_order_id)
        await conn.close()
        
        return [dict(row) for row in results]
    except Exception as e:
        await conn.close()
        raise HTTPException(status_code=500, detail=f"Error retrieving order indices summary: {str(e)}")

# New endpoint: Compare waste between indices
@router.get("/indices-comparison")
async def compare_indices_waste(
    current_user: TokenData = Depends(admin_or_manager)
):
    """
    Compare waste efficiency across different indices (batch runs).
    This endpoint is restricted to admin and manager users.
    """
    conn = await connect_to_db()
    try:
        # Analyze waste by index number for similar order types
        query = """
        WITH order_types AS (
            SELECT DISTINCT job_order_id, 
                CASE 
                    WHEN machine_id LIKE 'BF%' OR machine_id LIKE 'P%' OR machine_id LIKE 'C%' THEN 'rolls'
                    WHEN machine_id LIKE 'IM%' THEN 'hangers'
                    ELSE 'other'
                END AS product_type
            FROM machine_waste
        )
        SELECT 
            ot.product_type,
            mw.job_order_id,
            mw.index_number,
            SUM(mw.waste_amount_g) AS total_waste_g,
            AVG(mw.waste_amount_g) OVER (
                PARTITION BY ot.product_type, mw.job_order_id
            ) AS avg_waste_per_index_g,
            SUM(mw.waste_amount_g) - AVG(mw.waste_amount_g) OVER (
                PARTITION BY ot.product_type, mw.job_order_id
            ) AS deviation_from_avg_g,
            CASE 
                WHEN AVG(mw.waste_amount_g) OVER (PARTITION BY ot.product_type, mw.job_order_id) > 0 THEN
                    ROUND(((SUM(mw.waste_amount_g) / AVG(mw.waste_amount_g) OVER (
                        PARTITION BY ot.product_type, mw.job_order_id
                    )) - 1) * 100, 2)
                ELSE 0
            END AS percent_deviation
        FROM 
            machine_waste mw
        JOIN 
            order_types ot ON mw.job_order_id = ot.job_order_id
        GROUP BY 
            ot.product_type, mw.job_order_id, mw.index_number
        ORDER BY 
            ot.product_type, mw.job_order_id, mw.index_number
        """
        
        results = await conn.fetch(query)
        await conn.close()
        
        return [dict(row) for row in results]
    except Exception as e:
        await conn.close()
        raise HTTPException(status_code=500, detail=f"Error comparing indices waste: {str(e)}")