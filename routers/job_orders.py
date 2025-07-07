from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator, model_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncpg
from collections import defaultdict

# For user auth/roles, referencing your employees.py
from routers.employees import admin_or_manager, TokenData

# 1) Import the helper from inventory.py
from routers.inventory import get_available_weight_by_material_type, get_available_weight_by_material_type_and_degree

router = APIRouter(tags=["job_orders"])

# -------------------------------------------------------
# 1. Database Connection
# -------------------------------------------------------
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# -------------------------------------------------------
# 2. Dynamic Pydantic Models
# -------------------------------------------------------
class ComponentInput(BaseModel):
    material_name: str
    type: str
    quantity: Optional[float] = None
    attributes: Dict[str, Any] = {}

class RawMaterialInput(BaseModel):
    material_type: str
    degree: str
    percentage: float
    attributes: Dict[str, Any] = {}

    @field_validator("degree")  # ✅ MOVE THIS INSIDE THE CLASS
    def validate_degree(cls, v):
        allowed = ["1st Degree", "2nd Degree"]
        if v not in allowed:
            raise ValueError(f"degree must be one of: {allowed}")
        return v

   
class MachineInput(BaseModel):
    machine_type: str
    machine_id: str

class PriceUpdate(BaseModel):
    unit_price: float


# -------------------------------------------------------
# 3. Main JobOrder Model
# -------------------------------------------------------
class JobOrder(BaseModel):
    client_name: str
    product: str
    model: Optional[str] = None
    raw_degree: Optional[str] = None
    order_quantity: int
    unit_price: float  # NEW: Unit price input
    total_price: Optional[float] = None  # NEW: Will be calculated
    notes: Optional[str] = None  # Add this line


    # Dimensions (for certain products like bags)
    length_cm: float = 0
    width_cm: float = 0
    micron_mm: float = 0
    density: float = 0
    flap_cm: float = 0
    gusset1_cm: float = 0
    gusset2_cm: float = 0

    # For hangers or plastic rolls
    unit_weight: float = 0
    stretch_quantity: int = 0

    # Single-operator or single-machine references if needed
    operator_id: Optional[int] = None
    machine_type: Optional[str] = None
    machine_id: Optional[str] = None

    # Dynamic lists
    raw_materials: List[RawMaterialInput] = []
    components: List[ComponentInput] = []
    machines: List[MachineInput] = []

    # ---------- Validators ----------
    @field_validator("raw_degree")
    def validate_raw_degree(cls, v):
        allowed = ["1st Degree", "2nd Degree"]
        if v not in allowed:
            raise ValueError(f"raw_degree must be one of: {allowed}")
        return v

    @field_validator("product")
    def validate_product(cls, v):
        allowed = ["PH", "AB", "SB", "FPB", "TC", "LB", "FSB", "TB", "PR", "PC"]
        if v not in allowed:
            raise ValueError(f"product must be one of {allowed}")
        return v

    @field_validator("model")
    def validate_model(cls, v, info):
        values = info.data
        product = values.get("product")
        if product == "PH":
            allowed = ["WT-19", "WB-12", "WB-14", "WHB-12", "WHB-14"]
            if v not in allowed:
                raise ValueError(f"For Plastic Hanger (PH), model must be in {allowed}.")
        elif product == "AB":
            allowed = ["regular poly bags", "flap poly bags", "gusset poly bags"]
            if v not in allowed:
                raise ValueError(f"For Apparel Bags (AB), model must be in {allowed}.")
        return v
    
    @model_validator(mode='after')
    def validate_material_total(self):
        if self.raw_materials:
            total_percentage = sum(mat.percentage for mat in self.raw_materials)
            if not (99.999 <= total_percentage <= 100.001):
                raise ValueError(
                    f"Sum of material percentages must be 100. Currently it is {total_percentage}."
                )
        return self
    
    @field_validator("unit_price")
    def validate_unit_price(cls, v):
        if v <= 0:
            raise ValueError("Unit price must be greater than 0")
        return v

    @model_validator(mode='after')
    def calculate_total_price(self):
        # Calculate total_price automatically
        if self.unit_price and self.order_quantity:
            self.total_price = self.unit_price * self.order_quantity
        return self
    

# -------------------------------------------------------
# 4. Helper: Generate #ORD-YYYYMMDD-###
# -------------------------------------------------------
async def generate_order_id(conn):
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"#ORD-{today}"
    result = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM job_orders
        WHERE to_char(assigned_date, 'YYYYMMDD') = $1
        """,
        today
    )
    count_for_today = result if result else 0
    order_number = str(count_for_today + 1).zfill(3)
    return f"{prefix}-{order_number}"


def determine_job_order_degree(raw_materials: List[RawMaterialInput]) -> str:
    """
    Determine the overall degree for the job order based on materials used.
    If any material is 2nd degree, the entire job order becomes 2nd degree.
    Otherwise, it's 1st degree.
    """
    for material in raw_materials:
        if material.degree == "2nd Degree":
            return "2nd Degree"
    return "1st Degree"

async def get_available_weight_by_material_type_and_degree(
    conn: asyncpg.Connection, 
    material_type: str, 
    degree: str
) -> float:
    """
     Get available weight for a specific material type and degree combination.
    Note: 'degree' maps to 'category' in the inventory table
    """
    result = await conn.fetchval("""
        SELECT COALESCE(SUM(weight), 0) 
        FROM inventory
         WHERE LOWER(material_type) = $1 AND category = $2  
    """, material_type, degree)
    
    return float(result) if result else 0.0
# -------------------------------------------------------
# 5. Dynamic Validation Functions
# -------------------------------------------------------

async def validate_raw_materials(
    raw_materials: List[RawMaterialInput],
    conn: asyncpg.Connection,
    total_required_weight: float
):
    """
    Validate raw materials considering both material_type and degree.
    """
    # Get inventory data with degree information
    rows = await conn.fetch("SELECT id, material_type, category  FROM inventory")
    material_degree_combinations = set(
        (row["material_type"].lower(), row["category"]) for row in rows
    )

    for material in raw_materials:
        mat_type_lower = material.material_type.lower()
        material_key = (mat_type_lower, material.degree)
        
        if material_key not in material_degree_combinations:
            raise HTTPException(
                400,
                f"Raw material '{material.material_type}' with degree '{material.degree}' not found in inventory."
            )

        # Check weight availability for specific material type and degree
        needed_weight = total_required_weight * (material.percentage / 100.0)
        available_weight = await get_available_weight_by_material_type_and_degree(
            conn, mat_type_lower, material.degree
        )
        
        if available_weight < needed_weight:
            raise HTTPException(
                400,
                f"Insufficient stock for '{material.material_type}' ({material.degree}). "
                f"Needed: {needed_weight:.2f} kg, Available: {available_weight:.2f} kg"
            )

    return True

async def validate_components(
    components: List[ComponentInput],
    conn: asyncpg.Connection,
    order_quantity: int
):
    """
    Validate components with two scenarios:
    1. Direct quantity for solid components (clips, etc.)
    2. Liquid components (inks, solvents) with packaging attributes
    """

    # Fetch base inventory data
    comp_query = """
        SELECT c.id, c.material_name, c.type, c.quantity
        FROM comp_inventory c
    """
    comp_rows = await conn.fetch(comp_query)
    
    # Fetch attributes
    attr_query = """
        SELECT ca.comp_inventory_id, ca.key, ca.value
        FROM comp_inventory_attributes ca
    """
    attr_rows = await conn.fetch(attr_query)
    
    # Build inventory data structure
    inventory = {}
    for row in comp_rows:
        key = (row["material_name"].lower(), row["type"].lower())
        inventory[key] = {
            "id": row["id"],
            "quantity": row["quantity"],
            "attributes": {}
        }
    
    # Add attributes
    for attr in attr_rows:
        comp_id = attr["comp_inventory_id"]
        for item in inventory.values():
            if item["id"] == comp_id:
                item["attributes"][attr["key"].lower()] = attr["value"].lower()
    
    # Validate each component
    for comp in components:
        name_lower = comp.material_name.lower()
        type_lower = comp.type.lower()
        key = (name_lower, type_lower)
        
        # Check if component exists
        if key not in inventory:
            raise HTTPException(
                status_code=400,
                detail=f"Component '{comp.material_name}' with type '{comp.type}' not found in inventory."
            )
        
        inv_item = inventory[key]
        
        # Determine if this is a liquid component (with packaging attribute)
        is_liquid = False
        if "packaging" in inv_item["attributes"]:
            is_liquid = inv_item["attributes"]["packaging"].lower() in ["1litre", "1 litre", "1l"]
        
        if is_liquid:
            # LIQUID COMPONENT LOGIC
            # Get requested liters from attributes
            requested_liters = None
            
            # Look for liters in attributes
            if comp.attributes and "liters" in comp.attributes:
                try:
                    requested_liters = float(comp.attributes["liters"])
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid 'liters' value for liquid component '{comp.material_name}-{comp.type}'."
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing 'liters' in attributes for liquid component '{comp.material_name}-{comp.type}'."
                )
            
            # Check if we have enough quantity (1 quantity = 1 liter package)
            available_liters = inv_item["quantity"]
            if requested_liters > available_liters:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient quantity for liquid component '{comp.material_name}-{comp.type}'. "
                    f"Requested: {requested_liters} liters, Available: {available_liters} liters."
                )
        
        else:
            # SOLID COMPONENT LOGIC - direct quantity
            requested_quantity = None
            
            # Try to get quantity attribute from the component
            if hasattr(comp, "quantity") and comp.quantity is not None:
                try:
                    requested_quantity = float(comp.quantity)
                except (ValueError, TypeError):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid quantity value for component '{comp.material_name}-{comp.type}'."
                    )
            elif comp.attributes and "quantity" in comp.attributes:
                try:
                    requested_quantity = float(comp.attributes["quantity"])
                except (ValueError, TypeError):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid quantity in attributes for component '{comp.material_name}-{comp.type}'."
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing quantity for component '{comp.material_name}-{comp.type}'."
                )
            
            # Check if we have enough in inventory
            available_quantity = inv_item["quantity"]
            if requested_quantity > available_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient quantity for component '{comp.material_name}-{comp.type}'. "
                    f"Requested: {requested_quantity}, Available: {available_quantity}"
                )
    
    return True




async def validate_machines(machines: List[MachineInput], product: str, conn: asyncpg.Connection):
    machine_query = "SELECT id, machine_type, machine_id FROM machines"
    machine_rows = await conn.fetch(machine_query)
    
    available_machines = {
        (row["machine_type"].lower(), row["machine_id"].lower()): row["id"] 
        for row in machine_rows
    }

    for machine in machines:
        machine_key = (machine.machine_type.lower(), machine.machine_id.lower())
        if machine_key not in available_machines:
            raise HTTPException(
                400,
                f"Machine '{machine.machine_type}-{machine.machine_id}' not found in machines table."
            )

    machine_types_provided = {m.machine_type.lower() for m in machines}
    def normalize(s: str) -> str:
     return s.lower().replace(" ", "_")

# Normalize machine types provided by user
    normalized_provided = {normalize(m.machine_type) for m in machines}

    if product == "AB":  # Apparel Bags
        required = {"blowing_film", "printing", "cutting"}
        missing = required - normalized_provided
        if missing:
            raise HTTPException(400, f"Apparel Bags requires machines: {missing}")
    elif product == "PR":
        required = {"blowing_film"}
        missing = required - normalized_provided
        if missing:
            raise HTTPException(400, f"Plastic Rolls requires machine(s): {missing}")
    elif product == "PH":
        required = {"injection_molding"}
        missing = required - normalized_provided
        if missing:
            raise HTTPException(400, f"Plastic Hanger requires machine(s): {missing}")

# Add this after the database connection function
async def update_job_order_progress(conn, job_order_id: int):
    """Update the progress column in database based on target vs remaining weight"""
    await conn.execute("""
        UPDATE job_orders 
        SET progress = CASE 
            WHEN target_weight_no_waste > 0 
            THEN ROUND(
                CAST(100 - ((remaining_target_g / 1000.0) / target_weight_no_waste * 100) AS NUMERIC), 
                2
            )
            ELSE 0 
        END
        WHERE id = $1
    """, job_order_id)
# -------------------------------------------------------
# 6. Calculate Target Weight Based on Product
# -------------------------------------------------------
def calculate_target_weight(order: JobOrder):
    product = order.product
    base_weight = 0.0

    if product == "PH":
        if order.unit_weight <= 0:
            raise HTTPException(400, "For Plastic Hanger, unit_weight must be > 0.")
        base_weight = order.unit_weight * order.order_quantity
        base_weight /= 1000.0

    elif product == "AB":
        if order.model == "regular poly bags":
            # This initially calculates grams
            base_weight = (
                order.length_cm * order.width_cm *
                (order.micron_mm / 10000.0) *
                order.density * 2 *
                order.order_quantity
            )
            # Convert grams -> kilograms
            base_weight /= 1000.0

        elif order.model == "flap poly bags":
            base_weight = (
                (order.length_cm + (order.flap_cm / 2.0)) *
                order.width_cm *
                (order.micron_mm / 10000.0) *
                order.density *
                2 *
                order.order_quantity
            )
            base_weight /= 1000.0

        elif order.model == "gusset poly bags":
            base_weight = (
                order.length_cm *
                (order.width_cm + order.gusset1_cm + order.gusset2_cm) *
                (order.micron_mm / 10000.0) *
                order.density *
                2 *
                order.order_quantity
            )
            base_weight /= 1000.0

        else:
            raise HTTPException(400, "Invalid or missing model for Apparel Bags.")
    elif product == "PR":
        base_weight = order.unit_weight
    else:
        base_weight = order.unit_weight * order.order_quantity

    waste = base_weight * 0.05
    return base_weight, base_weight + waste

# -------------------------------------------------------
# 7. POST /job_orders (Create)
# -------------------------------------------------------
@router.post("/job_orders", dependencies=[Depends(admin_or_manager)])
async def create_job_order(order: JobOrder, token: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    try:
        # A) Generate textual order_id
        order_id = await generate_order_id(conn)

        calculated_raw_degree = determine_job_order_degree(order.raw_materials)
        
        # E) Calculate target weight
        target_weight_no_waste, target_weight_with_waste = calculate_target_weight(order)
        remaining_target_g = int(target_weight_with_waste * 1000)  # kg → g
        
        # B) Validate raw materials (with availability checks)
        await validate_raw_materials(
            raw_materials=order.raw_materials,
            conn=conn,
            total_required_weight=target_weight_with_waste
        )

        # C) Validate components (with quantity checks)
        await validate_components(
            components=order.components,
            conn=conn,
            order_quantity=order.order_quantity
        )
        
        # D) Validate machines
        await validate_machines(order.machines, order.product, conn)
        
        # 🔍 NEW: Check if customer account exists for this client (case-insensitive)
        existing_customer = await conn.fetchrow("""
            SELECT id, total_orders_count, total_amount_due, outstanding_balance, client_name
            FROM customer_accounts 
            WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
        """, order.client_name.strip())
        
        customer_account_id = existing_customer["id"] if existing_customer else None
        
        # Insert job_orders row (UPDATED with customer_account_id)
        job_row = await conn.fetchrow("""
            INSERT INTO job_orders (
                order_id,
                client_name,
                product,
                model,
                raw_degree,
                order_quantity,
                unit_price,
                total_price,
                length_cm,
                width_cm,
                micron_mm,
                density,
                flap_cm,
                gusset1_cm,
                gusset2_cm,
                unit_weight,
                stretch_quantity,
                machine_type,
                machine_id,
                operator_id,
                target_weight_no_waste,
                target_weight_with_waste,
                remaining_target_g,
                notes,
                customer_account_id,
                accounting_status,
                assigned_date,
                status
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8,
                $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26,
                CURRENT_TIMESTAMP,
                'pending'
            )
            RETURNING id
        """,
            order_id,
            order.client_name,
            order.product,
            order.model,
            calculated_raw_degree,
            order.order_quantity,
            order.unit_price,
            order.total_price,
            order.length_cm,
            order.width_cm,
            order.micron_mm,
            order.density,
            order.flap_cm,
            order.gusset1_cm,
            order.gusset2_cm,
            order.unit_weight,
            order.stretch_quantity,
            order.machine_type,
            order.machine_id,
            order.operator_id,
            float(target_weight_no_waste),
            float(target_weight_with_waste),
            remaining_target_g,
            order.notes,
            customer_account_id,  # 🆕 NEW: Link to customer account if exists
            'pending' if not customer_account_id else 'linked'  # 🆕 NEW: Set accounting status
        )            
        job_order_id = job_row["id"]

        await update_job_order_progress(conn, job_order_id)
        
        # 🆕 NEW: If customer account exists, update accounting tables
        customer_linked = False
        if existing_customer:
            try:
                # Create order_accounting record
                await conn.execute("""
                    INSERT INTO order_accounting (
                        customer_account_id,
                        job_order_id,
                        client_name,
                        order_amount,
                        outstanding_balance,
                        payment_status,
                        invoice_status,
                        order_date
                    )
                    VALUES ($1, $2, $3, $4, $4, 'unpaid', 'not_invoiced', CURRENT_TIMESTAMP)
                """,
                    existing_customer["id"],
                    job_order_id,
                    order.client_name,
                    float(order.total_price)
                )
                
                # Update customer account totals
                await conn.execute("""
                    UPDATE customer_accounts 
                    SET 
                        total_orders_count = total_orders_count + 1,
                        total_amount_due = total_amount_due + $1,
                        outstanding_balance = outstanding_balance + $1,
                        last_order_date = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2
                """, float(order.total_price), existing_customer["id"])
                
                customer_linked = True
                
            except Exception as e:
                # Log the error but don't fail the job order creation
                print(f"Warning: Failed to update customer accounting: {str(e)}")
        
        # Insert job_order_machines (unchanged)
        for m in order.machines:
            await conn.execute("""
                INSERT INTO job_order_machines (job_order_id, machine_type, machine_id)
                VALUES ($1, $2, $3)
            """, job_order_id, m.machine_type, m.machine_id)
        
        # Insert job_order_materials (unchanged)
        for mat in order.raw_materials:
            mat_needed = target_weight_with_waste * (mat.percentage / 100.0)
            await conn.execute("""
                INSERT INTO job_order_materials (
                    job_order_id,
                    material_type,
                    percentage,
                    calculated_weight,
                    degree
                )
                VALUES ($1, $2, $3, $4, $5)
            """,
                job_order_id,
                mat.material_type,
                mat.percentage,
                mat_needed,
                mat.degree
            )
        
        # Insert job_order_components (unchanged)
        for comp in order.components:
            component_id = await conn.fetchval("""
                INSERT INTO job_order_components (
                job_order_id, 
                material_name, 
                type,
                quantity
                )
                VALUES ($1, $2, $3, $4)
                RETURNING id
                 """, job_order_id, comp.material_name, comp.type, comp.quantity or 0)

            for attr_key, attr_val in comp.attributes.items():
                await conn.execute("""
                    INSERT INTO job_order_component_attributes (
                        job_order_component_id,
                        job_order_id,           
                        key,
                        value
                    )
                    VALUES ($1, $2, $3, $4)
                """, component_id, job_order_id, attr_key, str(attr_val))
        
        await conn.close()
        
        # 🆕 ENHANCED: Return response with customer accounting info
        response = {
            "message": "Job order created successfully",
            "order_id": order_id,
            "job_order_id": job_order_id,
            "calculated_raw_degree": calculated_raw_degree,
            "customer_accounting": {
                "customer_account_exists": customer_linked,
                "customer_account_id": existing_customer["id"] if existing_customer else None,
                "auto_linked": customer_linked,
                "accounting_status": "linked" if customer_linked else "pending"
            }
        }
        
        # Add suggestion if no customer account exists
        if not customer_linked:
            response["customer_accounting"]["suggestion"] = f"Create customer account for '{order.client_name}' to enable accounting features"
            response["customer_accounting"]["create_account_endpoint"] = f"POST /customer-accounts with client_name: '{order.client_name}'"
        
        return response
    
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error creating job order: {str(e)}")


# 🆕 NEW: Helper endpoint to link existing job orders to customer accounts
@router.post("/job_orders/{job_order_id}/link-to-customer", dependencies=[Depends(admin_or_manager)])
async def link_job_order_to_customer_account(
    job_order_id: int,
    client_name: str = None,  # Optional: override client name
    token: TokenData = Depends(admin_or_manager)
):
    """Link an existing job order to a customer account"""
    conn = await connect_to_db()
    try:
        # Get job order data
        job_order = await conn.fetchrow("""
            SELECT id, client_name, total_price, assigned_date, customer_account_id
            FROM job_orders WHERE id = $1
        """, job_order_id)
        
        if not job_order:
            raise HTTPException(404, f"Job order {job_order_id} not found")
        
        if job_order["customer_account_id"]:
            raise HTTPException(400, f"Job order {job_order_id} is already linked to a customer account")
        
        # Use provided client_name or job order's client_name
        target_client_name = client_name or job_order["client_name"]
        
        # Find customer account
        customer = await conn.fetchrow("""
            SELECT id FROM customer_accounts 
            WHERE LOWER(client_name) = LOWER($1)
        """, target_client_name.strip())
        
        if not customer:
            raise HTTPException(404, f"No customer account found for '{target_client_name}'")
        
        # Link job order to customer account
        await conn.execute("""
            UPDATE job_orders 
            SET customer_account_id = $1, accounting_status = 'linked'
            WHERE id = $2
        """, customer["id"], job_order_id)
        
        # Create order_accounting record
        await conn.execute("""
            INSERT INTO order_accounting (
                customer_account_id,
                job_order_id,
                client_name,
                order_amount,
                outstanding_balance,
                payment_status,
                invoice_status,
                order_date
            )
            VALUES ($1, $2, $3, $4, $4, 'unpaid', 'not_invoiced', $5)
        """,
            customer["id"],
            job_order_id,
            target_client_name,
            float(job_order["total_price"]),
            job_order["assigned_date"]
        )
        
        # Update customer account totals
        await conn.execute("""
            UPDATE customer_accounts 
            SET 
                total_orders_count = total_orders_count + 1,
                total_amount_due = total_amount_due + $1,
                outstanding_balance = outstanding_balance + $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
        """, float(job_order["total_price"]), customer["id"])
        
        await conn.close()
        return {
            "message": "Job order linked to customer account successfully",
            "job_order_id": job_order_id,
            "customer_account_id": customer["id"],
            "client_name": target_client_name,
            "order_amount": float(job_order["total_price"])
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error linking job order: {str(e)}")


# 🆕 NEW: Bulk link multiple job orders to customer accounts
@router.post("/job_orders/bulk-link-to-customers", dependencies=[Depends(admin_or_manager)])
async def bulk_link_job_orders_to_customers(
    job_order_ids: List[int] = None,
    client_name: str = None,  # Link all orders for specific client
    token: TokenData = Depends(admin_or_manager)
):
    """Bulk link job orders to customer accounts"""
    conn = await connect_to_db()
    try:
        linked_orders = []
        errors = []
        
        # Get job orders to process
        if client_name:
            # Get all unlinked orders for specific client
            job_orders = await conn.fetch("""
                SELECT id, client_name, total_price, assigned_date
                FROM job_orders 
                WHERE LOWER(client_name) = LOWER($1) 
                AND customer_account_id IS NULL
            """, client_name.strip())
        elif job_order_ids:
            # Get specific job orders
            job_orders = await conn.fetch("""
                SELECT id, client_name, total_price, assigned_date
                FROM job_orders 
                WHERE id = ANY($1) AND customer_account_id IS NULL
            """, job_order_ids)
        else:
            raise HTTPException(400, "Either job_order_ids or client_name must be provided")
        
        for job_order in job_orders:
            try:
                # Find customer account for this order's client
                customer = await conn.fetchrow("""
                    SELECT id FROM customer_accounts 
                    WHERE LOWER(client_name) = LOWER($1)
                """, job_order["client_name"].strip())
                
                if customer:
                    # Link job order
                    await conn.execute("""
                        UPDATE job_orders 
                        SET customer_account_id = $1, accounting_status = 'linked'
                        WHERE id = $2
                    """, customer["id"], job_order["id"])
                    
                    # Create order_accounting record
                    await conn.execute("""
                        INSERT INTO order_accounting (
                            customer_account_id, job_order_id, client_name,
                            order_amount, outstanding_balance, payment_status,
                            invoice_status, order_date
                        )
                        VALUES ($1, $2, $3, $4, $4, 'unpaid', 'not_invoiced', $5)
                    """,
                        customer["id"], job_order["id"], job_order["client_name"],
                        float(job_order["total_price"]), job_order["assigned_date"]
                    )
                    
                    # Update customer totals
                    await conn.execute("""
                        UPDATE customer_accounts 
                        SET 
                            total_orders_count = total_orders_count + 1,
                            total_amount_due = total_amount_due + $1,
                            outstanding_balance = outstanding_balance + $1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = $2
                    """, float(job_order["total_price"]), customer["id"])
                    
                    linked_orders.append({
                        "job_order_id": job_order["id"],
                        "client_name": job_order["client_name"],
                        "customer_account_id": customer["id"],
                        "amount": float(job_order["total_price"])
                    })
                else:
                    errors.append(f"Job order {job_order['id']}: No customer account found for '{job_order['client_name']}'")
                    
            except Exception as e:
                errors.append(f"Job order {job_order['id']}: {str(e)}")
        
        await conn.close()
        return {
            "message": f"Bulk link completed. Linked {len(linked_orders)} orders.",
            "linked_orders": linked_orders,
            "errors": errors,
            "total_processed": len(job_orders),
            "total_linked": len(linked_orders),
            "total_errors": len(errors)
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error in bulk link operation: {str(e)}")
    


# -------------------------------------------------------
# 8. GET /job_orders (Retrieve All)
# -------------------------------------------------------
@router.get("/job_orders", dependencies=[Depends(admin_or_manager)])
async def get_all_job_orders(token: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    try:
        rows = await conn.fetch("SELECT * FROM job_orders ORDER BY id ASC")
        results = [dict(r) for r in rows]
        await conn.close()
        return results
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving job orders: {str(e)}")

# -------------------------------------------------------
# 9. GET /job_orders/{id} (Retrieve with Details)
# -------------------------------------------------------
@router.get("/job_orders/{id}", dependencies=[Depends(admin_or_manager)])
async def get_job_order_details(id: int, token: TokenData = Depends(admin_or_manager)):
    conn = await connect_to_db()
    try:
        # Main job order
        job_order = await conn.fetchrow("SELECT * FROM job_orders WHERE id = $1", id)
        if not job_order:
            raise HTTPException(404, f"Job order with ID {id} not found")
        
        result = dict(job_order)

        # Operators (based on operator_id field)
        if job_order["operator_id"]:
            operator_row = await conn.fetchrow(
                "SELECT id AS operator_id, name, role FROM employees WHERE id = $1",
                job_order["operator_id"]
            )
            if operator_row:
                result["operators"] = [dict(operator_row)]
            else:
                result["operators"] = []
        else:
            result["operators"] = []

        
        # Materials + attributes
        materials_query = """
            SELECT jm.id, jm.material_type, jm.degree,  jm.percentage, jm.calculated_weight,
                   jma.key, jma.value
            FROM job_order_materials jm
            LEFT JOIN job_order_component_attributes jma 
                ON jm.id = jma.job_order_id
            WHERE jm.job_order_id = $1
        """
        material_rows = await conn.fetch(materials_query, id)
        
        materials_dict = {}
        for row in material_rows:
            mat_id = row["id"]
            if mat_id not in materials_dict:
                materials_dict[mat_id] = {
                    "material_type": row["material_type"],
                    "degree": row["degree"],
                    "percentage": row["percentage"],
                    "calculated_weight": row["calculated_weight"],
                    "attributes": {}
                }
            
            # Add attribute if present
            if row["key"] is not None:
                materials_dict[mat_id]["attributes"][row["key"]] = row["value"]
        
        result["raw_materials"] = list(materials_dict.values())
        
        # Components + attributes
        components_query = """
            SELECT jc.id, jc.material_name, jc.type,
                   jca.key, jca.value
            FROM job_order_components jc
            LEFT JOIN job_order_component_attributes jca 
                ON jc.id = jca.job_order_component_id
            WHERE jc.job_order_id = $1
        """
        component_rows = await conn.fetch(components_query, id)
        
        components_dict = {}
        for row in component_rows:
            comp_id = row["id"]
            if comp_id not in components_dict:
                components_dict[comp_id] = {
                    "material_name": row["material_name"],
                    "type": row["type"],
                    "attributes": {}
                }
            
            if row["key"] is not None:
                components_dict[comp_id]["attributes"][row["key"]] = row["value"]
        
        result["components"] = list(components_dict.values())
        
        # Machines
        machines_query = """
            SELECT machine_type, machine_id
            FROM job_order_machines
            WHERE job_order_id = $1
        """
        machine_rows = await conn.fetch(machines_query, id)
        result["machines"] = [dict(row) for row in machine_rows]
        
        await conn.close()
        return result
    
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving job order details: {str(e)}")
    

@router.patch("/job_orders/{id}/price", dependencies=[Depends(admin_or_manager)])
async def update_job_order_price(
    id: int, 
    price_update: PriceUpdate, 
    token: TokenData = Depends(admin_or_manager)
):
    conn = await connect_to_db()
    try:
        # Get current order quantity
        order_row = await conn.fetchrow(
            "SELECT order_quantity FROM job_orders WHERE id = $1", id
        )
        if not order_row:
            raise HTTPException(404, f"Job order with ID {id} not found")
        
        # Calculate new total price
        new_total_price = price_update.unit_price * order_row["order_quantity"]
        
        # Update both unit_price and total_price
        await conn.execute("""
            UPDATE job_orders 
            SET unit_price = $1, total_price = $2
            WHERE id = $3
        """, price_update.unit_price, new_total_price, id)
        
        await conn.close()
        return {
            "message": "Price updated successfully",
            "unit_price": price_update.unit_price,
            "total_price": new_total_price
        }
    
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error updating price: {str(e)}")
    


@router.post("/job_orders/bulk-update-progress", dependencies=[Depends(admin_or_manager)])
async def bulk_update_progress(token: TokenData = Depends(admin_or_manager)):
    """One-time update to calculate progress for all existing job orders"""
    conn = await connect_to_db()
    try:
        result = await conn.execute("""
            UPDATE job_orders 
            SET progress = CASE 
                WHEN target_weight_no_waste > 0 
                THEN ROUND(
                    CAST(100 - ((remaining_target_g / 1000.0) / target_weight_no_waste * 100) AS NUMERIC), 
                    2
                )
                ELSE 0 
            END
        """)
        
        await conn.close()
        return {
            "message": "Progress updated for all job orders",
            "status": "completed"
        }
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error updating progress: {str(e)}")
    

@router.get("/job_orders/filter/in-progress", dependencies=[Depends(admin_or_manager)])
async def get_in_progress_orders(token: TokenData = Depends(admin_or_manager)):
    """Get all job orders with status 'in_progress' and progress > 10%"""
    conn = await connect_to_db()
    try:
        rows = await conn.fetch("""
            SELECT * FROM job_orders 
            WHERE status = 'in_progress' 
            AND progress > 10
            ORDER BY progress DESC, assigned_date ASC
        """)
        
        results = [dict(r) for r in rows]
        await conn.close()
        
        return {
            "message": f"Found {len(results)} in-progress orders with >10% progress",
            "count": len(results),
            "orders": results
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving in-progress orders: {str(e)}")
    


# Add this endpoint for background calls
@router.post("/job_orders/update-progress-background")
async def update_progress_background():
    """Background endpoint for auto-updating progress"""
    conn = await connect_to_db()
    try:
        await conn.execute("""
            UPDATE job_orders 
            SET progress = CASE 
                WHEN target_weight_no_waste > 0 
                THEN ROUND(CAST(100 - ((remaining_target_g / 1000.0) / target_weight_no_waste * 100) AS NUMERIC), 2)
                ELSE 0 
            END
            WHERE status IN ('in_progress', 'pending')
        """)
        await conn.close()
        return {"status": "updated"}
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error: {str(e)}")