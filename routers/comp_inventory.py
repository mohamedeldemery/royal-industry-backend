import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, List
from datetime import datetime
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# Import the auth dependencies from employees.py
from routers.employees import admin_or_manager, TokenData

import asyncpg  # or wherever connect_to_db is defined

DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

router = APIRouter(tags=["comp_inventory"])

# ----------------------------
# Pydantic Models
# ----------------------------
class CompInventoryPriceUpdate(BaseModel):
    unit_price: float

class CompInventoryCreate(BaseModel):
    material_name: str
    type: str  # e.g., color if ink/solvent, size otherwise
    weight: float
    quantity: int
    supplier: str
    unit_price: float                    # Unit price per item
    total_price: Optional[float] = None  # Will be calculated
    attributes: Optional[Dict[str, str]] = Field(default_factory=dict)
    
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

# ----------------------------
# Helper: Generate Serial Number
# ----------------------------
async def generate_serial_number(
    conn: asyncpg.Connection,
    material_name: str,
    comp_type: str
) -> str:
    result = await conn.fetchrow("SELECT MAX(id) AS max_id FROM comp_inventory")
    max_id = result["max_id"] if result["max_id"] is not None else 0
    next_id = max_id + 1

    material_part = material_name[:3].upper()
    type_part = comp_type[:3].upper()
    date_part = datetime.now().strftime("%Y%m%d")
    batch_id_str = str(next_id).zfill(3)

    return f"{material_part}-{type_part}-{date_part}-{batch_id_str}"

# ----------------------------
# POST: Create New Component
# ----------------------------
@router.post("/comp_inventory", dependencies=[Depends(admin_or_manager)])
async def create_comp_inventory(
    item: CompInventoryCreate,
    token_data: TokenData = Depends(admin_or_manager)
):
    try:
        conn = await connect_to_db()
        async with conn.transaction():
            # Generate Serial Number
            serial_number = await generate_serial_number(
                conn,
                item.material_name,
                item.type
            )

            # Insert into comp_inventory
            query = """
                INSERT INTO comp_inventory
                    (serial_number, material_name, type, weight, quantity, supplier, 
                     unit_price, total_price, date_added)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                RETURNING id, serial_number
            """
            record = await conn.fetchrow(
                query,
                serial_number,
                item.material_name,
                item.type,
                item.weight,
                item.quantity,
                item.supplier,
                item.unit_price,
                item.total_price
            )

            comp_id = record["id"]

            # Insert dynamic attributes
            if item.attributes:
                for key, value in item.attributes.items():
                    await conn.execute(
                        """
                        INSERT INTO comp_inventory_attributes
                            (comp_inventory_id, key, value)
                        VALUES
                            ($1, $2, $3)
                        """,
                        comp_id, key, value
                    )

            return {
                "id": comp_id,
                "serial_number": record["serial_number"],
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "message": "Component inventory item created successfully."
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating comp_inventory item: {str(e)}"
        )
    finally:
        await conn.close()

# ----------------------------
# GET: List All Components with Attributes
# ----------------------------
@router.get("/comp_inventory", dependencies=[Depends(admin_or_manager)])
async def get_all_comp_inventory(token_data: TokenData = Depends(admin_or_manager)):
    try:
        conn = await connect_to_db()

        # Fetch all components
        components = await conn.fetch("SELECT * FROM comp_inventory ORDER BY id ASC")

        # Fetch attributes for all components
        attributes = await conn.fetch("SELECT * FROM comp_inventory_attributes")

        attr_map = {}
        for attr in attributes:
            comp_id = attr["comp_inventory_id"]
            if comp_id not in attr_map:
                attr_map[comp_id] = {}
            attr_map[comp_id][attr["key"]] = attr["value"]

        # Merge results
        items = []
        for comp in components:
            items.append({
                "id": comp["id"],
                "serial_number": comp["serial_number"],
                "material_name": comp["material_name"],
                "type": comp["type"],
                "weight": comp["weight"],
                "quantity": comp["quantity"],
                "supplier": comp["supplier"],
                "unit_price": comp["unit_price"],
                "total_price": comp["total_price"],
                "date_added": comp["date_added"],
                "attributes": attr_map.get(comp["id"], {})
            })

        return items
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving comp_inventory items: {str(e)}"
        )
    finally:
        await conn.close()

# ----------------------------
# STANDARDIZATION ENDPOINTS
# ----------------------------

# NEW: Get existing materials for standardization
@router.get("/comp_inventory/materials", dependencies=[Depends(admin_or_manager)])
async def get_existing_materials(token_data: TokenData = Depends(admin_or_manager)):
    """
    Get all existing material names and types to help with standardization.
    Returns unique combinations of material_name and type for suggestions.
    """
    try:
        conn = await connect_to_db()
        
        # Get all unique material-type combinations
        materials = await conn.fetch("""
            SELECT DISTINCT material_name, type, COUNT(*) as usage_count
            FROM comp_inventory 
            GROUP BY material_name, type
            ORDER BY material_name, usage_count DESC
        """)
        
        return [
            {
                "material_name": material["material_name"],
                "type": material["type"],
                "usage_count": material["usage_count"]
            }
            for material in materials
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving materials: {str(e)}"
        )
    finally:
        await conn.close()

# NEW: Get component statistics by category
@router.get("/comp_inventory/stats/category", dependencies=[Depends(admin_or_manager)])
async def get_component_stats_by_category(token_data: TokenData = Depends(admin_or_manager)):
    """
    Get component statistics grouped by category for better tracking.
    """
    try:
        conn = await connect_to_db()
        
        # Get statistics by category (from attributes)
        stats = await conn.fetch("""
            SELECT 
                cia.value as category,
                COUNT(DISTINCT ci.id) as component_count,
                SUM(ci.quantity) as total_quantity,
                SUM(ci.total_price) as total_value,
                AVG(ci.unit_price) as avg_unit_price
            FROM comp_inventory ci
            JOIN comp_inventory_attributes cia ON ci.id = cia.comp_inventory_id
            WHERE cia.key = 'category'
            GROUP BY cia.value
            ORDER BY total_value DESC
        """)
        
        return [
            {
                "category": stat["category"],
                "component_count": stat["component_count"],
                "total_quantity": stat["total_quantity"],
                "total_value": float(stat["total_value"]) if stat["total_value"] else 0,
                "avg_unit_price": float(stat["avg_unit_price"]) if stat["avg_unit_price"] else 0
            }
            for stat in stats
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving category stats: {str(e)}"
        )
    finally:
        await conn.close()

# NEW: Get similar materials (for suggesting standardization)
@router.get("/comp_inventory/similar/{material_name}", dependencies=[Depends(admin_or_manager)])
async def get_similar_materials(
    material_name: str, 
    token_data: TokenData = Depends(admin_or_manager)
):
    """
    Get materials with similar names to help identify potential duplicates.
    Uses fuzzy matching to suggest consolidation opportunities.
    """
    try:
        conn = await connect_to_db()
        
        # Get materials that might be similar (basic similarity check)
        similar_materials = await conn.fetch("""
            SELECT DISTINCT material_name, type, COUNT(*) as usage_count
            FROM comp_inventory 
            WHERE LOWER(material_name) LIKE $1 
               OR LOWER(material_name) LIKE $2
               OR LOWER(material_name) LIKE $3
            GROUP BY material_name, type
            ORDER BY usage_count DESC
        """, 
            f"%{material_name.lower()}%",
            f"{material_name.lower()}%",
            f"%{material_name.lower()}"
        )
        
        return [
            {
                "material_name": material["material_name"],
                "type": material["type"],
                "usage_count": material["usage_count"],
                "similarity_reason": "name_match"
            }
            for material in similar_materials
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error finding similar materials: {str(e)}"
        )
    finally:
        await conn.close()

# NEW: Enhanced search endpoint with category filtering
@router.get("/comp_inventory/search", dependencies=[Depends(admin_or_manager)])
async def search_components(
    category: Optional[str] = None,
    material_name: Optional[str] = None,
    material_type: Optional[str] = None,
    supplier: Optional[str] = None,
    token_data: TokenData = Depends(admin_or_manager)
):
    """
    Advanced search for components with multiple filters.
    Helps with inventory management and standardization tracking.
    """
    try:
        conn = await connect_to_db()
        
        # Build dynamic query based on filters
        conditions = []
        params = []
        param_count = 0
        
        base_query = """
            SELECT ci.*, cia_cat.value as category
            FROM comp_inventory ci
            LEFT JOIN comp_inventory_attributes cia_cat ON ci.id = cia_cat.comp_inventory_id AND cia_cat.key = 'category'
            WHERE 1=1
        """
        
        if category:
            param_count += 1
            conditions.append(f"cia_cat.value ILIKE ${param_count}")
            params.append(f"%{category}%")
            
        if material_name:
            param_count += 1
            conditions.append(f"ci.material_name ILIKE ${param_count}")
            params.append(f"%{material_name}%")
            
        if material_type:
            param_count += 1
            conditions.append(f"ci.type ILIKE ${param_count}")
            params.append(f"%{material_type}%")
            
        if supplier:
            param_count += 1
            conditions.append(f"ci.supplier ILIKE ${param_count}")
            params.append(f"%{supplier}%")
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
            
        base_query += " ORDER BY ci.date_added DESC"
        
        components = await conn.fetch(base_query, *params)
        
        # Get attributes for each component
        component_ids = [comp["id"] for comp in components]
        if component_ids:
            attributes = await conn.fetch("""
                SELECT comp_inventory_id, key, value 
                FROM comp_inventory_attributes 
                WHERE comp_inventory_id = ANY($1)
            """, component_ids)
            
            # Group attributes by component ID
            attr_map = {}
            for attr in attributes:
                comp_id = attr["comp_inventory_id"]
                if comp_id not in attr_map:
                    attr_map[comp_id] = {}
                attr_map[comp_id][attr["key"]] = attr["value"]
        else:
            attr_map = {}
        
        # Build response
        result = []
        for comp in components:
            result.append({
                "id": comp["id"],
                "serial_number": comp["serial_number"],
                "material_name": comp["material_name"],
                "type": comp["type"],
                "weight": comp["weight"],
                "quantity": comp["quantity"],
                "supplier": comp["supplier"],
                "unit_price": comp["unit_price"],
                "total_price": comp["total_price"],
                "date_added": comp["date_added"],
                "category": comp["category"],
                "attributes": attr_map.get(comp["id"], {})
            })
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error searching components: {str(e)}"
        )
    finally:
        await conn.close()

# NEW: Get standardization suggestions
@router.get("/comp_inventory/standardization/suggestions", dependencies=[Depends(admin_or_manager)])
async def get_standardization_suggestions(token_data: TokenData = Depends(admin_or_manager)):
    """
    Get suggestions for standardizing component entries.
    Identifies potential duplicates and inconsistencies.
    """
    try:
        conn = await connect_to_db()
        
        # Find potential duplicates based on similar names
        potential_duplicates = await conn.fetch("""
            WITH similar_materials AS (
                SELECT 
                    material_name,
                    type,
                    COUNT(*) as count,
                    ARRAY_AGG(DISTINCT supplier) as suppliers,
                    AVG(unit_price) as avg_price,
                    STDDEV(unit_price) as price_deviation
                FROM comp_inventory
                GROUP BY LOWER(TRIM(material_name)), LOWER(TRIM(type))
                HAVING COUNT(*) > 1
            )
            SELECT * FROM similar_materials
            WHERE price_deviation > (avg_price * 0.1) -- Price varies by more than 10%
            ORDER BY count DESC
        """)
        
        # Find materials without categories
        uncategorized = await conn.fetch("""
            SELECT ci.id, ci.material_name, ci.type, ci.supplier
            FROM comp_inventory ci
            LEFT JOIN comp_inventory_attributes cia ON ci.id = cia.comp_inventory_id AND cia.key = 'category'
            WHERE cia.value IS NULL
            ORDER BY ci.date_added DESC
            LIMIT 20
        """)
        
        return {
            "potential_duplicates": [
                {
                    "material_name": dup["material_name"],
                    "type": dup["type"],
                    "count": dup["count"],
                    "suppliers": dup["suppliers"],
                    "avg_price": float(dup["avg_price"]) if dup["avg_price"] else 0,
                    "price_deviation": float(dup["price_deviation"]) if dup["price_deviation"] else 0
                }
                for dup in potential_duplicates
            ],
            "uncategorized_items": [
                {
                    "id": item["id"],
                    "material_name": item["material_name"],
                    "type": item["type"],
                    "supplier": item["supplier"]
                }
                for item in uncategorized
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting standardization suggestions: {str(e)}"
        )
    finally:
        await conn.close()

# NEW: Get unique categories from existing data
@router.get("/comp_inventory/categories", dependencies=[Depends(admin_or_manager)])
async def get_existing_categories(token_data: TokenData = Depends(admin_or_manager)):
    """
    Get all existing categories to help with standardization and suggestions.
    """
    try:
        conn = await connect_to_db()
        
        categories = await conn.fetch("""
            SELECT DISTINCT cia.value as category, COUNT(*) as usage_count
            FROM comp_inventory_attributes cia
            WHERE cia.key = 'category'
            GROUP BY cia.value
            ORDER BY usage_count DESC
        """)
        
        return [
            {
                "category": cat["category"],
                "usage_count": cat["usage_count"]
            }
            for cat in categories
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving categories: {str(e)}"
        )
    finally:
        await conn.close()

# NEW: Get materials by category
@router.get("/comp_inventory/materials/by-category/{category}", dependencies=[Depends(admin_or_manager)])
async def get_materials_by_category(
    category: str,
    token_data: TokenData = Depends(admin_or_manager)
):
    """
    Get all materials that belong to a specific category.
    """
    try:
        conn = await connect_to_db()
        
        materials = await conn.fetch("""
            SELECT DISTINCT ci.material_name, COUNT(*) as usage_count
            FROM comp_inventory ci
            JOIN comp_inventory_attributes cia ON ci.id = cia.comp_inventory_id
            WHERE cia.key = 'category' AND cia.value = $1
            GROUP BY ci.material_name
            ORDER BY usage_count DESC
        """, category)
        
        return [
            {
                "material_name": mat["material_name"],
                "usage_count": mat["usage_count"]
            }
            for mat in materials
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving materials for category: {str(e)}"
        )
    finally:
        await conn.close()

# NEW: Get types by material
@router.get("/comp_inventory/types/by-material/{material_name}", dependencies=[Depends(admin_or_manager)])
async def get_types_by_material(
    material_name: str,
    token_data: TokenData = Depends(admin_or_manager)
):
    """
    Get all types that belong to a specific material.
    """
    try:
        conn = await connect_to_db()
        
        types = await conn.fetch("""
            SELECT DISTINCT type, COUNT(*) as usage_count
            FROM comp_inventory
            WHERE material_name = $1
            GROUP BY type
            ORDER BY usage_count DESC
        """, material_name)
        
        return [
            {
                "type": typ["type"],
                "usage_count": typ["usage_count"]
            }
            for typ in types
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving types for material: {str(e)}"
        )
    finally:
        await conn.close()

# ----------------------------
# EXISTING ENDPOINTS (Updated)
# ----------------------------

# PATCH: Update Component Price by ID
@router.patch("/comp_inventory/{item_id}/price", dependencies=[Depends(admin_or_manager)])
async def update_comp_inventory_price(
    item_id: int,
    price_update: CompInventoryPriceUpdate,
    token_data: TokenData = Depends(admin_or_manager)
):
    try:
        conn = await connect_to_db()
        
        # Get current quantity
        item_row = await conn.fetchrow(
            "SELECT quantity FROM comp_inventory WHERE id = $1", item_id
        )
        if not item_row:
            raise HTTPException(404, f"Component inventory item with ID {item_id} not found")
        
        # Calculate new total price
        new_total_price = price_update.unit_price * item_row["quantity"]
        
        # Update both unit_price and total_price
        await conn.execute("""
            UPDATE comp_inventory 
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

# GET: Get Component by ID with Details
@router.get("/comp_inventory/{item_id}", dependencies=[Depends(admin_or_manager)])
async def get_comp_inventory_by_id(
    item_id: int,
    token_data: TokenData = Depends(admin_or_manager)
):
    try:
        conn = await connect_to_db()
        
        # Get component details
        component = await conn.fetchrow(
            "SELECT * FROM comp_inventory WHERE id = $1", item_id
        )
        if not component:
            raise HTTPException(404, f"Component inventory item with ID {item_id} not found")
        
        # Get attributes
        attributes = await conn.fetch(
            "SELECT key, value FROM comp_inventory_attributes WHERE comp_inventory_id = $1",
            item_id
        )
        
        attr_dict = {attr["key"]: attr["value"] for attr in attributes}
        
        return {
            "id": component["id"],
            "serial_number": component["serial_number"],
            "material_name": component["material_name"],
            "type": component["type"],
            "weight": component["weight"],
            "quantity": component["quantity"],
            "supplier": component["supplier"],
            "unit_price": component["unit_price"],
            "total_price": component["total_price"],
            "date_added": component["date_added"],
            "attributes": attr_dict
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(400, f"Error retrieving component: {str(e)}")
    finally:
        await conn.close()