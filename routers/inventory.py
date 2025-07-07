import os
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, field_validator, model_validator
import asyncpg
from datetime import date, datetime
import random
from typing import Optional, List


# Import the auth dependencies from employees.py
from routers.employees import admin_or_manager, TokenData

# Initialize Router
router = APIRouter(tags=["inventory"])

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)



# --------------------------------------------
# MODELS
# --------------------------------------------
class InventoryItemResponse(BaseModel):
    id: int
    category: str
    material_type: str
    kind: str
    weight: float
    quantity: int
    supplier: str
    received_date: date
    group_id: str
    barcode: str
    density: float
    grade: str
    color: str
    unit_price: Optional[float] = 0.0  # Allow None, default to 0.0
    total_price: Optional[float] = 0.0  # Allow None, default to 0.0
    status: Optional[str] = "available"
    created_at: Optional[datetime] = None

    # Add a model validator to handle None values
    @model_validator(mode='after')
    def handle_null_prices(self):
        # Convert None to 0.0 for price fields
        if self.unit_price is None:
            self.unit_price = 0.0
        if self.total_price is None:
            self.total_price = 0.0
        return self

class PaginatedInventoryResponse(BaseModel):
    materials: List[InventoryItemResponse]
    pagination: dict
    summary: dict
    filters_applied: dict

class InventoryItem(BaseModel):
    category: str            # 1st Degree or 2nd Degree
    material_type: str       # e.g. LLDPE AAB, PP, etc.
    kind: str
    weight: float
    quantity: int            # Number of batches
    supplier: str
    received_date: date
    group_id: str
    unit_price: float        # Unit price per batch
    total_price: Optional[float] = None  # Will be calculated

    # New fields
    density: float
    grade: str
    color: str

class MaterialType(BaseModel):
    category: str            # "1st Degree" or "2nd Degree"
    material_type: str       # e.g. "LLDPE AAB" or "LLDPE (recycled)"

class InventorySummary(BaseModel):
    category: str
    material_type: str
    available_quantity: int
    available_weight: float

class InventoryPriceUpdate(BaseModel):
    unit_price: float

# NEW MODEL FOR INVENTORY ORDERS
class InventoryOrder(BaseModel):
    group_id: str
    received_date: date
    unit_price: float
    quantity: int
    total_price: float
    supplier: str
    category: str
    material_type: str

class InventoryOrderResponse(BaseModel):
    id: int
    group_id: str
    received_date: date
    unit_price: float
    quantity: int
    total_price: float
    supplier: str
    category: str
    material_type: str
    created_at: datetime

# ---------- Validators ----------
    @field_validator("unit_price")
    def validate_unit_price_positive(cls, v):
        if v <= 0:
            raise ValueError("Unit price must be greater than 0")
        return v

    @model_validator(mode='after')
    def calculate_total_price(self):
        # Calculate total_price automatically
        if self.unit_price and self.quantity:
            self.total_price = self.unit_price * self.quantity
        return self    

# --------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------
def generate_serial_number(category: str, material_type: str, batch_group_id: str, index: int):
    """Generates a barcode based on the predefined format."""
    category_code = "1D" if "1st" in category else "2D"
    material_code = "".join([x[0:3].upper() for x in material_type.split()])  # First 3 letters of material type
    date_code = datetime.now().strftime("%y%m%d")  # YYMMDD
    batch_id = batch_group_id.zfill(3)  # Ensures it's always 3 digits
    item_number = str(index).zfill(3)   # Ensures 001, 002, etc.
    return f"{category_code}-{material_code}-{date_code}-{batch_id}-{item_number}"

# --------------------------------------------
# DATABASE SETUP FUNCTION
# --------------------------------------------
async def create_inventory_orders_table():
    """Create the inventory_orders table if it doesn't exist"""
    conn = await connect_to_db()
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory_orders (
                id SERIAL PRIMARY KEY,
                group_id VARCHAR(50) UNIQUE NOT NULL,
                received_date DATE NOT NULL,
                unit_price DECIMAL(10, 2) NOT NULL,
                quantity INTEGER NOT NULL,
                total_price DECIMAL(12, 2) NOT NULL,
                supplier VARCHAR(255) NOT NULL,
                category VARCHAR(50) NOT NULL,
                material_type VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create index for better performance
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inventory_orders_group_id 
            ON inventory_orders(group_id);
        """)
        
        print("inventory_orders table created successfully")
    except Exception as e:
        print(f"Error creating inventory_orders table: {e}")
    finally:
        await conn.close()

# --------------------------------------------
# ENDPOINTS
# --------------------------------------------
@router.get("/inventory/materials", response_model=PaginatedInventoryResponse)
async def get_materials(
    # Category filter
    category: Optional[str] = Query(None, description="Filter by category: '1st Degree' or '2nd Degree'"),
    
    # Status filter
    status: Optional[str] = Query("available", description="Filter by status: available, used, reserved"),
    
    # Material type filter
    material_type: Optional[str] = Query(None, description="Filter by specific material type"),
    
    # Supplier filter
    supplier: Optional[str] = Query(None, description="Filter by supplier name"),
    
    # Pagination
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    limit: int = Query(50, ge=1, le=1000, description="Items per page (max 1000)"),
    
    # Sorting
    sort_by: str = Query("received_date", description="Sort by: received_date, material_type, weight, unit_price"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    
    # Search
    search: Optional[str] = Query(None, description="Search in material_type, supplier, or barcode"),
    
    current_user: TokenData = Depends(admin_or_manager)
):
    """
    Optimized endpoint to fetch inventory materials with filtering, pagination, and search.
    Perfect for frontend integration with large datasets.
    """
    conn = await connect_to_db()
    try:
        # Build dynamic query
        base_query = "SELECT * FROM inventory WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM inventory WHERE 1=1"
        params = []
        param_count = 0
        
        # Apply filters
        filters_applied = {}
        
        if category:
            if category not in ["1st Degree", "2nd Degree"]:
                raise HTTPException(400, "Category must be '1st Degree' or '2nd Degree'")
            param_count += 1
            base_query += f" AND category = ${param_count}"
            count_query += f" AND category = ${param_count}"
            params.append(category)
            filters_applied["category"] = category
        
        if status:
            param_count += 1
            base_query += f" AND status = ${param_count}"
            count_query += f" AND status = ${param_count}"
            params.append(status)
            filters_applied["status"] = status
        
        if material_type:
            param_count += 1
            base_query += f" AND LOWER(material_type) LIKE LOWER(${param_count})"
            count_query += f" AND LOWER(material_type) LIKE LOWER(${param_count})"
            params.append(f"%{material_type}%")
            filters_applied["material_type"] = material_type
        
        if supplier:
            param_count += 1
            base_query += f" AND LOWER(supplier) LIKE LOWER(${param_count})"
            count_query += f" AND LOWER(supplier) LIKE LOWER(${param_count})"
            params.append(f"%{supplier}%")
            filters_applied["supplier"] = supplier
        
        if search:
            param_count += 1
            search_condition = f" AND (LOWER(material_type) LIKE LOWER(${param_count}) OR LOWER(supplier) LIKE LOWER(${param_count}) OR LOWER(barcode) LIKE LOWER(${param_count}))"
            base_query += search_condition
            count_query += search_condition
            params.append(f"%{search}%")
            filters_applied["search"] = search
        
        # Get total count for pagination
        total_items = await conn.fetchval(count_query, *params)
        
        # Add sorting
        valid_sort_fields = ["received_date", "material_type", "weight", "unit_price", "id", "category"]
        if sort_by not in valid_sort_fields:
            sort_by = "received_date"
        
        if sort_order.lower() not in ["asc", "desc"]:
            sort_order = "desc"
        
        base_query += f" ORDER BY {sort_by} {sort_order.upper()}"
        
        # Add pagination
        offset = (page - 1) * limit
        param_count += 1
        base_query += f" LIMIT ${param_count}"
        params.append(limit)
        
        param_count += 1
        base_query += f" OFFSET ${param_count}"
        params.append(offset)
        
        # Execute query
        items = await conn.fetch(base_query, *params)
        
        # Calculate pagination info
        total_pages = (total_items + limit - 1) // limit  # Ceiling division
        has_next = page < total_pages
        has_prev = page > 1
        
        # Get summary statistics for the filtered results
        summary_query = """
            SELECT 
                COUNT(*) as total_items,
                SUM(weight) as total_weight,
                SUM(total_price) as total_value,
                COUNT(DISTINCT material_type) as unique_materials,
                COUNT(DISTINCT supplier) as unique_suppliers
            FROM inventory WHERE 1=1
        """
        
        # Apply same filters to summary
        summary_params = []
        param_count = 0
        
        if category:
            param_count += 1
            summary_query += f" AND category = ${param_count}"
            summary_params.append(category)
        
        if status:
            param_count += 1
            summary_query += f" AND status = ${param_count}"
            summary_params.append(status)
        
        if material_type:
            param_count += 1
            summary_query += f" AND LOWER(material_type) LIKE LOWER(${param_count})"
            summary_params.append(f"%{material_type}%")
        
        if supplier:
            param_count += 1
            summary_query += f" AND LOWER(supplier) LIKE LOWER(${param_count})"
            summary_params.append(f"%{supplier}%")
        
        if search:
            param_count += 1
            summary_query += f" AND (LOWER(material_type) LIKE LOWER(${param_count}) OR LOWER(supplier) LIKE LOWER(${param_count}) OR LOWER(barcode) LIKE LOWER(${param_count}))"
            summary_params.append(f"%{search}%")
        
        summary_result = await conn.fetchrow(summary_query, *summary_params)
        
        return PaginatedInventoryResponse(
            materials=[InventoryItemResponse(**dict(item)) for item in items],
            pagination={
                "current_page": page,
                "per_page": limit,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
                "showing_from": offset + 1 if items else 0,
                "showing_to": offset + len(items)
            },
            summary={
                "total_items": int(summary_result["total_items"]) if summary_result["total_items"] else 0,
                "total_weight": float(summary_result["total_weight"]) if summary_result["total_weight"] else 0.0,
                "total_value": float(summary_result["total_value"]) if summary_result["total_value"] else 0.0,
                "unique_materials": int(summary_result["unique_materials"]) if summary_result["unique_materials"] else 0,
                "unique_suppliers": int(summary_result["unique_suppliers"]) if summary_result["unique_suppliers"] else 0
            },
            filters_applied=filters_applied
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching materials: {str(e)}")
    finally:
        await conn.close()
# 1) Fetch all inventory items - Admin/Manager only
@router.get("/inventory")
async def get_inventory(current_user: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    items = await conn.fetch("SELECT * FROM inventory ORDER BY id ASC")
    await conn.close()
    return [dict(item) for item in items]

# 2) Add new inventory batch - Admin/Manager only (ENHANCED)
@router.post("/inventory")
async def add_inventory(item: InventoryItem, current_user: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()

    try:
        # Generate a unique group_id (if not provided)
        if not item.group_id:
            item.group_id = str(random.randint(100, 999))  # Random 3-digit ID

        # Check if group_id already exists in inventory_orders
        existing_order = await conn.fetchval(
            "SELECT COUNT(*) FROM inventory_orders WHERE group_id = $1", 
            item.group_id
        )
        
        if existing_order > 0:
            raise HTTPException(400, f"Group ID {item.group_id} already exists. Please use a different group ID.")

        # Calculate total price for the entire order
        total_order_price = item.unit_price * item.quantity

        # Insert into inventory_orders table FIRST
        await conn.execute("""
            INSERT INTO inventory_orders (
                group_id, received_date, unit_price, quantity, 
                total_price, supplier, category, material_type
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, 
            item.group_id,
            item.received_date,
            item.unit_price,
            item.quantity,
            total_order_price,
            item.supplier,
            item.category,
            item.material_type
        )

        # Insert multiple rows into inventory table if quantity > 1
        for i in range(1, item.quantity + 1):
            barcode = generate_serial_number(item.category, item.material_type, item.group_id, i)
            await conn.execute(
                """
                INSERT INTO inventory (
                    category, 
                    material_type, 
                    kind,
                    weight, 
                    quantity, 
                    supplier, 
                    received_date, 
                    group_id, 
                    barcode,
                    density,
                    grade,
                    color,
                    unit_price,
                    total_price
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                item.category,
                item.material_type,
                item.kind,
                item.weight,
                1,  # each batch row has quantity=1
                item.supplier,
                item.received_date,
                item.group_id,
                barcode,
                item.density,
                item.grade,
                item.color,
                item.unit_price,
                item.unit_price * 1  # total_price for each individual batch
            )

        return {
            "message": f"{item.quantity} batches added successfully", 
            "group_id": item.group_id,
            "total_cost": total_order_price,
            "order_recorded": True
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error adding inventory: {str(e)}")
    finally:
        await conn.close()

# NEW ENDPOINT: Get all inventory orders
@router.get("/inventory/orders", response_model=List[InventoryOrderResponse])
async def get_inventory_orders(current_user: TokenData = Depends(admin_or_manager)):
    """Get all inventory orders with their total costs"""
    conn = await connect_to_db()
    try:
        orders = await conn.fetch("""
            SELECT * FROM inventory_orders 
            ORDER BY received_date DESC, created_at DESC
        """)
        return [InventoryOrderResponse(**dict(order)) for order in orders]
    except Exception as e:
        raise HTTPException(500, f"Error fetching inventory orders: {e}")
    finally:
        await conn.close()

# NEW ENDPOINT: Get specific inventory order by group_id
@router.get("/inventory/orders/{group_id}", response_model=InventoryOrderResponse)
async def get_inventory_order_by_group(group_id: str, current_user: TokenData = Depends(admin_or_manager)):
    """Get inventory order details for a specific group_id"""
    conn = await connect_to_db()
    try:
        order = await conn.fetchrow("""
            SELECT * FROM inventory_orders WHERE group_id = $1
        """, group_id)
        
        if not order:
            raise HTTPException(404, f"No inventory order found with group_id: {group_id}")
            
        return InventoryOrderResponse(**dict(order))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching inventory order: {e}")
    finally:
        await conn.close()

# NEW ENDPOINT: Get total spending summary
@router.get("/inventory/orders/summary/spending")
async def get_spending_summary(current_user: TokenData = Depends(admin_or_manager)):
    """Get spending summary by category, material type, and supplier"""
    conn = await connect_to_db()
    try:
        # Total spending by category
        category_spending = await conn.fetch("""
            SELECT category, SUM(total_price) as total_spent, COUNT(*) as order_count
            FROM inventory_orders
            GROUP BY category
            ORDER BY total_spent DESC
        """)
        
        # Total spending by supplier
        supplier_spending = await conn.fetch("""
            SELECT supplier, SUM(total_price) as total_spent, COUNT(*) as order_count
            FROM inventory_orders
            GROUP BY supplier
            ORDER BY total_spent DESC
        """)
        
        # Total spending by material type
        material_spending = await conn.fetch("""
            SELECT material_type, category, SUM(total_price) as total_spent, COUNT(*) as order_count
            FROM inventory_orders
            GROUP BY material_type, category
            ORDER BY total_spent DESC
        """)
        
        # Overall totals
        overall_total = await conn.fetchval("SELECT SUM(total_price) FROM inventory_orders")
        total_orders = await conn.fetchval("SELECT COUNT(*) FROM inventory_orders")
        
        return {
            "overall_summary": {
                "total_spent": float(overall_total) if overall_total else 0,
                "total_orders": total_orders
            },
            "by_category": [dict(row) for row in category_spending],
            "by_supplier": [dict(row) for row in supplier_spending],
            "by_material_type": [dict(row) for row in material_spending]
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching spending summary: {e}")
    finally:
        await conn.close()

# 3) Get all material types - Admin/Manager only
@router.get("/material_types")
async def get_material_types(current_user: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    rows = await conn.fetch("SELECT category, material_type FROM material_types ORDER BY id ASC")
    await conn.close()
    return [dict(r) for r in rows]

# 4) Add a new material type - Admin/Manager only
@router.post("/material_types")
async def add_material_type(material: MaterialType, current_user: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    await conn.execute(
        "INSERT INTO material_types (category, material_type) VALUES ($1, $2)",
        material.category,
        material.material_type
    )
    await conn.close()
    return {"message": "Material type added successfully"}

# 5) Fetch all inventory records for a given group_id - Admin/Manager only
@router.get("/api/inventory/serials/{group_id}")
async def get_inventory_serials(group_id: str, status: str = None):
    conn = await connect_to_db()
    try:
        query = "SELECT * FROM inventory WHERE group_id=$1"
        params = [group_id]
        
        # Add status filter if provided
        if status:
            query += " AND status=$2"
            params.append(status)
            
        items = await conn.fetch(query, *params)
        return [dict(item) for item in items]
    except Exception as e:
        raise HTTPException(500, f"Error fetching serial numbers: {e}")
    finally:
        await conn.close()
        
@router.get("/api/inventory/summary", response_model=List[InventorySummary])
async def get_inventory_summary(current_user: TokenData = Depends(admin_or_manager)):
    """
    Retrieve a summary of available inventory items, grouped by category and material type.
    """
    conn = await connect_to_db()
    try:
        query = """
            SELECT 
                category, 
                material_type,
                COUNT(*) AS available_quantity,
                SUM(weight) AS available_weight
            FROM inventory
            WHERE status = 'available'
            GROUP BY category, material_type
            ORDER BY category, material_type
        """
        rows = await conn.fetch(query)
        return [InventorySummary(**dict(row)) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching inventory summary: {e}")
    finally:
        await conn.close()

async def get_available_weight_by_material_type(conn, material_type: str) -> float:
    """
    Sums weight of all unassigned (not used/activated) batches for given material_type.
    Assumes that used serials are recorded in 'used_materials' table via barcode.
    """
    result = await conn.fetchval("""
        SELECT COALESCE(SUM(i.weight), 0)
        FROM inventory i
        LEFT JOIN used_materials u ON i.barcode = u.barcode
        WHERE LOWER(i.material_type) = $1 AND u.barcode IS NULL
    """, material_type.lower())

    return float(result)

async def get_available_weight_by_material_type_and_degree(
    conn: asyncpg.Connection, 
    material_type: str, 
    degree: str
) -> float:
    """
    Get available weight for a specific material type and degree (category) combination.
    Note: 'degree' in job orders maps to 'category' in inventory
    """
    result = await conn.fetchval("""
        SELECT COALESCE(SUM(i.weight), 0)
        FROM inventory i
        LEFT JOIN used_materials u ON i.barcode = u.barcode
        WHERE LOWER(i.material_type) = $1 
        AND i.category = $2 
        AND u.barcode IS NULL
    """, material_type.lower(), degree)
    
    return float(result) if result else 0.0

# Update price for a specific group_id (ENHANCED)
@router.patch("/inventory/price/{group_id}")
async def update_inventory_price(
    group_id: str, 
    price_update: InventoryPriceUpdate, 
    current_user: TokenData = Depends(admin_or_manager)
):
    conn = await connect_to_db()
    try:
        # Check if group exists in inventory
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM inventory WHERE group_id = $1", group_id
        )
        if existing == 0:
            raise HTTPException(404, f"No inventory found with group_id: {group_id}")
        
        # Get quantity from inventory_orders table
        order_quantity = await conn.fetchval(
            "SELECT quantity FROM inventory_orders WHERE group_id = $1", group_id
        )
        
        if not order_quantity:
            raise HTTPException(404, f"No inventory order found with group_id: {group_id}")
        
        # Calculate new total price
        new_total_price = price_update.unit_price * order_quantity
        
        # Update inventory table
        updated_count = await conn.fetchval("""
            UPDATE inventory 
            SET unit_price = $1, total_price = $1 * quantity
            WHERE group_id = $2
            RETURNING COUNT(*)
        """, price_update.unit_price, group_id)
        
        # Update inventory_orders table
        await conn.execute("""
            UPDATE inventory_orders 
            SET unit_price = $1, total_price = $2
            WHERE group_id = $3
        """, price_update.unit_price, new_total_price, group_id)
        
        return {
            "message": f"Price updated for {updated_count} items in group {group_id}",
            "unit_price": price_update.unit_price,
            "total_price": new_total_price
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(400, f"Error updating price: {str(e)}")
    finally:
        await conn.close()

# Update price for a specific inventory item by ID
@router.patch("/inventory/{item_id}/price")
async def update_single_item_price(
    item_id: int, 
    price_update: InventoryPriceUpdate, 
    current_user: TokenData = Depends(admin_or_manager)
):
    conn = await connect_to_db()
    try:
        # Get current quantity
        item_row = await conn.fetchrow(
            "SELECT quantity FROM inventory WHERE id = $1", item_id
        )
        if not item_row:
            raise HTTPException(404, f"Inventory item with ID {item_id} not found")
        
        # Calculate new total price
        new_total_price = price_update.unit_price * item_row["quantity"]
        
        # Update both unit_price and total_price
        await conn.execute("""
            UPDATE inventory 
            SET unit_price = $1, total_price = $2
            WHERE id = $3
        """, price_update.unit_price, new_total_price, item_id)
        
        return {
            "message": "Price updated successfully",
            "unit_price": price_update.unit_price,
            "total_price": new_total_price
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(400, f"Error updating price: {str(e)}")
    finally:
        await conn.close()

# INITIALIZATION FUNCTION TO CALL ON STARTUP
async def initialize_inventory_orders():
    """Call this function on application startup to create the table"""
    await create_inventory_orders_table()