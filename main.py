from fastapi import FastAPI, Depends, HTTPException
from fastapi import security
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import os
from typing import Optional

# Import routers
from routers import inventory, employees, job_orders , machines, active_orders,comp_inventory,analytics,production_tracking,ph_production_tracking,storage_router,waste_management,machine_reports,customer_acc,supplier_acc,costs,revenues,recylcing_line
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status

security_scheme = HTTPBearer()

app = FastAPI(title="Factory Management System API", 
             description="API for managing factory inventory, employees, and job orders",
             version="1.0.0")

async def get_token_header(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials:
        return credentials.credentials
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(inventory.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(job_orders.router, prefix="/api")
app.include_router(machines.router, prefix="/api")
app.include_router(active_orders.router, prefix="/api")
app.include_router(comp_inventory.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(production_tracking.router, prefix= "/api")
app.include_router(ph_production_tracking.router, prefix= "/api")
app.include_router(storage_router.router, prefix="/api")  # Updated this line
app.include_router(waste_management.router)
app.include_router(machine_reports.router)
app.include_router(customer_acc.router, prefix="/api")
app.include_router(supplier_acc.router)
app.include_router(costs.router, prefix="/api")
app.include_router(revenues.router)
app.include_router(recylcing_line.router, prefix="/api")




# Health check endpoint
@app.get("/")
def read_root():
    return {"message": "Factory Management System API Running", 
            "version": "1.0.0",
            "status": "healthy"}