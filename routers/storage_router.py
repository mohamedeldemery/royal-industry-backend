import os
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
from pydantic import BaseModel

from routers.employees import admin_or_manager, TokenData

router = APIRouter(
    prefix="/storage",
    tags=["storage"],
    responses={404: {"description": "Not found"}},
)

# -------------------------------------------------------
# 1. Database Connection
# -------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# -------------------------------------------------------
# Models
# -------------------------------------------------------
class StorageRegistration(BaseModel):
    order_id: int
    notes: Optional[str] = None

class ShipOrder(BaseModel):
    order_id: int
    notes: Optional[str] = None

class StorageItem(BaseModel):
    id: int
    order_id: int
    client_name: str
    product: str
    model: Optional[str] = None
    order_quantity: int
    size_specs: str
    status: str
    storage_date: datetime
    shipping_date: Optional[datetime] = None
    stored_by: str
    shipped_by: Optional[str] = None
    notes: Optional[str] = None

class BatchDetail(BaseModel):
    batch_index: str
    packaged_weight_g: float

class StorageItemWithBatches(StorageItem):
    batches: List[BatchDetail]
class ManualStorageRegistration(BaseModel):
    client_name: str
    product: str  # AB, PR, PH, etc.
    model: Optional[str] = None
    order_quantity: int
    weight_g: Optional[float] = None
    length_cm: Optional[float] = None
    width_cm: Optional[float] = None
    micron_mm: Optional[float] = None
    gusset1_cm: Optional[float] = None
    gusset2_cm: Optional[float] = None
    flap_cm: Optional[float] = None
    unit_weight_g: Optional[float] = None
    notes: Optional[str] = None

class ManualShipOrder(BaseModel):
    storage_id: int  # Use storage table ID instead of order_id
    notes: Optional[str] = None

class ManualStorageItem(BaseModel):
    id: int
    order_id: int  # Will be 0 for manual entries
    client_name: str
    product: str
    model: Optional[str] = None
    order_quantity: int
    size_specs: str
    status: str
    storage_date: datetime
    shipping_date: Optional[datetime] = None
    stored_by: str
    shipped_by: Optional[str] = None
    notes: Optional[str] = None
    is_manual_entry: bool
    manual_weight_g: Optional[float] = None
    manual_length_cm: Optional[float] = None
    manual_width_cm: Optional[float] = None
    manual_micron_mm: Optional[float] = None
    manual_gusset1_cm: Optional[float] = None
    manual_gusset2_cm: Optional[float] = None
    manual_flap_cm: Optional[float] = None
    manual_unit_weight_g: Optional[float] = None




# -------------------------------------------------------
# Router
# -------------------------------------------------------


# -------------------------------------------------------
# Storage Management APIs
# -------------------------------------------------------
@router.post("/manual/register", response_model=ManualStorageItem, dependencies=[Depends(admin_or_manager)])
async def register_manual_storage(storage: ManualStorageRegistration, token: TokenData = Depends(admin_or_manager)):
    """
    Register a manually entered product in storage
    """
    conn = await connect_to_db()
    
    try:
        # Build size specs string based on provided dimensions
        size_specs_parts = []
        
        if storage.length_cm:
            size_specs_parts.append(f"L:{storage.length_cm}cm")
        if storage.width_cm:
            size_specs_parts.append(f"W:{storage.width_cm}cm")
        if storage.micron_mm:
            size_specs_parts.append(f"M:{storage.micron_mm}mm")
        if storage.gusset1_cm:
            size_specs_parts.append(f"G1:{storage.gusset1_cm}cm")
        if storage.gusset2_cm:
            size_specs_parts.append(f"G2:{storage.gusset2_cm}cm")
        if storage.flap_cm:
            size_specs_parts.append(f"F:{storage.flap_cm}cm")
        if storage.unit_weight_g:
            size_specs_parts.append(f"UW:{storage.unit_weight_g}g")
        
        size_specs = " | ".join(size_specs_parts) if size_specs_parts else "Manual Entry"
        
        # Current timestamp for storage registration
        current_time = datetime.now()
        
        # Register the manual entry in storage
        storage_item = await conn.fetchrow(
            """
            INSERT INTO storage_management 
            (order_id, client_name, product, model, order_quantity, size_specs, 
             storage_date, stored_by, notes, is_manual_entry, manual_weight_g,
             manual_length_cm, manual_width_cm, manual_micron_mm, manual_gusset1_cm,
             manual_gusset2_cm, manual_flap_cm, manual_unit_weight_g)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            RETURNING id, order_id, client_name, product, model, order_quantity, size_specs,
                     status, storage_date, shipping_date, stored_by, shipped_by, notes,
                     is_manual_entry, manual_weight_g, manual_length_cm, manual_width_cm,
                     manual_micron_mm, manual_gusset1_cm, manual_gusset2_cm, manual_flap_cm,
                     manual_unit_weight_g
            """,
            0,  # order_id = 0 for manual entries
            storage.client_name,
            storage.product,
            storage.model,
            storage.order_quantity,
            size_specs,
            current_time,
            token.name,
            storage.notes,
            True,  # is_manual_entry = True
            storage.weight_g,
            storage.length_cm,
            storage.width_cm,
            storage.micron_mm,
            storage.gusset1_cm,
            storage.gusset2_cm,
            storage.flap_cm,
            storage.unit_weight_g
        )
        
        return ManualStorageItem(**dict(storage_item))
    
    finally:
        await conn.close()

@router.post("/manual/ship", response_model=ManualStorageItem, dependencies=[Depends(admin_or_manager)])
async def ship_manual_order(shipping: ManualShipOrder, token: TokenData = Depends(admin_or_manager)):
    """
    Mark a manually entered order as shipped from storage
    """
    conn = await connect_to_db()
    
    try:
        # Check if storage item exists and is manual entry
        storage_item = await conn.fetchrow(
            """
            SELECT * FROM storage_management 
            WHERE id = $1 AND is_manual_entry = TRUE
            """,
            shipping.storage_id
        )
        
        if not storage_item:
            raise HTTPException(status_code=404, detail="Manual storage item not found")
            
        if storage_item['status'] == 'shipped':
            raise HTTPException(status_code=400, detail="Item already shipped")
        
        # Current timestamp for shipping
        current_time = datetime.now()
        
        # Update item to shipped status
        updated = await conn.fetchrow(
            """
            UPDATE storage_management 
            SET status = 'shipped', shipping_date = $1, shipped_by = $2,
                notes = CASE 
                          WHEN $3::text IS NULL THEN notes 
                          ELSE COALESCE(notes || ' | ', '') || 'Shipping note: ' || $3::text 
                        END
            WHERE id = $4
            RETURNING id, order_id, client_name, product, model, order_quantity, size_specs,
                     status, storage_date, shipping_date, stored_by, shipped_by, notes,
                     is_manual_entry, manual_weight_g, manual_length_cm, manual_width_cm,
                     manual_micron_mm, manual_gusset1_cm, manual_gusset2_cm, manual_flap_cm,
                     manual_unit_weight_g
            """,
            current_time,
            token.name,
            shipping.notes,
            shipping.storage_id
        )
        
        return ManualStorageItem(**dict(updated))
    
    finally:
        await conn.close()


@router.get("/manual/item/{storage_id}", response_model=ManualStorageItem, dependencies=[Depends(admin_or_manager)])
async def get_manual_storage_item_details(storage_id: int, token: TokenData = Depends(admin_or_manager)):
    """
    Get details for a specific manually entered item in storage
    """
    conn = await connect_to_db()
    
    try:
        item = await conn.fetchrow(
            """
            SELECT id, order_id, client_name, product, model, order_quantity, size_specs,
                   status, storage_date, shipping_date, stored_by, shipped_by, notes,
                   is_manual_entry, manual_weight_g, manual_length_cm, manual_width_cm,
                   manual_micron_mm, manual_gusset1_cm, manual_gusset2_cm, manual_flap_cm,
                   manual_unit_weight_g
            FROM storage_management
            WHERE id = $1 AND is_manual_entry = TRUE
            """,
            storage_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail="Manual storage item not found")
        
        return ManualStorageItem(**dict(item))
    
    finally:
        await conn.close()
        
@router.post("/register", response_model=StorageItemWithBatches, dependencies=[Depends(admin_or_manager)])
async def register_order_in_storage(storage: StorageRegistration, token: TokenData = Depends(admin_or_manager)):
    """
    Register a completed order in storage with current timestamp
    """
    conn = await connect_to_db()
    
    try:
        # Check if order exists and is completed
        order = await conn.fetchrow(
            """
            SELECT id, client_name, product, model, order_quantity, status, 
                   length_cm, width_cm, micron_mm, unit_weight
            FROM job_orders WHERE id = $1
            """,
            storage.order_id
        )
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
            
        if order['status'] != 'completed':
            raise HTTPException(
                status_code=400, 
                detail=f"Order is not ready for storage. Current status: {order['status']}"
            )
        
        # Check if already in storage
        existing = await conn.fetchval(
            "SELECT id FROM storage_management WHERE order_id = $1",
            storage.order_id
        )
        
        if existing:
            raise HTTPException(status_code=400, detail="Order already registered in storage")
        
        # Determine size specs based on product type
        if order['product'] in ['AB', 'PR']:
            size_specs = f"{order['length_cm']}*{order['width_cm']}*{order['micron_mm']}"
        else:
            size_specs = f"Unit Weight: {order['unit_weight']}g"
        
        # Current timestamp for storage registration
        current_time = datetime.now()
        
        # Register the order in storage with explicit timestamp
        storage_item = await conn.fetchrow(
            """
            INSERT INTO storage_management 
            (order_id, client_name, product, model, order_quantity, size_specs, 
             storage_date, stored_by, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, order_id, client_name, product, model, order_quantity, size_specs,
                     status, storage_date, shipping_date, stored_by, shipped_by, notes
            """,
            storage.order_id,
            order['client_name'],
            order['product'],
            order['model'],
            order['order_quantity'],
            size_specs,
            current_time,
            token.name,
            storage.notes
        )
        
        # Get batch details based on product type
        batches = []
        if order['product'] in ['AB', 'PR']:
            # Changed from batch_index to tmp_index for production_rolls
            batch_records = await conn.fetch(
                """
                SELECT tmp_index as batch_index, packaged_weight_g
                FROM production_rolls
                WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                """,
                storage.order_id
            )
            for batch in batch_records:
                batches.append({
                    "batch_index": str(batch['tmp_index']),  # Convert to string
                    "packaged_weight_g": batch['packaged_weight_g']
                })
        else:  # PH or others
            batch_records = await conn.fetch(
                """
                SELECT batch_index, packaged_weight_g
                FROM production_hangers
                WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                """,
                storage.order_id
            )
        
        for batch in batch_records:
            batches.append({
                "batch_index": str(batch['batch_index']),
                "packaged_weight_g": batch['packaged_weight_g']
            })
        
        # Combine order and batch information
        result = dict(storage_item)
        result["batches"] = batches
        
        return result
    
    finally:
        await conn.close()

@router.post("/ship", response_model=StorageItemWithBatches, dependencies=[Depends(admin_or_manager)])
async def ship_order(shipping: ShipOrder, token: TokenData = Depends(admin_or_manager)):
    """
    Mark an order as shipped from storage with current timestamp
    """
    conn = await connect_to_db()
    
    try:
        # Check if order exists in storage and is not already shipped
        storage_item = await conn.fetchrow(
            "SELECT * FROM storage_management WHERE order_id = $1",
            shipping.order_id
        )
        
        if not storage_item:
            raise HTTPException(status_code=404, detail="Order not found in storage")
            
        if storage_item['status'] == 'shipped':
            raise HTTPException(status_code=400, detail="Order already shipped")
        
        # Current timestamp for shipping
        current_time = datetime.now()
        
        # Update order to shipped status with explicit timestamp
        updated = await conn.fetchrow(
            """
            UPDATE storage_management 
            SET status = 'shipped', shipping_date = $1, shipped_by = $2,
                notes = CASE 
                          WHEN $3::text IS NULL THEN notes 
                          ELSE COALESCE(notes || ' | ', '') || 'Shipping note: ' || $3::text 
                        END
            WHERE order_id = $4
            RETURNING id, order_id, client_name, product, model, order_quantity, size_specs,
                     status, storage_date, shipping_date, stored_by, shipped_by, notes
            """,
            current_time,
            token.name,
            shipping.notes,
            shipping.order_id
        )
        
        # Get batch details based on product type
        batches = []
        if storage_item['product'] in ['AB', 'PR']:
            batch_records = await conn.fetch(
                """
                SELECT tmp_index, packaged_weight_g
                FROM production_rolls
                WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                """,
                shipping.order_id
            )
            
            # Process AB/PR batches - INDENTED INSIDE the if block
            for batch in batch_records:
                batches.append({
                    "batch_index": str(batch['tmp_index']),  # Using the original column name
                    "packaged_weight_g": batch['packaged_weight_g']
                })
        else:  # PH or others
            batch_records = await conn.fetch(
                """
                SELECT batch_index, packaged_weight_g
                FROM production_hangers
                WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                """,
                shipping.order_id
            )
            
            # Process other product batches - INDENTED INSIDE the else block
            for batch in batch_records:
                batches.append({
                    "batch_index": str(batch['batch_index']),
                    "packaged_weight_g": batch['packaged_weight_g']
                })
        
        # Combine order and batch information
        result = dict(updated)
        result["batches"] = batches
        
        return result
    
    finally:
        await conn.close()

@router.get("/inventory", response_model=List[StorageItemWithBatches], dependencies=[Depends(admin_or_manager)])
async def get_storage_inventory(status: Optional[str] = None, token: TokenData = Depends(admin_or_manager)):
    """
    Get all orders in storage, optionally filtered by status
    """
    conn = await connect_to_db()
    
    try:
        if status:
            items = await conn.fetch(
                """
                SELECT id, order_id, client_name, product, model, order_quantity, size_specs,
                       status, storage_date, shipping_date, stored_by, shipped_by, notes
                FROM storage_management
                WHERE status = $1
                ORDER BY storage_date DESC
                """,
                status
            )
        else:
            items = await conn.fetch(
                """
                SELECT id, order_id, client_name, product, model, order_quantity, size_specs,
                       status, storage_date, shipping_date, stored_by, shipped_by, notes
                FROM storage_management
                ORDER BY storage_date DESC
                """
            )
        
        result = []
        for item in items:
            item_dict = dict(item)
            
            # Get batch details based on product type
            batches = []
            if item['product'] in ['AB', 'PR']:
                batch_records = await conn.fetch(
                    """
                    SELECT tmp_index, packaged_weight_g
                    FROM production_rolls
                    WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                    """,
                    item['order_id']
                )
                
                # Process AB/PR batches - INDENTED INSIDE the if block
                for batch in batch_records:
                    batches.append({
                        "batch_index": str(batch['tmp_index']),  # Using original column name
                        "packaged_weight_g": batch['packaged_weight_g']
                    })
            else:  # PH or others
                batch_records = await conn.fetch(
                    """
                    SELECT batch_index, packaged_weight_g
                    FROM production_hangers
                    WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                    """,
                    item['order_id']
                )
                
                # Process other product batches - INDENTED INSIDE the else block
                for batch in batch_records:
                    batches.append({
                        "batch_index": str(batch['batch_index']),
                        "packaged_weight_g": batch['packaged_weight_g']
                    })
            
            item_dict["batches"] = batches
            result.append(item_dict)
        
        return result
    
    finally:
        await conn.close()

@router.get("/order/{order_id}", response_model=StorageItemWithBatches, dependencies=[Depends(admin_or_manager)])
async def get_storage_order_details(order_id: int, token: TokenData = Depends(admin_or_manager)):
    """
    Get details for a specific order in storage including timestamps
    """
    conn = await connect_to_db()
    
    try:
        item = await conn.fetchrow(
            """
            SELECT id, order_id, client_name, product, model, order_quantity, size_specs,
                   status, storage_date, shipping_date, stored_by, shipped_by, notes
            FROM storage_management
            WHERE order_id = $1
            """,
            order_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail="Order not found in storage")
        
        item_dict = dict(item)
        
        # Get batch details based on product type
        batches = []
        if item['product'] in ['AB', 'PR']:
            batch_records = await conn.fetch(
                """
                SELECT tmp_index, packaged_weight_g
                FROM production_rolls
                WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                """,
                order_id
            )
            
            # This for loop is now properly indented inside the if block
            for batch in batch_records:
                batches.append({
                    "batch_index": str(batch['tmp_index']),
                    "packaged_weight_g": batch['packaged_weight_g']
                })
        else:  # PH or others
            batch_records = await conn.fetch(
                """
                SELECT batch_index, packaged_weight_g
                FROM production_hangers
                WHERE order_id = $1 AND packaged_weight_g IS NOT NULL
                """,
                order_id
            )
            
            # This for loop is now properly indented inside the else block
            for batch in batch_records:
                batches.append({
                    "batch_index": str(batch['batch_index']),
                    "packaged_weight_g": batch['packaged_weight_g']
                })
        
        item_dict["batches"] = batches
        return item_dict
    
    finally:
        await conn.close()

@router.get("/stats", dependencies=[Depends(admin_or_manager)])
async def get_storage_stats(token: TokenData = Depends(admin_or_manager)):
    """
    Get storage statistics including time-based metrics
    """
    conn = await connect_to_db()
    
    try:
        stats = {}
        
        # Count of orders by status
        status_counts = await conn.fetch(
            """
            SELECT status, COUNT(*) as count
            FROM storage_management
            GROUP BY status
            """
        )
        
        stats["status_counts"] = {record["status"]: record["count"] for record in status_counts}
        
        # Count of orders by product type
        product_counts = await conn.fetch(
            """
            SELECT product, COUNT(*) as count
            FROM storage_management
            WHERE status = 'stored'
            GROUP BY product
            """
        )
        
        stats["product_counts"] = {record["product"]: record["count"] for record in product_counts}
        
        # Recent activity with timestamps
        recent_activity = await conn.fetch(
            """
            SELECT order_id, client_name, status, 
                   CASE 
                     WHEN status = 'stored' THEN storage_date
                     WHEN status = 'shipped' THEN shipping_date
                   END as activity_date,
                   CASE 
                     WHEN status = 'stored' THEN stored_by
                     WHEN status = 'shipped' THEN shipped_by
                   END as activity_by
            FROM storage_management
            ORDER BY 
                CASE 
                    WHEN status = 'stored' THEN storage_date
                    WHEN status = 'shipped' THEN shipping_date
                END DESC
            LIMIT 10
            """
        )
        
        stats["recent_activity"] = [dict(record) for record in recent_activity]
        
        # Time in storage stats (for shipped orders)
        time_in_storage = await conn.fetch(
            """
            SELECT 
                order_id,
                client_name,
                EXTRACT(EPOCH FROM (shipping_date - storage_date))/3600 as hours_in_storage
            FROM storage_management
            WHERE status = 'shipped' AND shipping_date IS NOT NULL
            ORDER BY shipping_date DESC
            LIMIT 15
            """
        )
        
        stats["time_in_storage"] = [dict(record) for record in time_in_storage]
        
        # Average time in storage by product type
        avg_time_by_product = await conn.fetch(
            """
            SELECT 
                product,
                AVG(EXTRACT(EPOCH FROM (shipping_date - storage_date))/3600) as avg_hours_in_storage,
                COUNT(*) as order_count
            FROM storage_management
            WHERE status = 'shipped' AND shipping_date IS NOT NULL
            GROUP BY product
            """
        )
        
        stats["avg_time_by_product"] = [dict(record) for record in avg_time_by_product]
        
        # Current month storage activity
        current_month_activity = await conn.fetch(
            """
            SELECT 
                COUNT(CASE WHEN status = 'stored' THEN 1 END) as orders_stored,
                COUNT(CASE WHEN status = 'shipped' THEN 1 END) as orders_shipped
            FROM storage_management
            WHERE storage_date >= date_trunc('month', CURRENT_DATE)
            """
        )
        
        stats["current_month"] = dict(current_month_activity[0]) if current_month_activity else {"orders_stored": 0, "orders_shipped": 0}
        
        return stats
    
    finally:
        await conn.close()

@router.get("/timeline", dependencies=[Depends(admin_or_manager)])
async def get_storage_timeline(days: int = 30, token: TokenData = Depends(admin_or_manager)):
    """
    Get storage activity timeline over specified number of days
    """
    conn = await connect_to_db()
    
    try:
        timeline = await conn.fetch(
            """
            WITH dates AS (
                SELECT generate_series(
                    CURRENT_DATE - INTERVAL '1 day' * $1, 
                    CURRENT_DATE, 
                    '1 day'::interval
                )::date as day
            )
            SELECT 
                dates.day,
                COUNT(CASE WHEN DATE(sm.storage_date) = dates.day THEN 1 END) as stored,
                COUNT(CASE WHEN DATE(sm.shipping_date) = dates.day THEN 1 END) as shipped
            FROM dates
            LEFT JOIN storage_management sm ON 
                DATE(sm.storage_date) = dates.day OR 
                DATE(sm.shipping_date) = dates.day
            GROUP BY dates.day
            ORDER BY dates.day
            """,
            days  # Now just pass the integer directly
        )
        
        return [dict(record) for record in timeline]
    
    finally:
        await conn.close()
