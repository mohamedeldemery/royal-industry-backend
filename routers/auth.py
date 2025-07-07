import os
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import asyncpg
import bcrypt
from datetime import datetime, timedelta
import jwt
from typing import Optional

# Initialize Router
router = APIRouter(tags=["auth"])

# Database Connection
DATABASE_URL = os.getenv("DATABASE_URL")

# JWT Configuration
SECRET_KEY = "your_secret_key_here"  # Change this to a secure random key in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Token model
class Token(BaseModel):
    access_token: str
    token_type: str

# User model for token data
class TokenData(BaseModel):
    id: int
    email: str
    role: str
    name: str
    barcode: str

# Employee Login Model
class EmployeeLogin(BaseModel):
    email: str
    password: str

# OAuth2 password bearer for token handling
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

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
        if user_data is None:
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

# Login and generate token
@router.post("/login", response_model=Token)
async def login_for_access_token(employee: EmployeeLogin):
    conn = await connect_to_db()
    user = await conn.fetchrow("SELECT * FROM employees WHERE email=$1", employee.email)
    await conn.close()

    if not user or not bcrypt.checkpw(employee.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create token with user information
    token_data = {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "barcode": user["barcode"]
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