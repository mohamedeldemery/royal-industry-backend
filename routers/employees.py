import os
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import asyncpg
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, List

# Initialize Router
router = APIRouter(tags=["employees"])

# Database Connection
DATABASE_URL = os.getenv("DATABASE_URL")

# JWT Configuration
SECRET_KEY = "your_secure_secret_key_here"  # Change this in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# OAuth2 password bearer for token handling
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# Employee Model for Registration
class EmployeeRegister(BaseModel):
    name: str
    email: str
    password: str
    role: str  # 'Admin', 'Manager', 'Operator'

# Token response model
class Token(BaseModel):
    access_token: str
    token_type: str
    # For Python 3.9, replace dict | None with Optional[dict].
    user_info: Optional[dict] = None

# User model for token data
class TokenData(BaseModel):
    id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    barcode: Optional[str] = None

# For GET /employees/operators
class OperatorOut(BaseModel):
    id: int
    name: str

# Generate Unique Barcode
def generate_barcode(employee_id: int, role: str):
    role_code = {"Admin": "ADM", "Manager": "MNG", "Operator": "OPR"}.get(role, "EMP")
    date_code = datetime.now().strftime("%y%m%d")
    unique_id = str(employee_id).zfill(4)
    return f"{role_code}-{date_code}-{unique_id}"

# Create access token
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Verify token and get current user
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_data = TokenData(
            id=payload.get("id"),
            email=payload.get("email"),
            role=payload.get("role"),
            name=payload.get("name"),
            barcode=payload.get("barcode")
        )
        if user_data.email is None:
            raise credentials_exception
        return user_data
    except jwt.PyJWTError:
        raise credentials_exception

# Admin-only access check
async def admin_only(current_user: TokenData = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Only admin users can access this endpoint")
    return current_user

# Admin or Manager only check
async def admin_or_manager(current_user: TokenData = Depends(get_current_user)):
    if current_user.role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Only admin or manager users can access this endpoint")
    return current_user

# Register New Employee
@router.post("/register")
async def register_employee(employee: EmployeeRegister):
    conn = await connect_to_db()

    # Check if email exists
    existing_user = await conn.fetchrow("SELECT id FROM employees WHERE email=$1", employee.email)
    if existing_user:
        await conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    hashed_password = bcrypt.hashpw(employee.password.encode(), bcrypt.gensalt()).decode()

    # Insert new employee
    new_employee = await conn.fetchrow(
        "INSERT INTO employees (name, email, password, role) VALUES ($1, $2, $3, $4) RETURNING id",
        employee.name, employee.email, hashed_password, employee.role
    )

    # Generate and store barcode
    barcode = generate_barcode(new_employee["id"], employee.role)
    await conn.execute("UPDATE employees SET barcode=$1 WHERE id=$2", barcode, new_employee["id"])

    # Fetch complete user information
    user = await conn.fetchrow("SELECT id, name, email, role, barcode FROM employees WHERE id=$1", new_employee["id"])
    await conn.close()

    # Create JWT token with user information
    user_data = dict(user)
    access_token = create_access_token(user_data)

    # Return token and user info
    return {
        "message": "Employee registered successfully",
        "access_token": access_token,
        "token_type": "bearer",
        "user_info": user_data
    }

# Employee Login (OAuth2 "password" flow)
@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = await connect_to_db()

    # Use form_data.username (the user’s email) and form_data.password
    user = await conn.fetchrow("SELECT * FROM employees WHERE email = $1", form_data.username)
    await conn.close()

    # Validate user
    if not user or not bcrypt.checkpw(form_data.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create token payload
    token_data = {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "barcode": user["barcode"],
    }
    access_token = create_access_token(token_data)

    return {"access_token": access_token, "token_type": "bearer"}

# Get current user profile
@router.get("/profile")
async def get_current_profile(current_user: TokenData = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "name": current_user.name,
        "barcode": current_user.barcode
    }

# Fetch All Employees (Admin only)################################################################
@router.get("/employees")
async def get_all_employees(current_user: TokenData = Depends(admin_only)):
    conn = await connect_to_db()
    employees = await conn.fetch("SELECT id, name, email, role, barcode FROM employees")
    await conn.close()
    return [dict(emp) for emp in employees]

# Delete Employee (Admin only)
@router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: int, current_user: TokenData = Depends(admin_only)):
    conn = await connect_to_db()

    # Check if employee exists
    employee = await conn.fetchrow("SELECT id, role FROM employees WHERE id=$1", employee_id)
    if not employee:
        await conn.close()
        raise HTTPException(status_code=404, detail="Employee not found")

    # Prevent deletion of the last admin
    if employee["role"] == "Admin":
        admin_count = await conn.fetchval("SELECT COUNT(*) FROM employees WHERE role='Admin'")
        if admin_count <= 1:
            await conn.close()
            raise HTTPException(status_code=400, detail="Cannot delete the last admin account")

    # Prevent self-deletion
    if employee["id"] == current_user.id:
        await conn.close()
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Delete the employee
    await conn.execute("DELETE FROM employees WHERE id=$1", employee_id)
    await conn.close()

    return {"message": "Employee deleted successfully"}

# Mark Attendance Using Barcode
@router.post("/attendance/{barcode}")
async def mark_attendance(barcode: str):
    conn = await connect_to_db()
    user = await conn.fetchrow("SELECT id, name FROM employees WHERE barcode=$1", barcode)

    if not user:
        await conn.close()
        raise HTTPException(status_code=404, detail="Employee not found")

    await conn.execute("INSERT INTO attendance (employee_id) VALUES ($1)", user["id"])
    await conn.close()

    return {"message": f"Attendance marked for {user['name']}"}


# -----------------------------------------------
# NEW: Get Operators
# -----------------------------------------------
@router.get("/employees/operators", response_model=List[OperatorOut])
async def get_operators(current_user: TokenData = Depends(admin_or_manager)):
    """
    Returns all employees who have role='Operator'.
    Admin or Manager only can call this endpoint.
    """
    conn = await connect_to_db()
    try:
        rows = await conn.fetch("SELECT id, name FROM employees WHERE role='Operator'")
        await conn.close()
        operators = [dict(r) for r in rows]
        return operators  # matches List[OperatorOut] structure
    except Exception as e:
        await conn.close()
        raise HTTPException(status_code=400, detail=f"Error fetching operators: {str(e)}")
