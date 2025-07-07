import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import asyncpg
from typing import List, Optional
from routers.employees import admin_only, admin_or_manager, TokenData

router = APIRouter(tags=["machines"])

DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# --------------------------------------------
# MODELS
# --------------------------------------------
class MachineCreate(BaseModel):
    production_line: str  # "Line 1" or "Line 2"
    machine_type: str         # "Blowing Film", "Printing", etc.

class Machine(BaseModel):
    id: int
    production_line: str
    machine_type: str
    machine_id: str
    status: str  # 'available', 'in_use', 'maintenance', 'out_of_order'
    current_job_order: Optional[int] = None

# --------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------
def get_machine_prefix(machine_type: str) -> str:
    """
    Maps machine_type to the prefix for machine_id.
    E.g.:
      "Blowing Film" -> "BF"
      "Printing" -> "P"
      "Cutting" -> "C"
      "Injection Molding" -> "IM"
      "Metal Detector" -> "MD"
    """
    mapping = {
        "Blowing Film": "BF",
        "Injection Molding": "IM",
        "Printing": "P",
        "Cutting": "C",
        "Metal Detector": "MD"
    }
    prefix = mapping.get(machine_type)
    if not prefix:
        raise ValueError(f"Invalid machine machine_type: {machine_type}")
    return prefix

async def generate_machine_id(conn, machine_type: str) -> str:
    """
    Generates the next machine_id in the format: <PREFIX>-XYZ
    Where <PREFIX> is based on machine_type, e.g. "BF" for Blowing Film.
    We count how many machines exist with the same machine_type, do count+1.
    BF-001, BF-002, ...
    """
    prefix = get_machine_prefix(machine_type)
    count_query = """
        SELECT COUNT(*) 
        FROM machines 
        WHERE machine_type = $1
    """
    existing_count = await conn.fetchval(count_query, machine_type)
    next_number = existing_count + 1
    return f"{prefix}-{str(next_number).zfill(3)}"

# --------------------------------------------
# ENDPOINTS
# --------------------------------------------

@router.post("/machines", response_model=Machine)
async def create_machine(
    machine: MachineCreate,
    current_user: TokenData = Depends(admin_only)
):
    # Validation and other code...
    
    conn = await connect_to_db()
    try:
        machine_id = await generate_machine_id(conn, machine.machine_type)

        result = await conn.fetchrow(
            """
            INSERT INTO machines (production_line, machine_type, machine_id)
            VALUES ($1, $2, $3)
            RETURNING id, production_line, machine_type, machine_id, status, current_job_order
            """,
            machine.production_line,
            machine.machine_type,
            machine_id
        )
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create machine.")

        return Machine(
            id=result["id"],
            production_line=result["production_line"],
            machine_type=result["machine_type"],
            machine_id=result["machine_id"],
            status=result["status"],  # Added this line
            current_job_order=result["current_job_order"]  # Added this line
        )
    # Exception handling and other code...
    except ValueError as ve:
        # If get_machine_prefix raised an error for invalid machine_type
        raise HTTPException(status_code=400, detail=str(ve))
    finally:
        await conn.close()

@router.get("/machines", response_model=List[Machine])
async def get_machines(current_user: TokenData = Depends(admin_or_manager)):
    """
    Admin or Manager can list all machines with status and current job order information.
    """
    conn = await connect_to_db()
    rows = await conn.fetch("""
        SELECT id, production_line, machine_type, machine_id, status, current_job_order
        FROM machines
        ORDER BY id
    """)
    await conn.close()

    return [Machine(
        id=r["id"],
        production_line=r["production_line"],
        machine_type=r["machine_type"],
        machine_id=r["machine_id"],
        status=r["status"],
        current_job_order=r["current_job_order"]
    ) for r in rows]