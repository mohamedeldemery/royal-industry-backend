from fastapi import APIRouter, Depends, HTTPException
from config import connect_to_db
from employee_routes.auth import TokenData

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Admin-only access
async def role_required(current_user: TokenData):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Fetch all employees (Admins, Managers, Operators)
@router.get("/employees")
async def get_all_employees(current_user: TokenData = Depends(role_required)):
    pool = await connect_to_db()
    async with pool.acquire() as conn:
        employees = await conn.fetch(
            "SELECT id, name, email, role, barcode, created_at FROM employees ORDER BY role, id"
        )
    return [dict(emp) for emp in employees]

# Delete an employee by ID (Admin privilege)
@router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: int, current_user: TokenData = Depends(role_required)):
    pool = await connect_to_db()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM employees WHERE id=$1", employee_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"message": "Employee deleted successfully"}
