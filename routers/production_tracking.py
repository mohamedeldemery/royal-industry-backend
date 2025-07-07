# routers/production_tracking.py
from enum import Enum
from typing import List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, NonNegativeInt
from datetime import datetime
from fastapi.responses import JSONResponse
from routers.employees import admin_or_manager, TokenData

router = APIRouter(tags=["production‑tracking"])

DB_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

# ──────────────────────────────────────────────────────────
# 1. ENUMS AND DOMAIN MODEL (MUST BE FIRST)
# ──────────────────────────────────────────────────────────

class Stage(str, Enum):
    # common
    BLOWING   = "BLOWING"
    PRINTING  = "PRINTING"
    CUTTING   = "CUTTING"
    METAL_DETECT = "METAL_DETECT"    # new
    PACKAGING = "PACKAGING"

# Valid stage sequences per product / raw‑degree
FLOW_AB_1ST = [Stage.BLOWING, Stage.PRINTING, Stage.CUTTING, Stage.PACKAGING]
FLOW_AB_2ND = [Stage.BLOWING, Stage.PRINTING, Stage.CUTTING,
               Stage.METAL_DETECT, Stage.PACKAGING]
FLOW_PR     = [Stage.BLOWING, Stage.PACKAGING]


def allowed_flow(product: str, raw_degree: Optional[str]) -> List[Stage]:
    if product == "PR":
        return FLOW_PR
    if product == "AB" and raw_degree == "2nd Degree":
        return FLOW_AB_2ND
    return FLOW_AB_1ST


# ──────────────────────────────────────────────────────────
# 2. Domain model
# ──────────────────────────────────────────────────────────



class RollCreate(BaseModel):
    weight_g: int = Field(..., ge=1)
    waste_of_blowing_g: Optional[int] = Field(None, ge=0)
    blowing_machine_id: str = Field(..., description="Machine ID that produced this roll")

class RollUpdate(BaseModel):
    stage: Optional[Stage] = None
    weight_g: Optional[NonNegativeInt] = None
    waste_of_blowing_g: Optional[NonNegativeInt] = None
    waste_of_printing_g: Optional[NonNegativeInt] = None
    waste_of_cutting_g: Optional[NonNegativeInt] = None
    waste_of_metal_detect_g: Optional[NonNegativeInt] = None
    
    # Machine IDs for each stage
    blowing_machine_id: Optional[str] = None
    printing_machine_id: Optional[str] = None
    cutting_machine_id: Optional[str] = None
    metal_detect_machine_id: Optional[str] = None


class RollOut(BaseModel):
    id: int
    order_id: int
    tmp_index: int
    stage: Stage

    roll_weight_g:      Optional[int] = None
    roll_weight_ts:     Optional[datetime] = None
    printed_weight_g:   Optional[int] = None
    printed_weight_ts:  Optional[datetime] = None
    cut_weight_g:       Optional[int] = None
    cut_weight_ts:      Optional[datetime] = None
    packaged_weight_g:  Optional[int] = None
    packaged_weight_ts: Optional[datetime] = None
    metal_detect_ts:    Optional[datetime] = None
    
    # Waste weight measurements with timestamps
    waste_of_blowing_g:        Optional[int] = None
    waste_of_blowing_ts:       Optional[datetime] = None
    waste_of_printing_g:       Optional[int] = None
    waste_of_printing_ts:      Optional[datetime] = None
    waste_of_cutting_g:        Optional[int] = None
    waste_of_cutting_ts:       Optional[datetime] = None
    waste_of_metal_detect_g:   Optional[int] = None
    waste_of_metal_detect_ts:  Optional[datetime] = None

     # Machine IDs
    blowing_machine_id: Optional[str] = None
    printing_machine_id: Optional[str] = None
    cutting_machine_id: Optional[str] = None
    metal_detect_machine_id: Optional[str] = None


class MachineProductionReport(BaseModel):
    machine_id: str
    machine_type: str
    production_line: str
    date_range: str
    total_production_kg: float
    total_waste_kg: float
    total_rolls_produced: int
    orders_worked_on: List[int]
    efficiency_rate: float  # (production / (production + waste)) * 100

class MachineProductionDetail(BaseModel):
    order_id: int
    roll_index: int
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
    Returns {product, raw_degree} or raises 404.
    """
    row = await db.fetchrow(
        "SELECT product, raw_degree FROM job_orders WHERE id=$1",
        order_id,
    )
    if not row:
        raise HTTPException(404, "Job order not found")
    return row


async def ensure_trackable(order_id: int, db: asyncpg.Connection = Depends(get_db)):
    """
    Allow only AB (bags) or PR (plastic rolls).
    Returns (product_code:str, raw_degree:str|None)
    """
    row = await get_order_basic(order_id, db)
    if row["product"] not in ("AB", "PR"):
        raise HTTPException(
            400,
            "Production rolls tracking is available only for Apparel Bags (AB) "
            "or Plastic Rolls (PR) orders.",
        )
    return row  # dependency return value

async def update_roll_stage_enum(db):
    await db.execute("""
    -- Add METAL_DETECT to the roll_stage enum if it doesn't exist
    ALTER TYPE roll_stage ADD VALUE IF NOT EXISTS 'METAL_DETECT';
    """)
    
    print("Updated roll_stage enum to include METAL_DETECT")




    # Revised helper functions for pre-assigned machine validation

async def get_assigned_machines_for_order_stage(
    order_id: int, 
    stage: Stage, 
    db: asyncpg.Connection
) -> List[dict]:
    """
    Returns machines that are assigned to this order and are suitable for the given stage.
    """
    stage_to_machine_type = {
        Stage.BLOWING: "Blowing Film",
        Stage.PRINTING: "Printing",
        Stage.CUTTING: "Cutting",
        Stage.METAL_DETECT: "Metal Detector"
    }
    
    machine_type = stage_to_machine_type.get(stage)
    if not machine_type:
        return []
    
    # Get machines assigned to this order that match the stage type
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

async def validate_machine_assigned_to_order(
    machine_id: str, 
    order_id: int, 
    stage: Stage, 
    db: asyncpg.Connection
) -> bool:
    """
    Validates that the machine is assigned to this order and is correct type for stage.
    """
    stage_to_machine_type = {
        Stage.BLOWING: "Blowing Film",
        Stage.PRINTING: "Printing", 
        Stage.CUTTING: "Cutting",
        Stage.METAL_DETECT: "Metal Detector"
    }
    
    expected_type = stage_to_machine_type.get(stage)
    if not expected_type:
        return False
    
    # Check if machine is assigned to this order and is correct type
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

async def check_order_has_assigned_machines(order_id: int, db: asyncpg.Connection) -> dict:
    """
    Returns summary of machines assigned to an order by type.
    """
    machines = await db.fetch(
        """
        SELECT machine_id, machine_type, production_line
        FROM machines 
        WHERE current_job_order = $1 AND status = 'in_use'
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

async def record_machine_production(
    machine_id: str, 
    order_id: int, 
    roll_index: int, 
    stage: Stage,
    production_weight_g: int,
    waste_weight_g: Optional[int],
    db: asyncpg.Connection
):
    """
    Records production data for machine reporting.
    """
    # Insert into machine production history table (if you create it)
    # Or this data is already captured in the production_rolls table with machine_ids
    await db.execute(
        """
        INSERT INTO machine_production_history 
        (machine_id, order_id, roll_index, stage, production_weight_g, waste_weight_g, recorded_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT (machine_id, order_id, roll_index, stage) 
        DO UPDATE SET 
            production_weight_g = EXCLUDED.production_weight_g,
            waste_weight_g = EXCLUDED.waste_weight_g,
            recorded_at = NOW()
        """,
        machine_id, order_id, roll_index, stage.value, production_weight_g, waste_weight_g
    )






# ──────────────────────────────────────────────────────────
# 2. Order‑completion synchroniser (same idea as before)
# ──────────────────────────────────────────────────────────
async def force_release_machines(order_id: int, db: asyncpg.Connection):
    """
    Forcefully release all machines assigned to an order.
    """
    # Get machines before update (for logging)
    machines_before = await db.fetch(
        """
        SELECT id, machine_id, status
        FROM machines
        WHERE current_job_order = $1
        """,
        order_id
    )
    
    # Execute the update without referencing updated_at column
    result = await db.execute(
        """
        UPDATE machines
        SET status = 'available',
            current_job_order = NULL
        WHERE current_job_order = $1
        """,
        order_id
    )
    
    # Verify and log the results
    if machines_before:
        machine_ids = ", ".join([m["machine_id"] for m in machines_before])
        print(f"FORCED RELEASE: Order {order_id} - Released machines: {machine_ids}")
    else:
        print(f"FORCED RELEASE: No machines found for order {order_id}")
    
    # Return number of machines released
    return len(machines_before)

async def check_order_completion(order_id: int, db: asyncpg.Connection):
    """Auto‑completes an order when packaged weight ≈ target."""
    jo = await db.fetchrow(
        """
        SELECT id, status, remaining_target_g,
               target_weight_no_waste,
               COALESCE((
                   SELECT SUM(packaged_weight_g) FROM production_rolls
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
        await force_release_machines(order_id, db)
        return True

    target_g   = int(jo["target_weight_no_waste"] * 1000)
    remaining  = max(0, target_g - jo["done_g"])
    tol_g      = min(100, int(target_g * 0.01))      # ≤1 % or 100 g

    if remaining <= tol_g:
        async with db.transaction():
            # Calculate total waste before updating the order
            waste_totals = await db.fetchrow(
                """
                SELECT 
                    COALESCE(SUM(waste_of_blowing_g), 0) AS blowing_waste_g,
                    COALESCE(SUM(waste_of_printing_g), 0) AS printing_waste_g,
                    COALESCE(SUM(waste_of_cutting_g), 0) AS cutting_waste_g,
                    COALESCE(SUM(waste_of_metal_detect_g), 0) AS metal_detect_waste_g
                FROM production_rolls
                WHERE order_id=$1
                """,
                order_id,
            )
            
            total_waste = (
                waste_totals["blowing_waste_g"] + 
                waste_totals["printing_waste_g"] + 
                waste_totals["cutting_waste_g"] + 
                waste_totals["metal_detect_waste_g"]
            )
            
            # First update the order status and total_waste_g
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
            
            # Then force-release all machines
            await force_release_machines(order_id, db)
        
        return True

    # keep remaining_target_g in‑sync
    if remaining != jo["remaining_target_g"]:
        await db.execute(
            "UPDATE job_orders SET remaining_target_g=$1 WHERE id=$2",
            remaining, order_id
        )
    return False
# 3. Add a one-time fix endpoint to release machines for already completed orders
# Add this endpoint to your production_tracking.py file
@router.post(
    "/job_orders/release-all-completed",
    dependencies=[Depends(admin_or_manager)],
)
async def release_machines_for_completed_orders(
    db: asyncpg.Connection = Depends(get_db),
):
    """
    One-time fix to release all machines assigned to completed orders.
    """
    # Get all completed orders
    completed_orders = await db.fetch(
        """
        SELECT id 
        FROM job_orders 
        WHERE status = 'completed'
        """
    )
    
    results = {}
    total_released = 0
    
    # Release machines for each completed order
    for order in completed_orders:
        order_id = order["id"]
        released = await force_release_machines(order_id, db)
        
        if released > 0:
            results[f"order_{order_id}"] = released
            total_released += released
    
    return {
        "success": True,
        "message": f"Released {total_released} machines from {len(results)} completed orders",
        "details": results
    }
async def release_machines(order_id: int, db: asyncpg.Connection):
    """
    Directly release all machines assigned to an order.
    """
    # Get the list of machines being released (for logging)
    machines = await db.fetch(
        """
        SELECT id, machine_id, machine_type
        FROM machines
        WHERE current_job_order = $1 AND status = 'in_use'
        """,
        order_id
    )
    
    if not machines:
        print(f"No machines to release for order {order_id}")
        return
    
    # Update all machines in a single query
    result = await db.execute(
        """
        UPDATE machines
        SET status = 'available',
            current_job_order = NULL,
            updated_at = NOW()
        WHERE current_job_order = $1
          AND status = 'in_use'
        """,
        order_id
    )
    
    machine_ids = ", ".join([m["machine_id"] for m in machines])
    print(f"Released machines for order {order_id}: {machine_ids}")
    
    # Verify the release was successful
    still_assigned = await db.fetch(
        """
        SELECT id, machine_id
        FROM machines
        WHERE current_job_order = $1
        """,
        order_id
    )
    
    if still_assigned:
        print(f"WARNING: {len(still_assigned)} machines still assigned to order {order_id} after release attempt")
    else:
        print(f"Successfully released all machines for order {order_id}")


# ──────────────────────────────────────────────────────────
# 4. Helper method for machine validation 
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# 4. POST  /rolls  (create)
# ──────────────────────────────────────────────────────────
@router.post(
    "/job_orders/{order_id}/rolls",
    response_model=RollOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_or_manager)],
)
async def create_roll(
    order_id: int,
    payload: RollCreate,
    meta=Depends(ensure_trackable),
    db: asyncpg.Connection = Depends(get_db),
):
    if await check_order_completion(order_id, db):
        raise HTTPException(400, "Order completed – cannot add rolls.")

    # Validate the blowing machine is assigned to this order
    if not await validate_machine_assigned_to_order(
        payload.blowing_machine_id, order_id, Stage.BLOWING, db
    ):
        raise HTTPException(
            400, 
            f"Machine {payload.blowing_machine_id} is not assigned to this order or not valid for blowing stage"
        )

    next_ndx = await db.fetchval(
        "SELECT COALESCE(MAX(tmp_index),0)+1 FROM production_rolls WHERE order_id=$1",
        order_id,
    )

    # Build the query with machine tracking
    base_query = """
        INSERT INTO production_rolls
              (order_id, tmp_index, stage,
               roll_weight_g, roll_weight_ts, blowing_machine_id"""
    
    values_part = """ VALUES ($1, $2, $3, $4, NOW(), $5"""
    
    query_params = [
        order_id,
        next_ndx,
        Stage.BLOWING.value,
        payload.weight_g,
        payload.blowing_machine_id,
    ]
    
    # Add waste of blowing if provided
    if payload.waste_of_blowing_g is not None:
        base_query += ", waste_of_blowing_g, waste_of_blowing_ts"
        values_part += f", ${len(query_params) + 1}, NOW()"
        query_params.append(payload.waste_of_blowing_g)
    
    # Complete the query
    query = base_query + ")" + values_part + ") RETURNING *;"
    
    async with db.transaction():
        row = await db.fetchrow(query, *query_params)
        
        # Record machine production for reporting
        await record_machine_production(
            payload.blowing_machine_id,
            order_id,
            next_ndx,
            Stage.BLOWING,
            payload.weight_g,
            payload.waste_of_blowing_g,
            db
        )
    
    return RollOut.model_validate(dict(row))

# ──────────────────────────────────────────────────────────
# 5. PATCH /rolls/{id} (update stage / weight)
# ──────────────────────────────────────────────────────────
@router.patch(
    "/job_orders/{order_id}/rolls/{roll_id}",
    response_model=RollOut,
    dependencies=[Depends(admin_or_manager)],
)
async def update_roll(
    order_id: int,
    roll_id: int,
    payload: RollUpdate,
    meta=Depends(ensure_trackable),
    db: asyncpg.Connection = Depends(get_db),
):
    product_code = meta["product"]
    raw_degree = meta["raw_degree"]
    flow = allowed_flow(product_code, raw_degree)

    if await check_order_completion(order_id, db):
        raise HTTPException(400, "Order completed – rolls are frozen.")

    roll = await db.fetchrow(
        "SELECT * FROM production_rolls WHERE id=$1 AND order_id=$2",
        roll_id, order_id,
    )
    if not roll:
        raise HTTPException(404, "Roll not found")

    current_stage = Stage(roll["stage"])
    new_stage = payload.stage or current_stage

    # Validate stage transition
    try:
        cur_idx = flow.index(current_stage)
    except ValueError:
        raise HTTPException(400, "Internal flow inconsistency")

    if new_stage != current_stage:
        if new_stage not in flow:
            raise HTTPException(400, f"{new_stage} not valid for this product")
        if flow.index(new_stage) != cur_idx + 1:
            raise HTTPException(400, "Stages must progress sequentially")

    # Validate machine for the new stage if provided (must be assigned to this order)
    machine_field_map = {
        Stage.BLOWING: 'blowing_machine_id',
        Stage.PRINTING: 'printing_machine_id', 
        Stage.CUTTING: 'cutting_machine_id',
        Stage.METAL_DETECT: 'metal_detect_machine_id'
    }
    
    stage_machine_id = getattr(payload, machine_field_map.get(new_stage, ''), None)
    if stage_machine_id and not await validate_machine_assigned_to_order(
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

    # Handle weight and machine assignment for each stage
    production_weight = None
    waste_weight = None
    
    if payload.weight_g is not None:
        val_index = len(vals) + 1
        production_weight = payload.weight_g
        
        if new_stage == Stage.BLOWING:
            sets.append(f"roll_weight_g=${val_index}")
            sets.append("roll_weight_ts = NOW()")
            if payload.blowing_machine_id:
                sets.append(f"blowing_machine_id=${val_index + 1}")
                vals.append(payload.weight_g)
                vals.append(payload.blowing_machine_id)
            else:
                vals.append(payload.weight_g)
                
        elif new_stage == Stage.PRINTING:
            sets.append(f"printed_weight_g=${val_index}")
            sets.append("printed_weight_ts = NOW()")
            if payload.printing_machine_id:
                sets.append(f"printing_machine_id=${val_index + 1}")
                vals.append(payload.weight_g)
                vals.append(payload.printing_machine_id)
            else:
                vals.append(payload.weight_g)
                
        elif new_stage == Stage.CUTTING:
            sets.append(f"cut_weight_g=${val_index}")
            sets.append("cut_weight_ts = NOW()")
            if payload.cutting_machine_id:
                sets.append(f"cutting_machine_id=${val_index + 1}")
                vals.append(payload.weight_g)
                vals.append(payload.cutting_machine_id)
            else:
                vals.append(payload.weight_g)
                
        elif new_stage == Stage.PACKAGING:
            sets.append(f"packaged_weight_g=${val_index}")
            sets.append("packaged_weight_ts = NOW()")
            vals.append(payload.weight_g)

    # Handle machine assignment without weight change
    if not payload.weight_g and stage_machine_id:
        val_index = len(vals) + 1
        sets.append(f"{machine_field_map[new_stage]}=${val_index}")
        vals.append(stage_machine_id)

    # METAL_DETECT only records timestamp and machine
    if new_stage == Stage.METAL_DETECT:
        sets.append("metal_detect_ts = NOW()")
        if payload.metal_detect_machine_id:
            val_index = len(vals) + 1
            sets.append(f"metal_detect_machine_id=${val_index}")
            vals.append(payload.metal_detect_machine_id)

    # Handle waste updates
    waste_fields = [
        ('waste_of_blowing_g', 'waste_of_blowing_ts'),
        ('waste_of_printing_g', 'waste_of_printing_ts'),
        ('waste_of_cutting_g', 'waste_of_cutting_ts'),
        ('waste_of_metal_detect_g', 'waste_of_metal_detect_ts')
    ]
    
    for waste_field, waste_ts_field in waste_fields:
        waste_value = getattr(payload, waste_field, None)
        if waste_value is not None:
            val_index = len(vals) + 1
            sets.append(f"{waste_field}=${val_index}")
            sets.append(f"{waste_ts_field} = NOW()")
            vals.append(waste_value)
            if waste_field.startswith(f'waste_of_{new_stage.value.lower()}'):
                waste_weight = waste_value

    sets.append("updated_at = NOW()")

    if not vals and len(sets) == 1:
        return RollOut.model_validate(dict(roll))

    vals.extend([roll_id, order_id])

    query = f"""
        UPDATE production_rolls
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
            await record_machine_production(
                stage_machine_id,
                order_id,
                roll["tmp_index"],
                new_stage,
                production_weight,
                waste_weight,
                db
            )

        # Handle packaging weight deduction
        if new_stage == Stage.PACKAGING and payload.weight_g is not None:
            delta = payload.weight_g - (roll["packaged_weight_g"] or 0)
            if delta:
                await db.execute(
                    """
                    UPDATE job_orders
                       SET remaining_target_g = GREATEST(0, remaining_target_g - $1)
                     WHERE id = $2
                    """,
                    delta, order_id,
                )

    await check_order_completion(order_id, db)
    return RollOut.model_validate(dict(updated))

# ──────────────────────────────────────────────────────────
# 6. GET /job_orders/{id}/status
# ──────────────────────────────────────────────────────────
@router.get(
    "/job_orders/{order_id}/status",
    dependencies=[Depends(admin_or_manager)],
)
async def get_status(order_id: int, db: asyncpg.Connection = Depends(get_db)):
    await check_order_completion(order_id, db)

    status_row = await db.fetchrow(
        """
        SELECT id,
               status,
               product,
               raw_degree,
               target_weight_no_waste,
               remaining_target_g,
               total_waste_g,
               COALESCE((
                   SELECT SUM(packaged_weight_g)
                   FROM   production_rolls
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
    
    # Get waste totals from production_rolls
    waste_totals = await db.fetchrow(
        """
        SELECT 
            COALESCE(SUM(waste_of_blowing_g), 0) AS blowing_waste_g,
            COALESCE(SUM(waste_of_printing_g), 0) AS printing_waste_g,
            COALESCE(SUM(waste_of_cutting_g), 0) AS cutting_waste_g,
            COALESCE(SUM(waste_of_metal_detect_g), 0) AS metal_detect_waste_g
        FROM production_rolls
        WHERE order_id = $1
        """,
        order_id
    )
    
    # Calculate current waste
    blowing_waste = waste_totals["blowing_waste_g"]
    printing_waste = waste_totals["printing_waste_g"]
    cutting_waste = waste_totals["cutting_waste_g"]
    metal_detect_waste = waste_totals["metal_detect_waste_g"]
    
    # For completed orders, use the stored total_waste_g
    if status_row["status"] == "completed":
        total_waste = status_row["total_waste_g"]
    else:
        total_waste = blowing_waste + printing_waste + cutting_waste + metal_detect_waste
    
    # Get the flow based on product and raw_degree
    product = status_row["product"]
    raw_degree = status_row["raw_degree"]
    flow = [stage.value for stage in allowed_flow(product, raw_degree)]

    return {
        "order_id": status_row["id"],
        "status": status_row["status"],
        "product": product,
        "raw_degree": raw_degree,
        "flow": flow,
        "target_g": tgt,
        "done_g": done,
        "remaining_g": status_row["remaining_target_g"],
        "completion_%": pct,
        "waste": {
            "blowing_waste_g": blowing_waste,
            "printing_waste_g": printing_waste,
            "cutting_waste_g": cutting_waste,
            "metal_detect_waste_g": metal_detect_waste,
            "total_waste_g": total_waste
        }
    }

# ──────────────────────────────────────────────────────────
# 7. GET rolls list
# ──────────────────────────────────────────────────────────
@router.get(
    "/job_orders/{order_id}/rolls",
    response_model=List[RollOut],
    dependencies=[Depends(admin_or_manager)],
)
async def list_rolls(order_id: int, db: asyncpg.Connection = Depends(get_db)):
    await check_order_completion(order_id, db)
    rows = await db.fetch(
        "SELECT * FROM production_rolls WHERE order_id=$1 ORDER BY id",
        order_id,
    )
    return [RollOut.model_validate(dict(r)) for r in rows]




    # Machine reporting endpoints

@router.get(
    "/machines/{machine_id}/production-report",
    response_model=MachineProductionReport,
    dependencies=[Depends(admin_or_manager)],
)
async def get_machine_production_report(
    machine_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Generate production report for a specific machine.
    """
    # Get machine details
    machine = await db.fetchrow(
        "SELECT machine_id, machine_type, production_line FROM machines WHERE machine_id = $1",
        machine_id
    )
    if not machine:
        raise HTTPException(404, "Machine not found")

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
    stage_column_map = {
        "Blowing Film": ("blowing_machine_id", "roll_weight_g", "waste_of_blowing_g"),
        "Printing": ("printing_machine_id", "printed_weight_g", "waste_of_printing_g"),
        "Cutting": ("cutting_machine_id", "cut_weight_g", "waste_of_cutting_g"),
        "Metal Detector": ("metal_detect_machine_id", None, "waste_of_metal_detect_g")
    }
    
    machine_type = machine["machine_type"]
    if machine_type not in stage_column_map:
        raise HTTPException(400, f"Unsupported machine type: {machine_type}")
    
    machine_col, weight_col, waste_col = stage_column_map[machine_type]
    
    # Build the query
    if weight_col:  # For machines that produce weight
        query = f"""
            SELECT 
                COUNT(*) as total_rolls,
                COALESCE(SUM({weight_col}), 0) as total_production_g,
                COALESCE(SUM({waste_col}), 0) as total_waste_g,
                array_agg(DISTINCT order_id) as orders
            FROM production_rolls 
            WHERE {machine_col} = $1 
            AND {weight_col} IS NOT NULL
            {date_filter}
        """
    else:  # For metal detector (no weight production)
        query = f"""
            SELECT 
                COUNT(*) as total_rolls,
                0 as total_production_g,
                COALESCE(SUM({waste_col}), 0) as total_waste_g,
                array_agg(DISTINCT order_id) as orders
            FROM production_rolls 
            WHERE {machine_col} = $1 
            AND metal_detect_ts IS NOT NULL
            {date_filter}
        """
    
    result = await db.fetchrow(query, *date_params)
    
    total_production_kg = (result["total_production_g"] or 0) / 1000
    total_waste_kg = (result["total_waste_g"] or 0) / 1000
    
    # Calculate efficiency
    total_output = total_production_kg + total_waste_kg
    efficiency_rate = (total_production_kg / total_output * 100) if total_output > 0 else 0
    
    return MachineProductionReport(
        machine_id=machine["machine_id"],
        machine_type=machine["machine_type"],
        production_line=machine["production_line"],
        date_range=date_range,
        total_production_kg=total_production_kg,
        total_waste_kg=total_waste_kg,
        total_rolls_produced=result["total_rolls"] or 0,
        orders_worked_on=result["orders"] or [],
        efficiency_rate=round(efficiency_rate, 2)
    )

@router.get(
    "/machines/{machine_id}/production-details",
    response_model=List[MachineProductionDetail],
    dependencies=[Depends(admin_or_manager)],
)
async def get_machine_production_details(
    machine_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get detailed production history for a machine.
    """
    machine = await db.fetchrow(
        "SELECT machine_type FROM machines WHERE machine_id = $1",
        machine_id
    )
    if not machine:
        raise HTTPException(404, "Machine not found")

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
    stage_column_map = {
        "Blowing Film": ("blowing_machine_id", "roll_weight_g", "waste_of_blowing_g", "roll_weight_ts"),
        "Printing": ("printing_machine_id", "printed_weight_g", "waste_of_printing_g", "printed_weight_ts"),
        "Cutting": ("cutting_machine_id", "cut_weight_g", "waste_of_cutting_g", "cut_weight_ts"),
        "Metal Detector": ("metal_detect_machine_id", None, "waste_of_metal_detect_g", "metal_detect_ts")
    }
    
    machine_type = machine["machine_type"]
    machine_col, weight_col, waste_col, ts_col = stage_column_map[machine_type]
    
    if weight_col:
        query = f"""
            SELECT 
                order_id,
                tmp_index as roll_index,
                COALESCE({weight_col}, 0) as production_weight_g,
                COALESCE({waste_col}, 0) as waste_weight_g,
                {ts_col} as timestamp
            FROM production_rolls 
            WHERE {machine_col} = $1 
            AND {weight_col} IS NOT NULL
            {date_filter}
            ORDER BY {ts_col} DESC
        """
    else:
        query = f"""
            SELECT 
                order_id,
                tmp_index as roll_index,
                0 as production_weight_g,
                COALESCE({waste_col}, 0) as waste_weight_g,
                {ts_col} as timestamp
            FROM production_rolls 
            WHERE {machine_col} = $1 
            AND {ts_col} IS NOT NULL
            {date_filter}
            ORDER BY {ts_col} DESC
        """
    
    rows = await db.fetch(query, *date_params)
    
    return [
        MachineProductionDetail(
            order_id=row["order_id"],
            roll_index=row["roll_index"],
            production_weight_kg=row["production_weight_g"] / 1000,
            waste_weight_kg=row["waste_weight_g"] / 1000,
            timestamp=row["timestamp"]
        )
        for row in rows
    ]

@router.get(
    "/machines/production-summary",
    dependencies=[Depends(admin_or_manager)],
)
async def get_all_machines_production_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get production summary for all machines.
    """
    machines = await db.fetch(
        "SELECT machine_id, machine_type, production_line FROM machines ORDER BY machine_id"
    )
    
    summary = []
    for machine in machines:
        try:
            report = await get_machine_production_report(
                machine["machine_id"], start_date, end_date, db
            )
            summary.append(report.dict())
        except:
            # Handle machines with no production data
            summary.append({
                "machine_id": machine["machine_id"],
                "machine_type": machine["machine_type"], 
                "production_line": machine["production_line"],
                "date_range": f"{start_date or 'start'} to {end_date or 'now'}",
                "total_production_kg": 0,
                "total_waste_kg": 0,
                "total_rolls_produced": 0,
                "orders_worked_on": [],
                "efficiency_rate": 0
            })
    
    return {"machines": summary}



@router.get(
    "/job_orders/{order_id}/assigned-machines",
    dependencies=[Depends(admin_or_manager)],
)
async def get_assigned_machines_for_order(
    order_id: int,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get all machines assigned to a specific order, grouped by type/stage.
    """
    # Check if order exists
    order = await db.fetchrow("SELECT id, status FROM job_orders WHERE id = $1", order_id)
    if not order:
        raise HTTPException(404, "Job order not found")
    
    machines_by_type = await check_order_has_assigned_machines(order_id, db)
    
    return {
        "order_id": order_id,
        "order_status": order["status"],
        "assigned_machines": machines_by_type
    }

@router.get(
    "/job_orders/{order_id}/assigned-machines/{stage}",
    dependencies=[Depends(admin_or_manager)],
)
async def get_assigned_machines_endpoint(
    order_id: int,
    stage: Stage,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Get machines assigned to an order that are suitable for a specific stage.
    This is what the frontend will call when user needs to select a machine for a roll.
    """
    # Check if order exists
    order = await db.fetchrow("SELECT id, status FROM job_orders WHERE id = $1", order_id)
    if not order:
        raise HTTPException(404, "Job order not found")
    
    machines = await get_assigned_machines_for_order_stage(order_id, stage, db)
    
    if not machines:
        return {
            "order_id": order_id,
            "stage": stage.value,
            "available_machines": [],
            "message": f"No {stage.value.lower()} machines assigned to this order"
        }
    
    return {
        "order_id": order_id,
        "stage": stage.value,
        "available_machines": machines
    }
    