from fastapi import APIRouter, Depends, HTTPException
from config import connect_to_db
from employee_routes.auth import TokenData

router = APIRouter(prefix="/api/manager", tags=["Manager"])

# Manager-only access
async def role_required(current_user: TokenData):
    if current_user.role != "Manager":
        raise HTTPException(status_code=403, detail="Manager access required")
    return current_user

# Fetch all Managers
@router.get("/employees")
async def get_all_managers(current_user: TokenData = Depends(role_required)):
    pool = await connect_to_db()
    async with pool.acquire() as conn:
        managers = await conn.fetch(
            "SELECT id, name, email, role, barcode, created_at FROM employees WHERE role='Manager'"
        )
    return [dict(manager) for manager in managers]

# Additional manager-specific routes can be added here
