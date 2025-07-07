from fastapi import APIRouter, Depends, HTTPException
from config import connect_to_db
from employee_routes.auth import TokenData

router = APIRouter(prefix="/api/operator", tags=["Operator"])

# Operator-only access
async def role_required(current_user: TokenData):
    if current_user.role != "Operator":
        raise HTTPException(status_code=403, detail="Operator access required")
    return current_user

# Operators can only view their own information
@router.get("/profile")
async def operator_profile(current_user: TokenData = Depends(role_required)):
    conn = await connect_to_db()
    operator = await conn.fetchrow("SELECT id, name, email, role, barcode, created_at FROM employees WHERE email=$1", current_user.email)
    await conn.close()
    
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")

    return dict(operator)
