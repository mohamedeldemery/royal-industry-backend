from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, field_validator, validator
from typing import List, Optional, Dict, Any, Union
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
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# Enums
class RecyclingStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class MaterialType(str, Enum):
    PLASTIC_ROLLS = "Plastic Rolls"
    POLY_BAGS = "Poly Bags"
    PLASTIC_HANGERS = "Plastic Hangers"
    OTHER = "Other"  # For manual entry

# Pydantic Models
class RecyclingLineBase(BaseModel):
    recycling_material_type: Union[MaterialType, str]  # Allow both enum and custom string
    material_type_custom: Optional[str] = None  # For custom material types
    input_weight: Decimal
    final_weight_recycled: Optional[Decimal] = None
    packaging_process_timestamp: Optional[datetime] = None
    count_packaged_bags: int = 0
    status: RecyclingStatus = RecyclingStatus.IN_PROGRESS

    @field_validator('recycling_material_type')
    @classmethod
    def validate_material_type(cls, v, values):
        # If material type is "Other", custom type must be provided
        if v == MaterialType.OTHER and not values.data.get('material_type_custom'):
            raise ValueError('Custom material type must be provided when selecting "Other"')
        return v

    @field_validator('material_type_custom')
    @classmethod
    def validate_custom_material(cls, v, values):
        # Custom material should only be provided when type is "Other"
        material_type = values.data.get('recycling_material_type')
        if material_type != MaterialType.OTHER and v:
            raise ValueError('Custom material type should only be provided when material type is "Other"')
        if v and len(v.strip()) == 0:
            raise ValueError('Custom material type cannot be empty')
        return v.strip() if v else v

    @field_validator('input_weight')
    @classmethod
    def validate_input_weight(cls, v):
        if v <= 0:
            raise ValueError('Input weight must be greater than 0')
        return v

    @field_validator('final_weight_recycled')
    @classmethod
    def validate_final_weight(cls, v):
        if v is not None and v < 0:
            raise ValueError('Final weight cannot be negative')
        return v

    @field_validator('count_packaged_bags')
    @classmethod
    def validate_bag_count(cls, v):
        if v < 0:
            raise ValueError('Bag count cannot be negative')
        return v

class RecyclingLineCreateSimplified(BaseModel):
    material_type: str  # Single field for both predefined and custom types
    input_weight: float
    
    @validator('material_type')
    def validate_material_type(cls, v):
        if not v or not v.strip():
            raise ValueError('Material type cannot be empty')
        return v.strip()


class RecyclingLineUpdate(BaseModel):
    recycling_material_type: Optional[Union[MaterialType, str]] = None
    material_type_custom: Optional[str] = None
    input_weight: Optional[Decimal] = None
    final_weight_recycled: Optional[Decimal] = None
    packaging_process_timestamp: Optional[datetime] = None
    count_packaged_bags: Optional[int] = None
    status: Optional[RecyclingStatus] = None

    @field_validator('recycling_material_type')
    @classmethod
    def validate_material_type(cls, v, values):
        if v == MaterialType.OTHER and not values.data.get('material_type_custom'):
            raise ValueError('Custom material type must be provided when selecting "Other"')
        return v

    @field_validator('input_weight')
    @classmethod
    def validate_input_weight(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Input weight must be greater than 0')
        return v

    @field_validator('final_weight_recycled')
    @classmethod
    def validate_final_weight(cls, v):
        if v is not None and v < 0:
            raise ValueError('Final weight cannot be negative')
        return v

class RecyclingLineResponse(BaseModel):
    id: int
    material_type: str
    input_weight: float
    created_at: datetime
    
    @classmethod
    def from_db_row(cls, row):
        return cls(
            id=row['id'],
            material_type=row['recycling_material_type'],  # Map from DB column name
            input_weight=float(row['input_weight']),  # Convert Decimal to float
            created_at=row['created_at']
        )

    class Config:
        from_attributes = True


class RecyclingSummary(BaseModel):
    recycling_date: date
    total_batches: int
    total_input_weight: Decimal
    total_recycled_weight: Optional[Decimal]
    avg_efficiency: Optional[Decimal]
    total_bags: int
class RecyclingLineFullResponse(BaseModel):
    id: int
    material_type: str
    input_weight: float
    timestamp_start: datetime
    final_weight_recycled: Optional[float] = None
    packaging_process_timestamp: Optional[datetime] = None
    calculated_recycling_time: Optional[str] = None  # Formatted as HH:MM:SS
    count_packaged_bags: int
    status: str
    efficiency_percentage: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_db_row(cls, row):
        # Handle timedelta conversion to string
        recycling_time_str = None
        if row['calculated_recycling_time'] is not None:
            td = row['calculated_recycling_time']
            if isinstance(td, timedelta):
                total_seconds = int(td.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                recycling_time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                recycling_time_str = str(td)
        
        return cls(
            id=row['id'],
            material_type=row['recycling_material_type'],
            input_weight=float(row['input_weight']),
            timestamp_start=row['timestamp_start'],
            final_weight_recycled=float(row['final_weight_recycled']) if row['final_weight_recycled'] is not None else None,
            packaging_process_timestamp=row['packaging_process_timestamp'],
            calculated_recycling_time=recycling_time_str,
            count_packaged_bags=row['count_packaged_bags'],
            status=row['status'],
            efficiency_percentage=float(row['efficiency_percentage']) if row['efficiency_percentage'] is not None else None,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    class Config:
        from_attributes = True
# Router
router = APIRouter(prefix="/api/recycling", tags=["Recycling Line"])

@router.post("/", response_model=RecyclingLineResponse)
async def create_recycling_batch(
    recycling_data: RecyclingLineCreateSimplified,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Create a new recycling batch with automatic ID and timestamp assignment"""
    try:
        conn = await connect_to_db()
        try:
            # Insert with automatic ID and timestamp
            # Store the material_type directly as provided by frontend
            query = """
                INSERT INTO recycling_line (
                    recycling_material_type, 
                    input_weight
                ) VALUES ($1, $2)
                RETURNING id, recycling_material_type, input_weight, created_at
            """
            
            row = await conn.fetchrow(
                query,
                recycling_data.material_type,
                recycling_data.input_weight
            )
            
            return RecyclingLineResponse.from_db_row(row)
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/", response_model=List[RecyclingLineFullResponse])
async def get_recycling_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[RecyclingStatus] = None,
    material_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get recycling batches with all details and optional filters"""
    try:
        conn = await connect_to_db()
        try:
            # Build dynamic query
            conditions = []
            params = []
            param_count = 0
            
            if status:
                param_count += 1
                conditions.append(f"status = ${param_count}")
                params.append(status.value)
            
            if material_type:
                param_count += 1
                conditions.append(f"recycling_material_type ILIKE ${param_count}")
                params.append(f"%{material_type}%")  # Use ILIKE for partial matching
            
            if date_from:
                param_count += 1
                conditions.append(f"DATE(timestamp_start) >= ${param_count}")
                params.append(date_from)
            
            if date_to:
                param_count += 1
                conditions.append(f"DATE(timestamp_start) <= ${param_count}")
                params.append(date_to)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            query = f"""
                SELECT 
                    id, recycling_material_type, input_weight, timestamp_start,
                    final_weight_recycled, packaging_process_timestamp, 
                    calculated_recycling_time, count_packaged_bags, status,
                    efficiency_percentage, created_at, updated_at
                FROM recycling_line
                {where_clause}
                ORDER BY timestamp_start DESC
                LIMIT ${param_count + 1} OFFSET ${param_count + 2}
            """
            params.extend([limit, skip])
            
            rows = await conn.fetch(query, *params)
            return [RecyclingLineFullResponse.from_db_row(row) for row in rows]
        finally:
            await conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/{batch_id}", response_model=RecyclingLineFullResponse)
async def get_recycling_batch(
    batch_id: int,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get a specific recycling batch by ID with all details"""
    try:
        conn = await connect_to_db()
        try:
            query = """
                SELECT 
                    id, recycling_material_type, input_weight, timestamp_start,
                    final_weight_recycled, packaging_process_timestamp, 
                    calculated_recycling_time, count_packaged_bags, status,
                    efficiency_percentage, created_at, updated_at
                FROM recycling_line 
                WHERE id = $1
            """
            row = await conn.fetchrow(query, batch_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Recycling batch not found")
            
            return RecyclingLineFullResponse.from_db_row(row)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Optional: Keep the simplified response model for the create endpoint
@router.post("/", response_model=RecyclingLineResponse)  # Keep simple response for create
async def create_recycling_batch(
    recycling_data: RecyclingLineCreateSimplified,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Create a new recycling batch with automatic ID and timestamp assignment"""
    try:
        conn = await connect_to_db()
        try:
            query = """
                INSERT INTO recycling_line (
                    recycling_material_type, 
                    input_weight
                ) VALUES ($1, $2)
                RETURNING id, recycling_material_type, input_weight, created_at
            """
            
            row = await conn.fetchrow(
                query,
                recycling_data.material_type,
                recycling_data.input_weight
            )
            
            return RecyclingLineResponse.from_db_row(row)
            
        finally:
            await conn.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/{batch_id}", response_model=RecyclingLineResponse)
async def update_recycling_batch(
    batch_id: int,
    recycling_data: RecyclingLineUpdate,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Update a recycling batch"""
    try:
        conn = await connect_to_db()
        try:
            # Check if batch exists
            existing = await conn.fetchrow("SELECT * FROM recycling_line WHERE id = $1", batch_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Recycling batch not found")
            
            # Build dynamic update query
            update_fields = []
            params = []
            param_count = 0
            
            update_data = recycling_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                if value is not None:
                    param_count += 1
                    if field == 'recycling_material_type':
                        # Handle material type updates
                        if value == MaterialType.OTHER:
                            # Use custom material type if provided
                            material_value = update_data.get('material_type_custom', 'Other')
                        elif hasattr(value, 'value'):
                            material_value = value.value
                        else:
                            material_value = str(value)
                        update_fields.append(f"recycling_material_type = ${param_count}")
                        params.append(material_value)
                    elif field == 'material_type_custom':
                        # Skip this field as it's handled with recycling_material_type
                        param_count -= 1
                        continue
                    elif field == 'status':
                        update_fields.append(f"{field} = ${param_count}")
                        params.append(value.value if hasattr(value, 'value') else str(value))
                    else:
                        update_fields.append(f"{field} = ${param_count}")
                        params.append(value)
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            params.append(batch_id)
            query = f"""
                UPDATE recycling_line 
                SET {', '.join(update_fields)}
                WHERE id = ${param_count + 1}
                RETURNING *
            """
            
            row = await conn.fetchrow(query, *params)
            return RecyclingLineResponse.from_db_row(row)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.delete("/{batch_id}")
async def delete_recycling_batch(
    batch_id: int,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Delete a recycling batch"""
    try:
        conn = await connect_to_db()
        try:
            result = await conn.execute("DELETE FROM recycling_line WHERE id = $1", batch_id)
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Recycling batch not found")
            
            return {"message": "Recycling batch deleted successfully"}
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/{batch_id}/complete")
async def complete_recycling_batch(
    batch_id: int,
    final_weight: Decimal,
    bag_count: int,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Mark a recycling batch as completed"""
    try:
        conn = await connect_to_db()
        try:
            query = """
                UPDATE recycling_line 
                SET final_weight_recycled = $1,
                    count_packaged_bags = $2,
                    packaging_process_timestamp = CURRENT_TIMESTAMP,
                    status = 'COMPLETED'
                WHERE id = $3 AND status = 'IN_PROGRESS'
                RETURNING *
            """
            
            row = await conn.fetchrow(query, final_weight, bag_count, batch_id)
            if not row:
                raise HTTPException(
                    status_code=404, 
                    detail="Recycling batch not found or already completed"
                )
            
            return RecyclingLineResponse.from_db_row(row)
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/summary/daily", response_model=List[RecyclingSummary])
async def get_daily_summary(
    days: int = Query(7, ge=1, le=365),
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get daily recycling summary for the last N days"""
    try:
        conn = await connect_to_db()
        try:
            query = """
                SELECT 
                    DATE(timestamp_start) as recycling_date,
                    COUNT(*)::int as total_batches,
                    SUM(input_weight) as total_input_weight,
                    SUM(final_weight_recycled) as total_recycled_weight,
                    AVG(efficiency_percentage) as avg_efficiency,
                    SUM(count_packaged_bags)::int as total_bags
                FROM recycling_line 
                WHERE timestamp_start >= CURRENT_DATE - INTERVAL '%s days'
                GROUP BY DATE(timestamp_start)
                ORDER BY recycling_date DESC
            """ % days
            
            rows = await conn.fetch(query)
            return [RecyclingSummary(**dict(row)) for row in rows]
        finally:
            await conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/export/csv")
async def export_to_csv(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    token_data: TokenData = Depends(admin_or_manager)
):
    """Export recycling data to CSV"""
    try:
        conn = await connect_to_db()
        try:
            conditions = []
            params = []
            
            if date_from:
                conditions.append("DATE(timestamp_start) >= $1")
                params.append(date_from)
            
            if date_to:
                param_num = len(params) + 1
                conditions.append(f"DATE(timestamp_start) <= ${param_num}")
                params.append(date_to)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            query = f"""
                SELECT 
                    id, recycling_material_type, input_weight, final_weight_recycled,
                    timestamp_start, packaging_process_timestamp, calculated_recycling_time,
                    count_packaged_bags, efficiency_percentage, status
                FROM recycling_line
                {where_clause}
                ORDER BY timestamp_start DESC
            """
            
            rows = await conn.fetch(query, *params)
            
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'ID', 'Material Type', 'Input Weight (kg)', 'Final Weight (kg)',
                'Start Time', 'Packaging Time', 'Recycling Duration',
                'Packaged Bags', 'Efficiency %', 'Status'
            ])
            
            # Write data
            for row in rows:
                writer.writerow([
                    row['id'],
                    row['recycling_material_type'],
                    row['input_weight'],
                    row['final_weight_recycled'],
                    row['timestamp_start'],
                    row['packaging_process_timestamp'],
                    row['calculated_recycling_time'],
                    row['count_packaged_bags'],
                    row['efficiency_percentage'],
                    row['status']
                ])
            
            output.seek(0)
            
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=recycling_data.csv"}
            )
        finally:
            await conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/stats/overview")
async def get_overview_stats(
    token_data: TokenData = Depends(admin_or_manager)
):
    """Get overview statistics for the recycling line"""
    try:
        conn = await connect_to_db()
        try:
            query = """
                SELECT 
                    COUNT(*) as total_batches,
                    COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') as active_batches,
                    COUNT(*) FILTER (WHERE status = 'COMPLETED') as completed_batches,
                    SUM(input_weight) as total_input_weight,
                    SUM(final_weight_recycled) as total_recycled_weight,
                    AVG(efficiency_percentage) as avg_efficiency,
                    SUM(count_packaged_bags) as total_bags_produced,
                    COUNT(*) FILTER (WHERE DATE(timestamp_start) = CURRENT_DATE) as today_batches
                FROM recycling_line
                WHERE timestamp_start >= CURRENT_DATE - INTERVAL '30 days'
            """
            
            row = await conn.fetchrow(query)
            return dict(row)
        finally:
            await conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")