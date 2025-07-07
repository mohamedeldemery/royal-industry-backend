from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import asyncpg
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional
from config import connect_to_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# JWT Configuration
SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200  # 30 days

# Employee Models
class EmployeeRegister(BaseModel):
    name: str
    email: str
    password: str
    role: str  # Admin, Manager, Operator

class EmployeeLogin(BaseModel):
    email: str
    password: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

# Generate JWT Token
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Register Employee
@router.post("/register")
async def register_employee(employee: EmployeeRegister):
    conn = await connect_to_db()

    # Check email existence
    existing_user = await conn.fetchrow("SELECT id FROM employees WHERE email=$1", employee.email)
    if existing_user:
        await conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    hashed_password = bcrypt.hashpw(employee.password.encode(), bcrypt.gensalt()).decode()

    # Barcode generation
    barcode = str(hash(employee.email))[-8:]

    # Insert into employees table
    new_employee = await conn.fetchrow(
        "INSERT INTO employees (name, email, password, role, barcode) VALUES ($1, $2, $3, $4, $5) RETURNING id",
        employee.name, employee.email, hashed_password, employee.role, barcode
    )

    # Auto-insert into role-specific tables (if used)
    employee_id = new_employee["id"]
    if employee.role == 'Admin':
        await conn.execute("INSERT INTO admin_employees (employee_id) VALUES ($1)", employee_id)
    elif employee.role == 'Manager':
        await conn.execute("INSERT INTO manager_employees (employee_id) VALUES ($1)", employee_id)
    elif employee.role == 'Operator':
        await conn.execute("INSERT INTO operator_employees (employee_id) VALUES ($1)", employee_id)

    access_token = create_access_token(data={"email": employee.email, "role": employee.role, "sub": str(employee_id)})
    await conn.close()

    return {"id": employee_id, "role": employee.role, "token": access_token}

# Employee Login
@router.post("/login")
async def login_employee(employee: EmployeeLogin):
    conn = await connect_to_db()
    user = await conn.fetchrow("SELECT * FROM employees WHERE email=$1", employee.email)

    if not user or not bcrypt.checkpw(employee.password.encode(), user["password"].encode()):
        await conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate JWT Token
    access_token = create_access_token(data={"email": employee.email, "role": user["role"], "sub": str(user["id"])})

    await conn.close()
    return {
        "id": str(user["id"]),
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "token": access_token
    }
