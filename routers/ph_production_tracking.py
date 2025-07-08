# routers/ph_production_tracking.py
from enum import Enum
from typing import List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, NonNegativeInt
from datetime import datetime
from fastapi.responses import JSONResponse
from routers.employees import admin_or_manager, TokenData

router = APIRouter(tags=["ph-production-tracking"])

DB_URL = "postgresql://postgres:tGMQdkuBjfHViJgVAPzbodCTFZHrvtEJ@postgres.railway.internal:5432/railway"

# ──────────────────────────────────────────────────────────
# 3. Domain model
# ──────────────────────────────────────────────────────────
class PHStage(str, Enum):
    INJECTION     = "INJECTION"
    WEIGHING      = "WEIGHING"
    METAL_DETECT  = "METAL_DETECT"
    SIZING        = "SIZING"
    PLASTIC_CLIPS = "PLASTIC_CLIPS"
    METAL_CLIPS   = "METAL_CLIPS"
    PACKAGING     = "PACKAGING"


# Valid stage sequences based on model and raw_degree
FLOW_PH_WT19 = [
    PHStage.INJECTION, 
    PHStage.WEIGHING, 
    PHStage.SIZING, 
    PHStage.PACKAGING
]

FLOW_PH_WT19_2ND = [
    PHStage.INJECTION, 
    PHStage.WEIGHING, 
    PHStage.METAL_DETECT,
    PHStage.SIZING, 
    PHStage.PACKAGING
]

FLOW_PH_OTHER = [
    PHStage.INJECTION, 
    PHStage.WEIGHING, 
    PHStage.SIZING, 
    PHStage.PLASTIC_CLIPS, 
    PHStage.METAL_CLIPS, 
    PHStage.PACKAGING
]

FLOW_PH_OTHER_2ND = [
    PHStage.INJECTION, 
    PHStage.WEIGHING, 
    PHStage.METAL_DETECT,
    PHStage.SIZING, 
    PHStage.PLASTIC_CLIPS, 
    PHStage.METAL_CLIPS, 
    PHStage.PACKAGING
]


def allowed_ph_flow(model: Optional[str], raw_degree: Optional[str]) -> List[PHStage]:
    """
    Determine the production flow based on hanger model and raw_degree
    
    - METAL_DETECT is only needed for 2nd Degree raw material
    - WT-19 doesn't need plastic or metal clips
    """
    is_second_degree = raw_degree == "2nd Degree"
    is_wt19 = model and "WT-19" in model
    
    if is_wt19:
        return FLOW_PH_WT19_2ND if is_second_degree else FLOW_PH_WT19
    else:
        return FLOW_PH_OTHER_2ND if is_second_degree else FLOW_PH_OTHER


# Updated Pydantic models for PH machine tracking

class HangerCreate(BaseModel):
    weight_g: int = Field(..., ge=1)
    waste_of_im_g: Optional[int] = Field(None, ge=0)
    injection_machine_id: str = Field(..., description="Injection molding machine ID that produced this batch")

class HangerUpdate(BaseModel):
    stage: Optional[PHStage] = None
    weight_g: Optional[NonNegativeInt] = None
    waste_of_metaldetect_g: Optional[NonNegativeInt] = None
    
    # Machine IDs for stages that use machines
    injection_machine_id: Optional[str] = None
    metal_detect_machine_id: Optional[str] = None

class HangerOut(BaseModel):
    id: int
    order_id: int
    batch_index: int
    stage: PHStage
    model: Optional[str] = None

    # Weight measurements with timestamps
    injection_weight_g: Optional[int] = None
    injection_weight_ts: Optional[datetime] = None
    packaged_weight_g: Optional[int] = None
    packaged_weight_ts: Optional[datetime] = None
    
    # Waste weight measurements with timestamps
    waste_of_im_g: Optional[int] = None
    waste_of_im_ts: Optional[datetime] = None
    waste_of_metaldetect_g: Optional[int] = None
    waste_of_metaldetect_ts: Optional[datetime] = None
    
    # Machine IDs
    injection_machine_id: Optional[str] = None
    metal_detect_machine_id: Optional[str] = None
    
    # Timestamps for non-weight stages
    metal_detect_ts: Optional[datetime] = None
    sizing_ts: Optional[datetime] = None
    plastic_clips_ts: Optional[datetime] = None
    metal_clips_ts: Optional[datetime] = None

# New models for PH machine reports
class PHMachineProductionReport(BaseModel):
    machine_id: str
    machine_type: str
    production_line: str
    date_range: str
    total_production_kg: float
    total_waste_kg: float
    total_batches_produced: int
    orders_worked_on: List[int]
    efficiency_rate: float  # (production / (production + waste)) * 100

class PHMachineProductionDetail(BaseModel):
    order_id: int
    batch_index: int
    production_weight_kg: float
    waste_weight_kg: float
    timestamp: datetime

# ──────────────────────────────────────────────────────────
# 1. Helpers ─ DB connection + order look‑ups
# ──────────────────────────────────────────────────────────
async def get_db():
    conn = await asyncpg.connect(DB_URL)
    try:
        yield conn
    finally:
        await conn.close()


async def get_order_basic(order_id: int, db: asyncpg.Connection):
    """
    Returns {product, raw_degree, model} or raises 404.
    """
    row = await db.fetchrow(
        "SELECT product, raw_degree, model FROM job_orders WHERE id=$1",
        order_id,
    )
    if not row:
        raise HTTPException(404, "Job order not found")
    return row


async def ensure_ph_order(order_id: int, db: asyncpg.Connection = Depends(get_db)):
    """
    Allow only PH (plastic hangers).
    Returns (product_code:str, raw_degree:str, model:str)
    """
    row = await get_order_basic(order_id, db)
    if row["product"] != "PH":
        raise HTTPException(
            400,
            "This endpoint is only for Plastic Hangers (PH) orders.",
        )
    return row  # dependency return value


# Helper functions for PH machine validation and tracking

async def validate_ph_machine_assigned_to_order(
    machine_id: str, 
    order_id: int, 
    stage: PHStage, 
    db: asyncpg.Connection
) -> bool:
    """
    Validates that the machine is assigned to this order and is correct type for PH stage.
    """
    stage_to_machine_type = {
        PHStage.INJECTION: "Injection Molding",
        PHStage.METAL_DETECT: "Metal Detector"
    }
    
    expected_type = stage_to_machine_type.get(stage)
    if not expected_type:
        return False
    
    machine = await db.fetchrow(
        """
        SELECT machine_type, status, current_job_order 
        FROM machines 
        WHERE machine_id = $1
        """,
        machine_id
    )
    
    if not machine:
        return False
    
    return (
        machine["current_job_order"] == order_id and 
        machine["machine_type"] == expected_type and
        machine["status"] == "in_use"
    )

async def get_assigned_ph_machines_for_order_stage(
    order_id: int, 
    stage: PHStage, 
    db: asyncpg.Connection
) -> List[dict]:
    """
    Returns PH machines that are assigned to this order and are suitable for the given stage.
    """
    stage_to_machine_type = {
        PHStage.INJECTION: "Injection Molding",
        PHStage.METAL_DETECT: "Metal Detector"
    }
    
    machine_type = stage_to_machine_type.get(stage)
    if not machine_type:
        return []
    
    machines = await db.fetch(
        """
        SELECT machine_id, machine_type, production_line, status
        FROM machines 
        WHERE current_job_order = $1 
        AND machine_type = $2
        AND status = 'in_use'
        ORDER BY machine_id
        """,
        order_id, machine_type
    )
    
    return [dict(machine) for machine in machines]

async def check_ph_order_has_assigned_machines(order_id: int, db: asyncpg.Connection) -> dict:
    """
    Returns summary of machines assigned to a PH order by type.
    """
    machines = await db.fetch(
        """
        SELECT machine_id, machine_type, production_line
        FROM machines 
        WHERE current_job_order = $1 
        AND status = 'in_use'
        AND machine_type IN ('Injection Molding', 'Metal Detector')
        ORDER BY machine_type, machine_id
        """,
        order_id
    )
    
    # Group by machine type
    by_type = {}
    for machine in machines:
        machine_type = machine["machine_type"]
        if machine_type not in by_type:
            by_type[machine_type] = []
        by_type[machine_type].append({
            "machine_id": machine["machine_id"],
            "production_line": machine["production_line"]
        })
    
    return by_type

async def record_ph_machine_production(
    machine_id: str, 
    order_id: int, 
    batch_index: int, 
    stage: PHStage,
    production_weight_g: int,
    waste_weight_g: Optional[int],
    db: asyncpg.Connection
):
    """
    Records PH production data for machine reporting.
    """
    await db.execute(
        """
        INSERT INTO machine_production_history_ph 
        (machine_id, order_id, batch_index, stage, production_weight_g, waste_weight_g, recorded_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT (machine_id, order_id, batch_index, stage) 
        DO UPDATE SET 
            production_weight_g = EXCLUDED.production_weight_g,
            waste_weight_g = EXCLUDED.waste_weight_g,
            recorded_at = NOW()
        """,
        machine_id, order_id, batch_index, stage.value, production_weight_g, waste_weight_g
    )


# ──────────────────────────────────────────────────────────
# 2. Order‑completion synchroniser
# ──────────────────────────────────────────────────────────
async def force_release_injection_machines(order_id: int, db: asyncpg.Connection):
    """
    Forcefully release all injection molding machines assigned to an order.
    """
    # Get machines before update (for logging)
    machines_before = await db.fetch(
        """
        SELECT id, machine_id, status
        FROM machines
        WHERE current_job_order = $1 AND machine_type = 'Injection Molding'
        """,
        order_id
    )
    
    # Execute the update with no conditions
    result = await db.execute(
        """
        UPDATE machines
        SET status = 'available',
            current_job_order = NULL
        WHERE current_job_order = $1 AND machine_type = 'Injection Molding'
        """,
        order_id
    )
    
    # Verify and log the results
    if machines_before:
        machine_ids = ", ".join([m["machine_id"] for m in machines_before])
        print(f"FORCED RELEASE: Order {order_id} - Released injection machines: {machine_ids}")
    else:
        print(f"FORCED RELEASE: No injection machines found for order {order_id}")
    
    # Return number of machines released
    return len(machines_before)


async def check_order_completion(order_id: int, db: asyncpg.Connection):
    """Auto‑completes an order when packaged weight ≈ target."""
    jo = await db.fetchrow(
        """
        SELECT id, status, remaining_target_g,
               target_weight_no_waste,
               COALESCE((
                   SELECT SUM(packaged_weight_g) FROM production_hangers
                   WHERE order_id=$1 AND packaged_weight_g IS NOT NULL
               ),0) AS done_g
        FROM job_orders
        WHERE id=$1
        """,
        order_id,
    )
    if not jo:
        return False

    # If already completed, force-release any machines still assigned
    if jo["status"] == "completed":
        await force_release_injection_machines(order_id, db)
        return True

    target_g   = int(jo["target_weight_no_waste"] * 1000)
    remaining  = max(0, target_g - jo["done_g"])
    tol_g      = min(100, int(target_g * 0.01))  # ≤1 % or 100 g

    if remaining <= tol_g:
        async with db.transaction():
            # Calculate total waste before updating the order
            waste_totals = await db.fetchrow(
                """
                SELECT 
                    COALESCE(SUM(waste_of_im_g), 0) AS im_waste_g,
                    COALESCE(SUM(waste_of_metaldetect_g), 0) AS md_waste_g
                FROM production_hangers
                WHERE order_id=$1
                """,
                order_id,
            )
            
            total_waste = waste_totals["im_waste_g"] + waste_totals["md_waste_g"]
            
            # Update the order status and total_waste_g
            await db.execute(
                """
                UPDATE job_orders
                SET status='completed',
                    remaining_target_g=0,
                    completed_at = NOW(),
                    total_waste_g = $1
                WHERE id=$2
                """,
                total_waste, order_id,
            )
            
            # Then force-release all injection machines
            await force_release_injection_machines(order_id, db)
        
        return True

    # keep remaining_target_g in‑sync
    if remaining != jo["remaining_target_g"]:
        await db.execute(
            "UPDATE job_orders SET remaining_target_g=$1 WHERE id=$2",
            remaining, order_id
        )
    return False




# ──────────────────────────────────────────────────────────
# 4. POST  /hangers  (create)
# ──────────────────────────────────────────────────────────
@router.post(
    "/job_orders/{order_id}/hangers",
    response_model=HangerOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_or_manager)],
)
async def create_hanger_batch(
    order_id: int,
    payload: HangerCreate,
    meta=Depends(ensure_ph_order),
    db: asyncpg.Connection = Depends(get_db),
):
    if await check_order_completion(order_id, db):
        raise HTTPException(400, "Order completed – cannot add hanger batches.")

    # Validate the injection molding machine is assigned to this order
    if not await validate_ph_machine_assigned_to_order(
        payload.injection_machine_id, order_id, PHStage.INJECTION, db
    ):
        raise HTTPException(
            400, 
            f"Machine {payload.injection_machine_id} is not assigned to this order or not valid for injection molding stage"
        )

    next_ndx = await db.fetchval(
        "SELECT COALESCE(MAX(batch_index),0)+1 FROM production_hangers WHERE order_id=$1",
        order_id,
    )

    # Get model information
    model = meta["model"]

    # Build the query with machine tracking
    base_query = """
        INSERT INTO production_hangers
              (order_id, batch_index, stage, model,
               injection_weight_g, injection_weight_ts, injection_machine_id"""
    
    values_part = """ VALUES ($1, $2, $3, $4, $5, NOW(), $6"""
    
    query_params = [
        order_id,
        next_ndx,
        PHStage.INJECTION.value,
        model,
        payload.weight_g,
        payload.injection_machine_id,
    ]
    
    # Add waste of injection molding if provided
    if payload.waste_of_im_g is not None:
        base_query += ", waste_of_im_g, waste_of_im_ts"
        values_part += f", ${len(query_params) + 1}, NOW()"
        query_params.append(payload.waste_of_im_g)
    
    # Complete the query
    query = base_query + ")" + values_part + ") RETURNING *;"
    
    async with db.transaction():
        row = await db.fetchrow(query, *query_params)
        
        # Record machine production for reporting
        await record_ph_machine_production(
            payload.injection_machine_id,
            order_id,
            next_ndx,
            PHStage.INJECTION,
            payload.weight_g,
            payload.waste_of_im_g,
            db
        )
    
    return HangerOut.model_validate(dict(row))


# ──────────────────────────────────────────────────────────
# 5. PATCH /hangers/{id} (update stage / weight)
# ──────────────────────────────────────────────────────────
@router.patch(
    "/job_orders/{order_id}/hangers/{hanger_id}",
    response_model=HangerOut,
    dependencies=[Depends(admin_or_manager)],
)
async def update_hanger(
    order_id: int,
    hanger_id: int,
    payload: HangerUpdate,
    meta=Depends(ensure_ph_order),
    db: asyncpg.Connection = Depends(get_db),
):
    # Get model and raw_degree from job order
    model = meta["model"]
    raw_degree = meta["raw_degree"]
    flow = allowed_ph_flow(model, raw_degree)

    # Stop editing finished orders
    if await check_order_completion(order_id, db):
        raise HTTPException(400, "Order completed – hangers are frozen.")

    hanger = await db.fetchrow(
        "SELECT * FROM production_hangers WHERE id=$1 AND order_id=$2",
        hanger_id, order_id,
    )
    if not hanger:
        raise HTTPException(404, "Hanger batch not found")

    current_stage = PHStage(hanger["stage"])
    new_stage = payload.stage or current_stage

    # Validate stage transition
    try:
        cur_idx = flow.index(current_stage)
    except ValueError:
        raise HTTPException(400, "Internal flow inconsistency")

    if new_stage != current_stage:
        if new_stage not in flow:
            raise HTTPException(400, f"{new_stage} not valid for this model and raw degree")
        if flow.index(new_stage) != cur_idx + 1:
            raise HTTPException(400, "Stages must progress sequentially")

    # Validate machine for stages that require machines
    machine_field_map = {
        PHStage.INJECTION: 'injection_machine_id',
        PHStage.METAL_DETECT: 'metal_detect_machine_id'
    }
    
    stage_machine_id = getattr(payload, machine_field_map.get(new_stage, ''), None)
    if stage_machine_id and not await validate_ph_machine_assigned_to_order(
        stage_machine_id, order_id, new_stage, db
    ):
        raise HTTPException(
            400, 
            f"Machine {stage_machine_id} is not assigned to this order or not valid for {new_stage.value} stage"
        )

    # Build UPDATE clause
    sets, vals = [], []
    if new_stage != current_stage:
        sets.append(f"stage=$1")
        vals.append(new_stage.value)

    # Handle weight and machine assignment for weight-recording stages
    production_weight = None
    waste_weight = None
    
    if payload.weight_g is not None:
        val_index = len(vals) + 1
        production_weight = payload.weight_g
        
        if new_stage == PHStage.INJECTION:
            sets.append(f"injection_weight_g=${val_index}")
            sets.append("injection_weight_ts = NOW()")
            if payload.injection_machine_id:
                sets.append(f"injection_machine_id=${val_index + 1}")
                vals.append(payload.weight_g)
                vals.append(payload.injection_machine_id)
            else:
                vals.append(payload.weight_g)
                
        elif new_stage == PHStage.PACKAGING:
            sets.append(f"packaged_weight_g=${val_index}")
            sets.append("packaged_weight_ts = NOW()")
            vals.append(payload.weight_g)

    # Handle machine assignment without weight change
    if not payload.weight_g and stage_machine_id:
        val_index = len(vals) + 1
        sets.append(f"{machine_field_map[new_stage]}=${val_index}")
        vals.append(stage_machine_id)

    # Handle waste from Metal Detect during PACKAGING stage
    if new_stage == PHStage.PACKAGING and payload.waste_of_metaldetect_g is not None:
        val_index = len(vals) + 1
        sets.append(f"waste_of_metaldetect_g=${val_index}")
        sets.append("waste_of_metaldetect_ts = NOW()")
        vals.append(payload.waste_of_metaldetect_g)
        waste_weight = payload.waste_of_metaldetect_g

    # Handle timestamp-only stages
    if new_stage == PHStage.METAL_DETECT:
        sets.append("metal_detect_ts = NOW()")
        if payload.metal_detect_machine_id:
            val_index = len(vals) + 1
            sets.append(f"metal_detect_machine_id=${val_index}")
            vals.append(payload.metal_detect_machine_id)
    elif new_stage == PHStage.SIZING:
        sets.append("sizing_ts = NOW()")
    elif new_stage == PHStage.PLASTIC_CLIPS:
        sets.append("plastic_clips_ts = NOW()")
    elif new_stage == PHStage.METAL_CLIPS:
        sets.append("metal_clips_ts = NOW()")

    # Always stamp update time
    sets.append("updated_at = NOW()")

    if not vals and len(sets) == 1:  # only updated_at
        return HangerOut.model_validate(dict(hanger))

    # Positional parameters: stage/weight ... then ids
    vals.extend([hanger_id, order_id])

    query = f"""
        UPDATE production_hangers
           SET {', '.join(sets)}
         WHERE id = ${len(vals)-1} AND order_id = ${len(vals)}
     RETURNING *;
    """
    
    async with db.transaction():
        updated = await db.fetchrow(query, *vals)
        if not updated:
            raise HTTPException(404, "Update failed")
        
        # Record machine production for reporting if we have weight and machine
        if production_weight and stage_machine_id:
            await record_ph_machine_production(
                stage_machine_id,
                order_id,
                hanger["batch_index"],
                new_stage,
                production_weight,
                waste_weight,
                db
            )

        # After PACKAGING weight → deduct from remaining_target_g
        if new_stage == PHStage.PACKAGING and payload.weight_g is not None:
            delta = payload.weight_g - (hanger["packaged_weight_g"] or 0)
            if delta:
                await db.execute(
                    """
                    UPDATE job_orders
                       SET remaining_target_g = GREATEST(0, remaining_target_g - $1)
                     WHERE id = $2
                    """,
                    delta, order_id,
                )

    # Sync completion
    await check_order_completion(order_id, db)
    return HangerOut.model_validate(dict(updated))

# ──────────────────────────────────────────────────────────
# 6. GET /job_orders/{id}/ph-status
# ──────────────────────────────────────────────────────────
@router.get(
    "/job_orders/{order_id}/ph-status",
    dependencies=[Depends(admin_or_manager)],
)
async def get_ph_status(
    order_id: int, 
    meta=Depends(ensure_ph_order),
    db: asyncpg.Connection = Depends(get_db)
):
    await check_order_completion(order_id, db)

    status_row = await db.fetchrow(
        """
        SELECT id,
               status,
               product,
               raw_degree,
               model,
               target_weight_no_waste,
               remaining_target_g,
               total_waste_g,
               COALESCE((
                   SELECT SUM(packaged_weight_g)
                   FROM   production_hangers
                   WHERE  order_id = $1
                     AND  packaged_weight_g IS NOT NULL
               ),0) AS done_g
        FROM job_orders
        WHERE id=$1
        """,
        order_id,
    )
    if not status_row:
        raise HTTPException(404, "Job order not found")

    tgt = int(status_row["target_weight_no_waste"] * 1000)
    done = status_row["done_g"]
    pct = round(done / tgt * 100, 2) if tgt else 0
    
    # Get waste totals from production_hangers
    waste_totals = await db.fetchrow(
        """
        SELECT 
            COALESCE(SUM(waste_of_im_g), 0) AS im_waste_g,
            COALESCE(SUM(waste_of_metaldetect_g), 0) AS md_waste_g
        FROM production_hangers
        WHERE order_id = $1
        """,
        order_id
    )
    
    # Calculate current waste
    im_waste = waste_totals["im_waste_g"]
    md_waste = waste_totals["md_waste_g"]
    
    # For completed orders, use the stored total_waste_g
    # For in-progress orders, calculate the total
    if status_row["status"] == "completed":
        total_waste = status_row["total_waste_g"]
    else:
        total_waste = im_waste + md_waste
    
    # Get counts by stage
    stage_counts = await db.fetch(
        """
        SELECT stage, COUNT(*) as count
        FROM production_hangers
        WHERE order_id = $1
        GROUP BY stage
        """,
        order_id
    )
    
    # Convert to dictionary
    stages = {row["stage"]: row["count"] for row in stage_counts}
    
    # Get model and raw_degree information
    model = status_row["model"]
    raw_degree = status_row["raw_degree"]
    flow = [stage.value for stage in allowed_ph_flow(model, raw_degree)]

    return {
        "order_id": status_row["id"],
        "status": status_row["status"],
        "model": model,
        "raw_degree": raw_degree,
        "flow": flow,
        "target_g": tgt,
        "done_g": done,
        "remaining_g": status_row["remaining_target_g"],
        "completion_%": pct,
        "waste": {
            "injection_molding_waste_g": im_waste,
            "metal_detect_waste_g": md_waste,
            "total_waste_g": total_waste
        },
        "stages": stages
    }
# ──────────────────────────────────────────────────────────
# 7. GET hangers list
# ──────────────────────────────────────────────────────────
@router.get(
    "/job_orders/{order_id}/hangers",
    response_model=List[HangerOut],
    dependencies=[Depends(admin_or_manager)],
)
async def list_hangers(
    order_id: int, 
    meta=Depends(ensure_ph_order),
    db: asyncpg.Connection = Depends(get_db)
):
    await check_order_completion(order_id, db)
    rows = await db.fetch(
        "SELECT * FROM production_hangers WHERE order_id=$1 ORDER BY id",
        order_id,
    )
    return [HangerOut.model_validate(dict(r)) for r in rows]


# ──────────────────────────────────────────────────────────
# 8. One-time fix endpoint to release machines
# ──────────────────────────────────────────────────────────
@router.post(
    "/job_orders/release-all-completed-ph",
    dependencies=[Depends(admin_or_manager)],
)
async def release_machines_for_completed_ph_orders(
    db: asyncpg.Connection = Depends(get_db),
):
    """
    One-time fix to release all injection machines assigned to completed PH orders.
    """
    # Get all completed PH orders
    completed_orders = await db.fetch(
        """
        SELECT id 
        FROM job_orders 
        WHERE status = 'completed' AND product = 'PH'
        """
    )
    
    results = {}
    total_released = 0
    
    # Release machines for each completed order
    for order in completed_orders:
        order_id = order["id"]
        released = await force_release_injection_machines(order_id, db)
        
        if released > 0:
            results[f"order_{order_id}"] = released
            total_released += released
    
    return {
        "success": True,
        "message": f"Released {total_released} injection machines from {len(results)} completed PH orders",
        "details": results
    }



# ──────────────────────────────────────────────────────────
# 9. PH Machine assignment endpoints
# ──────────────────────────────────────────────────────────



@router.get(
    "/job_orders/{order_id}/ph-assigned-machines",
    dependencies=[Depends(admin_or_manager)],
)
async def get_assigned_ph_machines_for_order(
    order_id: int,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get all machines assigned to a specific PH order, grouped by type/stage.
    """
    # Check if order exists and is PH
    order = await db.fetchrow(
        "SELECT id, status, product FROM job_orders WHERE id = $1", 
        order_id
    )
    if not order:
        raise HTTPException(404, "Job order not found")
    
    if order["product"] != "PH":
        raise HTTPException(400, "This endpoint is only for Plastic Hangers (PH) orders")
    
    machines_by_type = await check_ph_order_has_assigned_machines(order_id, db)
    
    return {
        "order_id": order_id,
        "order_status": order["status"],
        "assigned_machines": machines_by_type
    }

@router.get(
    "/job_orders/{order_id}/ph-assigned-machines/{stage}",
    dependencies=[Depends(admin_or_manager)],
)
async def get_assigned_ph_machines_endpoint(
    order_id: int,
    stage: PHStage,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get machines assigned to a PH order that are suitable for a specific stage.
    This is what the frontend will call when user needs to select a machine for a hanger batch.
    """
    # Check if order exists and is PH
    order = await db.fetchrow(
        "SELECT id, status, product FROM job_orders WHERE id = $1", 
        order_id
    )
    if not order:
        raise HTTPException(404, "Job order not found")
    
    if order["product"] != "PH":
        raise HTTPException(400, "This endpoint is only for Plastic Hangers (PH) orders")
    
    machines = await get_assigned_ph_machines_for_order_stage(order_id, stage, db)
    
    if not machines:
        return {
            "order_id": order_id,
            "stage": stage.value,
            "available_machines": [],
            "message": f"No {stage.value.lower()} machines assigned to this PH order"
        }
    
    return {
        "order_id": order_id,
        "stage": stage.value,
        "available_machines": machines
    }


# PH Machine reporting endpoints

@router.get(
    "/ph-machines/{machine_id}/production-report",
    response_model=PHMachineProductionReport,
    dependencies=[Depends(admin_or_manager)],
)
async def get_ph_machine_production_report(
    machine_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Generate production report for a specific machine in PH production.
    """
    # Get machine details
    machine = await db.fetchrow(
        "SELECT machine_id, machine_type, production_line FROM machines WHERE machine_id = $1",
        machine_id
    )
    if not machine:
        raise HTTPException(404, "Machine not found")

    # Only allow Injection Molding and Metal Detector machines
    if machine["machine_type"] not in ["Injection Molding", "Metal Detector"]:
        raise HTTPException(400, f"Machine {machine_id} is not used in PH production")

    # Build date filter
    date_filter = ""
    date_params = [machine_id]
    
    if start_date and end_date:
        date_filter = "AND created_at BETWEEN $2 AND $3"
        date_params.extend([start_date, end_date])
        date_range = f"{start_date} to {end_date}"
    elif start_date:
        date_filter = "AND created_at >= $2"
        date_params.append(start_date)
        date_range = f"from {start_date}"
    elif end_date:
        date_filter = "AND created_at <= $2"
        date_params.append(end_date)
        date_range = f"until {end_date}"
    else:
        date_range = "all time"

    # Query based on machine type and stage
    machine_type = machine["machine_type"]
    
    if machine_type == "Injection Molding":
        query = f"""
            SELECT 
                COUNT(*) as total_batches,
                COALESCE(SUM(injection_weight_g), 0) as total_production_g,
                COALESCE(SUM(waste_of_im_g), 0) as total_waste_g,
                array_agg(DISTINCT order_id) as orders
            FROM production_hangers 
            WHERE injection_machine_id = $1 
            AND injection_weight_g IS NOT NULL
            {date_filter}
        """
    else:  # Metal Detector
        query = f"""
            SELECT 
                COUNT(*) as total_batches,
                0 as total_production_g,
                COALESCE(SUM(waste_of_metaldetect_g), 0) as total_waste_g,
                array_agg(DISTINCT order_id) as orders
            FROM production_hangers 
            WHERE metal_detect_machine_id = $1 
            AND metal_detect_ts IS NOT NULL
            {date_filter}
        """
    
    result = await db.fetchrow(query, *date_params)
    
    total_production_kg = (result["total_production_g"] or 0) / 1000
    total_waste_kg = (result["total_waste_g"] or 0) / 1000
    
    # Calculate efficiency
    total_output = total_production_kg + total_waste_kg
    efficiency_rate = (total_production_kg / total_output * 100) if total_output > 0 else 0
    
    return PHMachineProductionReport(
        machine_id=machine["machine_id"],
        machine_type=machine["machine_type"],
        production_line=machine["production_line"],
        date_range=date_range,
        total_production_kg=total_production_kg,
        total_waste_kg=total_waste_kg,
        total_batches_produced=result["total_batches"] or 0,
        orders_worked_on=result["orders"] or [],
        efficiency_rate=round(efficiency_rate, 2)
    )

@router.get(
    "/ph-machines/{machine_id}/production-details",
    response_model=List[PHMachineProductionDetail],
    dependencies=[Depends(admin_or_manager)],
)
async def get_ph_machine_production_details(
    machine_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get detailed production history for a machine in PH production.
    """
    machine = await db.fetchrow(
        "SELECT machine_type FROM machines WHERE machine_id = $1",
        machine_id
    )
    if not machine:
        raise HTTPException(404, "Machine not found")

    if machine["machine_type"] not in ["Injection Molding", "Metal Detector"]:
        raise HTTPException(400, f"Machine {machine_id} is not used in PH production")

    # Build date filter
    date_filter = ""
    date_params = [machine_id]
    
    if start_date and end_date:
        date_filter = "AND created_at BETWEEN $2 AND $3"
        date_params.extend([start_date, end_date])
    elif start_date:
        date_filter = "AND created_at >= $2"
        date_params.append(start_date)
    elif end_date:
        date_filter = "AND created_at <= $2"
        date_params.append(end_date)

    # Query based on machine type
    machine_type = machine["machine_type"]
    
    if machine_type == "Injection Molding":
        query = f"""
            SELECT 
                order_id,
                batch_index,
                COALESCE(injection_weight_g, 0) as production_weight_g,
                COALESCE(waste_of_im_g, 0) as waste_weight_g,
                injection_weight_ts as timestamp
            FROM production_hangers 
            WHERE injection_machine_id = $1 
            AND injection_weight_g IS NOT NULL
            {date_filter}
            ORDER BY injection_weight_ts DESC
        """
    else:  # Metal Detector
        query = f"""
            SELECT 
                order_id,
                batch_index,
                0 as production_weight_g,
                COALESCE(waste_of_metaldetect_g, 0) as waste_weight_g,
                metal_detect_ts as timestamp
            FROM production_hangers 
            WHERE metal_detect_machine_id = $1 
            AND metal_detect_ts IS NOT NULL
            {date_filter}
            ORDER BY metal_detect_ts DESC
        """
    
    rows = await db.fetch(query, *date_params)
    
    return [
        PHMachineProductionDetail(
            order_id=row["order_id"],
            batch_index=row["batch_index"],
            production_weight_kg=row["production_weight_g"] / 1000,
            waste_weight_kg=row["waste_weight_g"] / 1000,
            timestamp=row["timestamp"]
        )
        for row in rows
    ]

@router.get(
    "/ph-machines/production-summary",
    dependencies=[Depends(admin_or_manager)],
)
async def get_all_ph_machines_production_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get production summary for all PH machines (Injection Molding and Metal Detector).
    """
    machines = await db.fetch(
        """
        SELECT machine_id, machine_type, production_line 
        FROM machines 
        WHERE machine_type IN ('Injection Molding', 'Metal Detector')
        ORDER BY machine_id
        """
    )
    
    summary = []
    for machine in machines:
        machine_id = machine["machine_id"]
        machine_type = machine["machine_type"]
        
        # Build date filter
        date_filter = ""
        date_params = [machine_id]
        
        if start_date and end_date:
            date_filter = "AND created_at BETWEEN $2 AND $3"
            date_params.extend([start_date, end_date])
        elif start_date:
            date_filter = "AND created_at >= $2"
            date_params.append(start_date)
        elif end_date:
            date_filter = "AND created_at <= $2"
            date_params.append(end_date)

        # Query based on machine type
        if machine_type == "Injection Molding":
            query = f"""
                SELECT 
                    COUNT(*) as total_batches,
                    COALESCE(SUM(injection_weight_g), 0) as total_production_g,
                    COALESCE(SUM(waste_of_im_g), 0) as total_waste_g,
                    COUNT(DISTINCT order_id) as orders_count
                FROM production_hangers 
                WHERE injection_machine_id = $1 
                AND injection_weight_g IS NOT NULL
                {date_filter}
            """
        else:  # Metal Detector
            query = f"""
                SELECT 
                    COUNT(*) as total_batches,
                    0 as total_production_g,
                    COALESCE(SUM(waste_of_metaldetect_g), 0) as total_waste_g,
                    COUNT(DISTINCT order_id) as orders_count
                FROM production_hangers 
                WHERE metal_detect_machine_id = $1 
                AND metal_detect_ts IS NOT NULL
                {date_filter}
            """
        
        result = await db.fetchrow(query, *date_params)
        
        total_production_kg = (result["total_production_g"] or 0) / 1000
        total_waste_kg = (result["total_waste_g"] or 0) / 1000
        total_output = total_production_kg + total_waste_kg
        efficiency_rate = (total_production_kg / total_output * 100) if total_output > 0 else 0
        
        summary.append({
            "machine_id": machine_id,
            "machine_type": machine_type,
            "production_line": machine["production_line"],
            "total_production_kg": round(total_production_kg, 2),
            "total_waste_kg": round(total_waste_kg, 2),
            "total_batches": result["total_batches"] or 0,
            "orders_worked": result["orders_count"] or 0,
            "efficiency_rate": round(efficiency_rate, 2)
        })
    
    date_range = "all time"
    if start_date and end_date:
        date_range = f"{start_date} to {end_date}"
    elif start_date:
        date_range = f"from {start_date}"
    elif end_date:
        date_range = f"until {end_date}"
    
    return {
        "date_range": date_range,
        "machines": summary
    }

# Frontend helper endpoints for PH production

@router.get(
    "/ph-machines/all-by-type/{machine_type}",
    dependencies=[Depends(admin_or_manager)],
)
async def get_all_ph_machines_by_type(
    machine_type: str,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get all PH machines of a specific type (useful for assigning machines to orders).
    """
    # Validate machine type for PH production
    valid_ph_types = ["Injection Molding", "Metal Detector"]
    if machine_type not in valid_ph_types:
        raise HTTPException(400, f"Invalid machine type for PH production. Valid types: {valid_ph_types}")
    
    machines = await db.fetch(
        """
        SELECT machine_id, machine_type, production_line, status, current_job_order
        FROM machines 
        WHERE machine_type = $1
        ORDER BY machine_id
        """,
        machine_type
    )
    
    return {
        "machine_type": machine_type,
        "machines": [dict(machine) for machine in machines]
    }

@router.get(
    "/ph-machines/available-for-stage/{stage}",
    dependencies=[Depends(admin_or_manager)],
)
async def get_available_ph_machines_for_stage_endpoint(
    stage: PHStage,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get list of available PH machines for a specific production stage.
    This shows all machines of the correct type, regardless of assignment.
    """
    stage_to_machine_type = {
        PHStage.INJECTION: "Injection Molding",
        PHStage.METAL_DETECT: "Metal Detector"
    }
    
    machine_type = stage_to_machine_type.get(stage)
    if not machine_type:
        return {"stage": stage.value, "available_machines": [], "message": f"No machines required for {stage.value} stage"}
    
    machines = await db.fetch(
        """
        SELECT machine_id, machine_type, production_line, status, current_job_order
        FROM machines 
        WHERE machine_type = $1 AND status IN ('available', 'in_use')
        ORDER BY machine_id
        """,
        machine_type
    )
    
    return {"stage": stage.value, "available_machines": [dict(machine) for machine in machines]}

@router.get(
    "/job_orders/{order_id}/ph-flow",
    dependencies=[Depends(admin_or_manager)],
)
async def get_ph_order_flow(
    order_id: int,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get the production flow for a specific PH order based on model and raw_degree.
    """
    order = await db.fetchrow(
        "SELECT product, model, raw_degree FROM job_orders WHERE id = $1",
        order_id
    )
    if not order:
        raise HTTPException(404, "Job order not found")
    
    if order["product"] != "PH":
        raise HTTPException(400, "This endpoint is only for Plastic Hangers (PH) orders")
    
    flow = allowed_ph_flow(order["model"], order["raw_degree"])
    
    # Add machine requirements for each stage
    flow_with_machines = []
    for stage in flow:
        stage_info = {"stage": stage.value, "requires_machine": False, "machine_type": None}
        
        if stage == PHStage.INJECTION:
            stage_info["requires_machine"] = True
            stage_info["machine_type"] = "Injection Molding"
        elif stage == PHStage.METAL_DETECT:
            stage_info["requires_machine"] = True
            stage_info["machine_type"] = "Metal Detector"
        
        flow_with_machines.append(stage_info)
    
    return {
        "order_id": order_id,
        "model": order["model"],
        "raw_degree": order["raw_degree"],
        "flow": flow_with_machines
    }