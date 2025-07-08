import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
import asyncpg
from datetime import datetime

from routers.employees import admin_or_manager, TokenData

router = APIRouter(tags=["active_orders"])
DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# 📦 Request model
class OrderConfirmRequest(BaseModel):
    operator_barcodes: List[str]
    material_barcodes: List[str]
    machine_barcodes: List[str]

# 🔍 Preview job order
@router.get("/job_orders/{order_id}/preview")
async def preview_job_order(order_id: int, current_user: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    try:
        order = await conn.fetchrow("SELECT * FROM job_orders WHERE id=$1", order_id)
        if not order:
            raise HTTPException(404, "Job order not found")
        result = dict(order)

        # Include raw materials
        raw = await conn.fetch("SELECT * FROM job_order_materials WHERE job_order_id=$1", order_id)
        result["raw_materials"] = [dict(r) for r in raw]

        # Include components
        comps = await conn.fetch("SELECT * FROM job_order_components WHERE job_order_id=$1", order_id)
        result["components"] = [dict(r) for r in comps]

        # Include assigned machines
        machs = await conn.fetch("SELECT * FROM job_order_machines WHERE job_order_id=$1", order_id)
        result["machines"] = [dict(m) for m in machs]

        # Include operator (if any)
        if result.get("operator_id"):
            op = await conn.fetchrow("SELECT id, name, barcode, role FROM employees WHERE id=$1", result["operator_id"])
            if op:
                result["operator"] = dict(op)

        return result
    except Exception as e:
        raise HTTPException(500, f"Error previewing order: {e}")
    finally:
        await conn.close()

# ✅ Confirm and activate order
# ✅ Confirm and activate order
@router.patch("/job_orders/{order_id}/confirm")
async def confirm_order(order_id: int, data: OrderConfirmRequest, current_user: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    try:
        # Start a transaction
        tr = conn.transaction()
        await tr.start()
        
        # 1. Validate job order exists and is pending
        order = await conn.fetchrow("SELECT * FROM job_orders WHERE id=$1", order_id)
        if not order:
            raise HTTPException(404, "Job order not found")
        if order["status"] != "pending":
            raise HTTPException(400, "Order is not in pending state")
        
        # 🚨 Prevent double deduction
        already_deducted = await conn.fetchval("""
            SELECT TRUE
            FROM job_order_components
            WHERE job_order_id = $1 AND deducted = TRUE
            LIMIT 1
        """, order_id)

        if already_deducted:
            raise HTTPException(status_code=400, detail="Component quantities have already been deducted for this order.")

        # 2. Validate operator barcodes
        operator_ids = []
        for ob in data.operator_barcodes:
            row = await conn.fetchrow("SELECT id FROM employees WHERE barcode=$1 AND role='Operator'", ob)
            if not row:
                raise HTTPException(400, f"Invalid operator barcode: {ob}")
            operator_ids.append(row["id"])

        if not operator_ids:
            raise HTTPException(400, "No valid operators found")

        # 3. Validate material barcodes — check all first
        for mb in data.material_barcodes:
            exists = await conn.fetchval("SELECT 1 FROM inventory WHERE barcode=$1 AND status='available'", mb)
            if not exists:
                raise HTTPException(400, f"Material barcode not found or already in use: {mb}")

        # 4. Validate machine barcodes
        machine_info = []
        for mach_b in data.machine_barcodes:
            m = await conn.fetchrow("SELECT id, machine_type, machine_id FROM machines WHERE machine_id=$1", mach_b)
            if not m:
                raise HTTPException(400, f"Invalid machine barcode: {mach_b}")
            machine_info.append(m)

        # 5. Validate component inventory quantities
        job_components = await conn.fetch("""
            SELECT id AS joc_id, material_name, type, quantity
            FROM job_order_components
            WHERE job_order_id = $1 AND deducted = FALSE
        """, order_id)

        for comp in job_components:
            material_name = comp["material_name"]
            material_type = comp["type"]
            required_quantity = comp["quantity"]
            
            # Check if we have enough inventory
            available_quantity = await conn.fetchval("""
                SELECT quantity 
                FROM comp_inventory
                WHERE material_name = $1 AND type = $2
            """, material_name, material_type)
            
            if available_quantity is None:
                raise HTTPException(status_code=404, detail=f"Component {material_name} of type {material_type} not found in comp_inventory")
            
            if available_quantity < required_quantity:
                raise HTTPException(status_code=400, detail=f"Not enough quantity for {material_name}. Required: {required_quantity}, Available: {available_quantity}")

        # AFTER ALL VALIDATIONS PASSED, perform updates
        
        # Update operator status
        await conn.execute(
            "UPDATE employees SET status='busy', current_job_order=$1 WHERE id=$2",
            order_id, operator_ids[0]
        )

        # Update materials status
        for mb in data.material_barcodes:
            await conn.execute(
                "UPDATE inventory SET status='used', job_order_id=$2 WHERE barcode=$1", 
                mb, order_id
            )

        # Deduct component inventory
        for comp in job_components:
            joc_id = comp["joc_id"]
            material_name = comp["material_name"]
            material_type = comp["type"]
            required_quantity = comp["quantity"]
            
            # Perform deduction
            await conn.execute("""
                UPDATE comp_inventory
                SET quantity = quantity - $1
                WHERE material_name = $2 AND type = $3
            """, required_quantity, material_name, material_type)
            
            # Mark as deducted
            await conn.execute("""
                UPDATE job_order_components
                SET deducted = TRUE
                WHERE id = $1
            """, joc_id)

        # Add machines to job order
        for m in machine_info:
            await conn.execute(
                "INSERT INTO job_order_machines (job_order_id, machine_type, machine_id) VALUES ($1, $2, $3)",
                order_id, m["machine_type"], m["machine_id"]
            )
            await conn.execute(
                "UPDATE machines SET status='in_use', current_job_order=$1 WHERE machine_id=$2",
                order_id, m["machine_id"]
            )

            

        # Update the job order: status, operator, machine, start_time
        now = datetime.now()
        await conn.execute(
            """
            UPDATE job_orders
            SET status='in_progress', start_time=$2, operator_id=$3, machine_id=$4
            WHERE id=$1
            """,
            order_id,
            now,
            operator_ids[0],
            machine_info[0]["machine_id"] if machine_info else None
        )

        # Commit all changes
        await tr.commit()

        return {
            "message": "Order activated successfully.",
            "order_id": order_id,
            "operator_id": operator_ids[0],
            "machines_used": [m["machine_id"] for m in machine_info],
            "start_time": now.isoformat()
        }

    except Exception as e:
        # If any exception occurs, rollback the transaction
        try:
            await tr.rollback()
        except:
            pass  # Ignore rollback error
        
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, f"Server error: {str(e)}")
    finally:
        await conn.close()