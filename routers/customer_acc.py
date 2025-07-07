from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, field_validator, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import asyncpg
from decimal import Decimal
from enum import Enum
import json

# Import authentication from your existing system
from routers.employees import admin_or_manager, TokenData

router = APIRouter(tags=["accounting"])

# Database connection
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# -------------------------------------------------------
# Enums for status fields
# -------------------------------------------------------
class PaymentStatus(str, Enum):
    paid = "paid"
    unpaid = "unpaid"
    partial = "partial"
    overdue = "overdue"

class PaymentMethod(str, Enum):
    bank_transfer = "bank_transfer"
    cash = "cash"
    check = "check"
    credit_card = "credit_card"
    online = "online"
    other = "other"

class BankOrCash(str, Enum):
    bank = "bank"
    cash = "cash"

# -------------------------------------------------------
# Pydantic Models
# -------------------------------------------------------
class CustomerAccountCreateByName(BaseModel):
    client_name: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_person_name: Optional[str] = None
    company_address: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    payment_terms: str = "Net 30"
    currency: str = "USD"
    credit_limit: Optional[float] = 0.00
    tax_id: Optional[str] = None
    industry: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

    @field_validator("client_name")
    def validate_client_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError("Client name must be at least 2 characters")
        return v.strip()

class CustomerAccountUpdate(BaseModel):
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_person_name: Optional[str] = None
    shipping_address: Optional[str] = None
    currency: Optional[str] = None
    payment_terms: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

class InvoiceCreate(BaseModel):
    customer_account_id: int
    job_order_id: int
    po_reference: Optional[str] = None
    tax_percentage: float = 0.00
    due_days: int = 30
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

    @field_validator("tax_percentage")
    def validate_tax_percentage(cls, v):
        if v < 0 or v > 100:
            raise ValueError("Tax percentage must be between 0 and 100")
        return v

    @field_validator("due_days")
    def validate_due_days(cls, v):
        if v < 0:
            raise ValueError("Due days must be non-negative")
        return v

class ReceiptCreate(BaseModel):
    customer_account_id: int
    job_order_id: int
    amount_received: float
    payment_method: PaymentMethod
    bank_or_cash: BankOrCash
    invoice_id: Optional[int] = None
    transaction_reference: Optional[str] = None
    bank_name: Optional[str] = None
    check_number: Optional[str] = None
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None

class ClientOrderSummary(BaseModel):
    job_order_id: int
    order_id: str
    product: str
    model: Optional[str]
    order_amount: float
    payment_status: str
    invoice_status: str
    order_date: datetime
    due_date: Optional[datetime]

   

class CustomFieldDefinition(BaseModel):
    table_name: str
    field_name: str
    field_type: str
    field_label: str
    field_options: Optional[Dict[str, Any]] = None
    is_required: bool = False
    default_value: Optional[str] = None
    validation_rules: Optional[Dict[str, Any]] = None
    display_order: int = 0

    @field_validator("table_name")
    def validate_table_name(cls, v):
        allowed_tables = ["customer_accounts", "invoices", "receipts"]
        if v not in allowed_tables:
            raise ValueError(f"Table name must be one of: {allowed_tables}")
        return v

    @field_validator("field_type")
    def validate_field_type(cls, v):
        allowed_types = ["text", "number", "date", "boolean", "select", "textarea"]
        if v not in allowed_types:
            raise ValueError(f"Field type must be one of: {allowed_types}")
            
        return v

# -------------------------------------------------------
# Helper Functions
# -------------------------------------------------------
async def get_job_order_data(conn: asyncpg.Connection, job_order_id: int):
    """Fetch job order data for accounting purposes"""
    job_order = await conn.fetchrow("""
        SELECT id, client_name, product, model, total_price, order_id
        FROM job_orders 
        WHERE id = $1
    """, job_order_id)
    
    if not job_order:
        raise HTTPException(404, f"Job order with ID {job_order_id} not found")
    
    return dict(job_order)

async def get_similar_customers_by_name(conn: asyncpg.Connection, client_name: str):
    """Get all existing customer accounts with similar names (case-insensitive)"""
    customers = await conn.fetch("""
        SELECT id, client_name, 
               COALESCE(total_orders_count, 0) as total_orders_count, 
               COALESCE(total_amount_due, 0) as total_amount_due, 
               COALESCE(outstanding_balance, 0) as outstanding_balance, 
               account_status
        FROM customer_accounts 
        WHERE LOWER(TRIM(COALESCE(client_name, ''))) = LOWER(TRIM($1))
           OR LOWER(COALESCE(client_name, '')) LIKE LOWER($2)
           OR LOWER(COALESCE(client_name, '')) LIKE LOWER($3)
    """, 
    client_name.strip(), 
    f"%{client_name.strip()}%",
    f"{client_name.strip()}%"
    )
    return [dict(customer) for customer in customers]

async def get_all_client_orders(conn: asyncpg.Connection, client_name: str):
    """Get all job orders for a client name"""
    orders = await conn.fetch("""
        SELECT id, order_id, client_name, product, model, total_price, 
               assigned_date, status
        FROM job_orders 
        WHERE LOWER(client_name) = LOWER($1)
        ORDER BY assigned_date DESC
    """, client_name.strip())
    return [dict(order) for order in orders]

async def calculate_client_totals(conn: asyncpg.Connection, client_name: str):
    """Calculate total orders and amounts for a client"""
    totals = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total_orders,
            COALESCE(SUM(total_price), 0) as total_amount_due
        FROM job_orders 
        WHERE LOWER(client_name) = LOWER($1)
        AND status != 'cancelled'
    """, client_name.strip())
    
    if totals:
        result = dict(totals)
        # Ensure total_amount_due is never None
        if result["total_amount_due"] is None:
            result["total_amount_due"] = 0
        return result
    else:
        return {"total_orders": 0, "total_amount_due": 0}

async def generate_invoice_number(conn: asyncpg.Connection):
    """Generate unique invoice number"""
    today = datetime.now().strftime("%Y")
    
    # Get the next sequence number for this year
    count = await conn.fetchval("""
        SELECT COUNT(*) FROM invoices 
        WHERE EXTRACT(YEAR FROM invoice_date) = $1
    """, int(today))
    
    sequence = str(count + 1).zfill(6)
    return f"INV-{today}-{sequence}"

async def generate_receipt_number(conn: asyncpg.Connection):
    """Generate unique receipt number"""
    today = datetime.now().strftime("%Y")
    
    count = await conn.fetchval("""
        SELECT COUNT(*) FROM receipts 
        WHERE EXTRACT(YEAR FROM payment_date) = $1
    """, int(today))
    
    sequence = str(count + 1).zfill(6)
    return f"RCP-{today}-{sequence}"

# -------------------------------------------------------
# Customer Accounts Endpoints
# -------------------------------------------------------
@router.post("/customer-accounts", dependencies=[Depends(admin_or_manager)])





async def create_customer_account_by_name(
    account_data: CustomerAccountCreateByName,
    force_create: bool = Query(False, description="Force creation even if similar names exist"),
    token: TokenData = Depends(admin_or_manager)
):
    """Create customer account by client name and auto-link all their orders (CASE-INSENSITIVE)"""
    conn = await connect_to_db()
    try:
        # Check for similar customer names (case-insensitive)
        similar_customers = await get_similar_customers_by_name(conn, account_data.client_name)
        
        # Check for exact match (case-insensitive)
        exact_match = None
        for customer in similar_customers:
            if customer["client_name"].lower().strip() == account_data.client_name.lower().strip():
                exact_match = customer
                break
        
        if exact_match:
            await conn.close()
            raise HTTPException(400, f"Customer account already exists for '{exact_match['client_name']}' (ID: {exact_match['id']})")
        
        # If similar names found and force_create is False, return them for user decision
        if similar_customers and not force_create:
            await conn.close()
            return {
                "action_required": True,
                "message": f"Found {len(similar_customers)} similar customer name(s). Please review and use force_create=true if you want to create anyway.",
                "similar_customers": similar_customers,
                "suggested_action": "Review the similar names above. If none match, add ?force_create=true to the request URL to proceed."
            }
        
        # Get all job orders for this client (CASE-INSENSITIVE)
        client_orders = await conn.fetch("""
            SELECT id, order_id, client_name, product, model, total_price, 
                   assigned_date, status
            FROM job_orders 
            WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
            ORDER BY assigned_date DESC
        """, account_data.client_name.strip())
        
        if not client_orders:
            await conn.close()
            raise HTTPException(404, f"No job orders found for client '{account_data.client_name}' (case-insensitive search)")
        
        client_orders = [dict(order) for order in client_orders]
        
        # Calculate totals from all orders with comprehensive null handling
        totals_result = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_orders,
                COALESCE(SUM(CASE WHEN total_price IS NOT NULL THEN total_price ELSE 0 END), 0) as total_amount_due
            FROM job_orders 
            WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
            AND status != 'cancelled'
        """, account_data.client_name.strip())
        
        # Safely extract totals with default values
        if totals_result:
            total_orders = totals_result["total_orders"] if totals_result["total_orders"] is not None else 0
            total_amount_due = totals_result["total_amount_due"] if totals_result["total_amount_due"] is not None else 0.0
        else:
            total_orders = 0
            total_amount_due = 0.0
        
        # Ensure we have numeric values
        total_orders = int(total_orders) if total_orders is not None else 0
        total_amount_due = float(total_amount_due) if total_amount_due is not None else 0.0
        
        # FIXED: Calculate last_order_date safely with proper timezone handling
        last_order_date = None
        if client_orders:
            valid_dates = []
            for order in client_orders:
                date_val = order.get("assigned_date")
                if date_val is not None:
                    try:
                        # Convert to naive datetime if it's timezone-aware
                        if hasattr(date_val, 'tzinfo') and date_val.tzinfo is not None:
                            # Convert timezone-aware to naive (UTC)
                            if date_val.tzinfo.utcoffset(date_val) is not None:
                                date_val = date_val.replace(tzinfo=None)
                        
                        # Ensure it's a datetime object
                        if hasattr(date_val, 'year'):  # Check if it's a datetime-like object
                            valid_dates.append(date_val)
                    except Exception as e:
                        # Skip invalid dates
                        print(f"Skipping invalid date: {date_val}, error: {e}")
                        continue
            
            last_order_date = max(valid_dates) if valid_dates else None
        
        # Create customer account with safe values
        customer_id = await conn.fetchval("""
            INSERT INTO customer_accounts (
                client_name, contact_email, contact_phone, contact_person_name,
                company_address, billing_address, shipping_address, payment_terms,
                currency, credit_limit, tax_id, industry, custom_fields,
                total_orders_count, total_amount_due, outstanding_balance,
                account_status, last_order_date
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $15, 'active', $16)
            RETURNING id
        """,
            account_data.client_name.strip(),
            account_data.contact_email,
            account_data.contact_phone,
            account_data.contact_person_name,
            account_data.company_address,
            account_data.billing_address,
            account_data.shipping_address,
            account_data.payment_terms,
            account_data.currency,
            float(account_data.credit_limit) if account_data.credit_limit is not None else 0.0,
            account_data.tax_id,
            account_data.industry,
            json.dumps(account_data.custom_fields) if account_data.custom_fields else None,
            total_orders,
            total_amount_due,
            last_order_date
        )
        
        # Update all job orders to link to this customer account (CASE-INSENSITIVE)
        job_order_ids = [order["id"] for order in client_orders if order.get("id") is not None]
        if job_order_ids:
            await conn.execute("""
                UPDATE job_orders 
                SET customer_account_id = $1 
                WHERE id = ANY($2)
            """, customer_id, job_order_ids)
        
        # Create order_accounting records for each order
        for order in client_orders:
            if order.get("id") is not None and order.get("total_price") is not None:
                order_amount = float(order["total_price"]) if order["total_price"] is not None else 0.0
                
                # FIXED: Handle assigned_date properly for order_accounting
                order_date = order.get("assigned_date")
                if order_date and hasattr(order_date, 'tzinfo') and order_date.tzinfo is not None:
                    order_date = order_date.replace(tzinfo=None)
                
                await conn.execute("""
                    INSERT INTO order_accounting (
                        customer_account_id, job_order_id, client_name,
                        order_amount, outstanding_balance, order_date
                    )
                    VALUES ($1, $2, $3, $4, $4, $5)
                """,
                    customer_id,
                    order["id"],
                    account_data.client_name.strip(),
                    order_amount,
                    order_date
                )
        
        await conn.close()
        return {
            "message": "Customer account created successfully",
            "customer_id": customer_id,
            "client_name": account_data.client_name.strip(),
            "total_orders_linked": len([o for o in client_orders if o.get("id") is not None]),
            "total_amount_due": total_amount_due,
            "linked_orders": [
                {
                    "id": o["id"], 
                    "order_id": o.get("order_id", ""), 
                    "amount": float(o["total_price"]) if o.get("total_price") is not None else 0.0
                } 
                for o in client_orders if o.get("id") is not None
            ],
            "note": "All orders with matching client name (case-insensitive) were automatically linked to this account"
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error creating customer account: {str(e)}")


# ALTERNATIVE: Simpler helper function to handle datetime conversion
def safe_datetime_to_naive(dt):
    """Convert datetime to naive datetime, handling timezone-aware objects"""
    if dt is None:
        return None
    
    try:
        # If it's timezone-aware, convert to naive
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None
    

    
@router.get("/customer-accounts/simple", dependencies=[Depends(admin_or_manager)])
async def get_customer_accounts_simple(
    token: TokenData = Depends(admin_or_manager),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """Get simple list of customer accounts with just client_name, total_orders_count, total_amount_due, outstanding_balance"""
    conn = await connect_to_db()
    try:
        accounts = await conn.fetch("""
            SELECT 
                client_name,
                COALESCE(total_orders_count, 0) as total_orders_count,
                COALESCE(total_amount_due, 0) as total_amount_due,
                COALESCE(outstanding_balance, 0) as outstanding_balance
            FROM customer_accounts
            ORDER BY client_name
            LIMIT $1 OFFSET $2
        """, limit, skip)
        
        total_count = await conn.fetchval("SELECT COUNT(*) FROM customer_accounts")
        
        await conn.close()
        
        return {
            "accounts": [
                {
                    "client_name": account["client_name"],
                    "total_orders_count": int(account["total_orders_count"]),
                    "total_amount_due": float(account["total_amount_due"]),
                    "outstanding_balance": float(account["outstanding_balance"])
                }
                for account in accounts
            ],
            "total_count": total_count,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving customer accounts: {str(e)}")

  
@router.get("/customer-accounts/by-name/{client_name}", dependencies=[Depends(admin_or_manager)])
async def get_customer_accounts_by_name(
    client_name: str,
    token: TokenData = Depends(admin_or_manager)
):
    """Get customer account(s) with details by client name - CASE-INSENSITIVE search"""
    conn = await connect_to_db()
    try:
        # URL decode the client name in case it contains special characters
        from urllib.parse import unquote
        decoded_name = unquote(client_name)
        
        # FIXED: Use case-insensitive search
        accounts = await conn.fetch("""
            SELECT * FROM customer_account_summary 
            WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
            ORDER BY id
        """, decoded_name)
        
        if not accounts:
            raise HTTPException(404, f"No customer accounts found with name '{decoded_name}' (case-insensitive search)")
        
        # If only one account, return single account format (backward compatibility)
        if len(accounts) == 1:
            account = accounts[0]
            customer_account_id = account['id']
            
            # Get related invoices
            invoices = await conn.fetch("""
                SELECT * FROM invoices WHERE customer_account_id = $1 ORDER BY invoice_date DESC
            """, customer_account_id)
            
            # Get related receipts
            receipts = await conn.fetch("""
                SELECT * FROM receipts WHERE customer_account_id = $1 ORDER BY payment_date DESC
            """, customer_account_id)
            
            await conn.close()
            return {
                "account": dict(account),
                "invoices": [dict(inv) for inv in invoices],
                "receipts": [dict(rec) for rec in receipts],
                "multiple_accounts": False
            }
        
        # Multiple accounts found - return all with their details
        result_accounts = []
        for account in accounts:
            customer_account_id = account['id']
            
            # Get related invoices for this account
            invoices = await conn.fetch("""
                SELECT * FROM invoices WHERE customer_account_id = $1 ORDER BY invoice_date DESC
            """, customer_account_id)
            
            # Get related receipts for this account
            receipts = await conn.fetch("""
                SELECT * FROM receipts WHERE customer_account_id = $1 ORDER BY payment_date DESC
            """, customer_account_id)
            
            result_accounts.append({
                "account": dict(account),
                "invoices": [dict(inv) for inv in invoices],
                "receipts": [dict(rec) for rec in receipts]
            })
        
        await conn.close()
        return {
            "accounts": result_accounts,
            "total_accounts": len(accounts),
            "client_name": decoded_name,
            "multiple_accounts": True
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving customer accounts: {str(e)}")

@router.get("/client-orders/by-name/{client_name}", dependencies=[Depends(admin_or_manager)])
async def get_client_orders_by_name(
    client_name: str,
    simple: bool = Query(False, description="Return simplified format with just id, product/model, total_price"),
    token: TokenData = Depends(admin_or_manager)
):
    """Get all orders for a client by name (case-insensitive, exact spelling match)"""
    conn = await connect_to_db()
    try:
        from urllib.parse import unquote
        decoded_name = unquote(client_name)
        
        if simple:
            # Simple format: just id, product/model, total_price
            orders = await conn.fetch("""
                SELECT 
                    id,
                    CASE 
                        WHEN model IS NOT NULL AND TRIM(model) != '' 
                        THEN CONCAT(product, ' / ', model)
                        ELSE product 
                    END as product_model,
                    COALESCE(total_price, 0) as total_price
                FROM job_orders 
                WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
                ORDER BY assigned_date DESC
            """, decoded_name)
            
            total_amount = sum(float(order["total_price"]) for order in orders)
            
            await conn.close()
            return {
                "client_name": decoded_name,
                "total_orders": len(orders),
                "total_amount": total_amount,
                "orders": [dict(order) for order in orders]
            }
        else:
            # Detailed format: existing functionality with enhanced customer info
            # Check if customer account exists
            similar_customers = await get_similar_customers_by_name(conn, decoded_name)
            if not similar_customers:
                # No customer account found, but still get orders from job_orders table
                orders = await conn.fetch("""
                    SELECT 
                        id,
                        order_id,
                        product,
                        model,
                        CASE 
                            WHEN model IS NOT NULL AND TRIM(model) != '' 
                            THEN CONCAT(product, ' / ', model)
                            ELSE product 
                        END as product_model,
                        COALESCE(total_price, 0) as total_price,
                        assigned_date,
                        status
                    FROM job_orders 
                    WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
                    ORDER BY assigned_date DESC
                """, decoded_name)
                
                await conn.close()
                return {
                    "client_name": decoded_name,
                    "has_customer_account": False,
                    "total_orders": len(orders),
                    "total_amount": sum(float(order["total_price"]) for order in orders),
                    "orders": [dict(order) for order in orders],
                    "message": "Orders found but no customer account exists. Consider creating a customer account for accounting purposes."
                }
            
            # Find exact match customer
            customer = None
            for cust in similar_customers:
                if cust["client_name"].lower().strip() == decoded_name.lower().strip():
                    customer = cust
                    break
            
            if not customer:
                customer = similar_customers[0]  # Use first similar customer if no exact match
            
            # Get enhanced customer information with contact details
            customer_info = await conn.fetchrow("""
                SELECT 
                    id,
                    client_name,
                    contact_email,
                    contact_phone,
                    shipping_address,
                    tax_id,
                    industry,
                    created_at,
                    updated_at
                FROM customer_accounts 
                WHERE id = $1
            """, customer["id"])
            
            # Get detailed order accounting information
            order_details = await conn.fetch("""
                SELECT 
                    oa.job_order_id as id,
                    jo.order_id,
                    jo.product,
                    jo.model,
                    CASE 
                        WHEN jo.model IS NOT NULL AND TRIM(jo.model) != '' 
                        THEN CONCAT(jo.product, ' / ', jo.model)
                        ELSE jo.product 
                    END as product_model,
                    oa.order_amount as total_price,
                    oa.amount_invoiced,
                    oa.amount_paid,
                    oa.outstanding_balance,
                    oa.payment_status,
                    oa.invoice_status,
                    oa.order_date,
                    oa.due_date,
                    COUNT(DISTINCT i.id) as invoice_count,
                    COUNT(DISTINCT r.id) as payment_count
                FROM order_accounting oa
                JOIN job_orders jo ON oa.job_order_id = jo.id
                LEFT JOIN invoices i ON oa.job_order_id = i.job_order_id
                LEFT JOIN receipts r ON oa.job_order_id = r.job_order_id
                WHERE oa.customer_account_id = $1
                GROUP BY oa.id, jo.order_id, jo.product, jo.model, oa.order_amount, 
                         oa.amount_invoiced, oa.amount_paid, oa.outstanding_balance,
                         oa.payment_status, oa.invoice_status, oa.order_date, oa.due_date
                ORDER BY oa.order_date DESC
            """, customer["id"])
            
            # Get all invoices for this customer
            invoices = await conn.fetch("""
                SELECT 
                    i.id as invoice_id,
                    i.invoice_date,
                    i.amount_paid,
                    i.due_date,
                    i.job_order_id,
                    jo.order_id,
                    CASE 
                        WHEN jo.model IS NOT NULL AND TRIM(jo.model) != '' 
                        THEN CONCAT(jo.product, ' / ', jo.model)
                        ELSE jo.product 
                    END as product_model
                FROM invoices i
                JOIN job_orders jo ON i.job_order_id = jo.id
                JOIN order_accounting oa ON oa.job_order_id = jo.id
                WHERE oa.customer_account_id = $1
                ORDER BY i.invoice_date DESC
            """, customer["id"])
            
            # Get all receipts for this customer
            receipts = await conn.fetch("""
                SELECT 
                    r.id as receipt_id,
                    r.receipt_number,
                    r.customer_account_id,
                    r.job_order_id,
                    r.invoice_id,
                    r.client_name,
                    r.amount_received,
                    r.payment_date,
                    r.payment_method,
                    r.transaction_reference,
                    r.bank_name,
                    r.check_number,
                    jo.order_id,
                    CASE 
                        WHEN jo.model IS NOT NULL AND TRIM(jo.model) != '' 
                        THEN CONCAT(jo.product, ' / ', jo.model)
                        ELSE jo.product 
                    END as product_model
                FROM receipts r
                LEFT JOIN job_orders jo ON r.job_order_id = jo.id
                WHERE r.customer_account_id = $1
                ORDER BY r.payment_date DESC
            """, customer["id"])
            
            await conn.close()
            return {
                "client_name": decoded_name,
                "has_customer_account": True,
                "customer": {
                    "id": customer_info["id"],
                    "client_name": customer_info["client_name"],
                    "contact_email": customer_info["contact_email"],
                    "contact_phone": customer_info["contact_phone"],
                    "shipping_address": customer_info["shipping_address"],
                    "tax_id": customer_info["tax_id"],
                    "industry": customer_info["industry"],
                    "created_at": customer_info["created_at"],
                    "updated_at": customer_info["updated_at"]
                },
                "orders": [dict(order) for order in order_details],
                "invoices": [dict(invoice) for invoice in invoices],
                "receipts": [dict(receipt) for receipt in receipts],
                "summary": {
                    "total_orders": len(order_details),
                    "total_invoices": len(invoices),
                    "total_receipts": len(receipts),
                    "total_amount": sum(float(o["total_price"]) for o in order_details),
                    "total_paid": sum(float(o["amount_paid"]) for o in order_details),
                    "outstanding_balance": sum(float(o["outstanding_balance"]) for o in order_details),
                    "total_invoice_amount": sum(float(i["amount_paid"]) for i in invoices if i["amount_paid"]),
                    "total_receipts_amount": sum(float(r["amount_received"]) for r in receipts if r["amount_received"])
                }
            }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving client orders: {str(e)}")


# Alternative: Simple dedicated endpoint for basic order listing
@router.get("/orders/by-client/{client_name}", dependencies=[Depends(admin_or_manager)])
async def get_orders_by_client_name(
    client_name: str,
    token: TokenData = Depends(admin_or_manager)
):
    """Get basic order information for a client (id, product/model, total_price)"""
    conn = await connect_to_db()
    try:
        from urllib.parse import unquote
        decoded_name = unquote(client_name)
        
        orders = await conn.fetch("""
            SELECT 
                id,
                CASE 
                    WHEN model IS NOT NULL AND TRIM(model) != '' 
                    THEN CONCAT(product, ' / ', model)
                    ELSE product 
                END as product_model,
                COALESCE(total_price, 0) as total_price
            FROM job_orders 
            WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
            AND status != 'cancelled'
            ORDER BY assigned_date DESC
        """, decoded_name)
        
        if not orders:
            raise HTTPException(404, f"No orders found for client '{decoded_name}'")
        
        total_amount = sum(float(order["total_price"]) for order in orders)
        
        await conn.close()
        return {
            "client_name": decoded_name,
            "total_orders": len(orders),
            "total_amount": total_amount,
            "orders": [dict(order) for order in orders]
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving orders: {str(e)}")

@router.post("/customer-accounts/auto-link-order", dependencies=[Depends(admin_or_manager)])
async def auto_link_new_order_to_customer(
    job_order_id: int,
    token: TokenData = Depends(admin_or_manager)
):
    """Auto-link a new job order to existing customer account - CASE-INSENSITIVE"""
    conn = await connect_to_db()
    try:
        # Get job order data
        job_order = await conn.fetchrow("""
            SELECT id, client_name, total_price, assigned_date
            FROM job_orders WHERE id = $1
        """, job_order_id)
        
        if not job_order:
            raise HTTPException(404, f"Job order {job_order_id} not found")
        
        # FIXED: Use case-insensitive search for customer account
        similar_customers = await get_similar_customers_by_name(conn, job_order["client_name"])
        
        customer = None
        if similar_customers:
            # Find exact match first (case-insensitive)
            for cust in similar_customers:
                if cust["client_name"].lower().strip() == job_order["client_name"].lower().strip():
                    customer = cust
                    break
            
            # If no exact match, use first similar customer
            if not customer:
                customer = similar_customers[0]
        
        if customer:
            # Link this order to existing customer account
            await conn.execute("""
                UPDATE job_orders 
                SET customer_account_id = $1 
                WHERE id = $2
            """, customer["id"], job_order_id)
            
            # Create order_accounting record
            await conn.execute("""
                INSERT INTO order_accounting (
                    customer_account_id, job_order_id, client_name,
                    order_amount, outstanding_balance, order_date
                )
                VALUES ($1, $2, $3, $4, $4, $5)
            """,
                customer["id"],
                job_order_id,
                job_order["client_name"],
                float(job_order["total_price"]) if job_order["total_price"] is not None else 0.0,
                job_order["assigned_date"]
            )
            
            # Update customer account totals
            await conn.execute("""
                UPDATE customer_accounts 
                SET total_orders_count = total_orders_count + 1,
                    total_amount_due = total_amount_due + $1,
                    outstanding_balance = outstanding_balance + $1,
                    last_order_date = $2
                WHERE id = $3
            """, float(job_order["total_price"]) if job_order["total_price"] is not None else 0.0, 
                job_order["assigned_date"], customer["id"])
            
            await conn.close()
            return {
                "message": "Order auto-linked to existing customer account (case-insensitive match)",
                "customer_id": customer["id"],
                "customer_name": customer["client_name"],
                "order_client_name": job_order["client_name"],
                "linked": True
            }
        else:
            await conn.close()
            return {
                "message": "No existing customer account found - order not linked",
                "client_name": job_order["client_name"],
                "linked": False,
                "suggestion": f"Create customer account for '{job_order['client_name']}' to enable accounting"
            }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error auto-linking order: {str(e)}")

@router.put("/customer-accounts/{customer_id}", dependencies=[Depends(admin_or_manager)])
async def update_customer_account(
    customer_id: int,
    account_update: CustomerAccountUpdate,
    token: TokenData = Depends(admin_or_manager)
):
    """Update customer account information"""
    conn = await connect_to_db()
    try:
        # Check if account exists
        existing = await conn.fetchval("SELECT id FROM customer_accounts WHERE id = $1", customer_id)
        if not existing:
            raise HTTPException(404, f"Customer account with ID {customer_id} not found")
        
        # Build update query dynamically
        update_fields = []
        values = []
        param_count = 1
        
        for field, value in account_update.dict(exclude_unset=True).items():
            if value is not None:
                update_fields.append(f"{field} = ${param_count}")
                # Convert custom_fields dict to JSON string for JSONB column
                if field == "custom_fields" and isinstance(value, dict):
                    values.append(json.dumps(value))
                else:
                    values.append(value)
                param_count += 1
        
        if update_fields:
            values.append(customer_id)
            query = f"""
                UPDATE customer_accounts 
                SET {', '.join(update_fields)}
                WHERE id = ${param_count}
            """
            await conn.execute(query, *values)
        
        await conn.close()
        return {"message": "Customer account updated successfully"}
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error updating customer account: {str(e)}")
    


@router.get("/customer-accounts/by-name/{client_name}", dependencies=[Depends(admin_or_manager)])
async def get_customer_accounts_by_name(
    client_name: str,
    token: TokenData = Depends(admin_or_manager)
):
    """Get customer account(s) with details by client name - returns all accounts if multiple exist"""
    conn = await connect_to_db()
    try:
        # URL decode the client name in case it contains special characters
        from urllib.parse import unquote
        decoded_name = unquote(client_name)
        
        # Get all accounts with this name
        accounts = await conn.fetch("""
            SELECT * FROM customer_account_summary WHERE LOWER(client_name) = LOWER($1)
            ORDER BY id
        """, decoded_name)
        
        if not accounts:
            raise HTTPException(404, f"No customer accounts found with name '{decoded_name}'")
        
        # If only one account, return single account format (backward compatibility)
        if len(accounts) == 1:
            account = accounts[0]
            customer_account_id = account['id']
            
            # Get related invoices
            invoices = await conn.fetch("""
                SELECT * FROM invoices WHERE customer_account_id = $1 ORDER BY invoice_date DESC
            """, customer_account_id)
            
            # Get related receipts
            receipts = await conn.fetch("""
                SELECT * FROM receipts WHERE customer_account_id = $1 ORDER BY payment_date DESC
            """, customer_account_id)
            
            await conn.close()
            return {
                "account": dict(account),
                "invoices": [dict(inv) for inv in invoices],
                "receipts": [dict(rec) for rec in receipts],
                "multiple_accounts": False
            }
        
        # Multiple accounts found - return all with their details
        result_accounts = []
        for account in accounts:
            customer_account_id = account['id']
            
            # Get related invoices for this account
            invoices = await conn.fetch("""
                SELECT * FROM invoices WHERE customer_account_id = $1 ORDER BY invoice_date DESC
            """, customer_account_id)
            
            # Get related receipts for this account
            receipts = await conn.fetch("""
                SELECT * FROM receipts WHERE customer_account_id = $1 ORDER BY payment_date DESC
            """, customer_account_id)
            
            result_accounts.append({
                "account": dict(account),
                "invoices": [dict(inv) for inv in invoices],
                "receipts": [dict(rec) for rec in receipts]
            })
        
        await conn.close()
        return {
            "accounts": result_accounts,
            "total_accounts": len(accounts),
            "client_name": decoded_name,
            "multiple_accounts": True
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving customer accounts: {str(e)}")


@router.put("/customer-accounts/by-name/{client_name}", dependencies=[Depends(admin_or_manager)])
async def update_customer_accounts_by_name(
    client_name: str,
    account_update: CustomerAccountUpdate,
    customer_id: int = Query(None, description="Specific customer ID to update (required if multiple accounts exist with same name)"),
    update_all: bool = Query(False, description="Update all accounts with this name (use with caution)"),
    token: TokenData = Depends(admin_or_manager)
):
    """Update customer account(s) by client name - CASE-INSENSITIVE search"""
    conn = await connect_to_db()
    try:
        # URL decode the client name in case it contains special characters
        from urllib.parse import unquote
        decoded_name = unquote(client_name)
        
        # FIXED: Use case-insensitive search
        customer_records = await conn.fetch("""
            SELECT id, client_name FROM customer_accounts 
            WHERE LOWER(TRIM(client_name)) = LOWER(TRIM($1))
            ORDER BY id
        """, decoded_name)
        
        if not customer_records:
            raise HTTPException(404, f"No customer accounts found with name '{decoded_name}' (case-insensitive search)")
        
        # If multiple accounts exist, require specific handling
        if len(customer_records) > 1:
            if not customer_id and not update_all:
                # Return list of available accounts to choose from
                await conn.close()
                accounts_info = [{"id": rec['id'], "name": rec['client_name']} for rec in customer_records]
                raise HTTPException(400, {
                    "error": f"Multiple accounts found with name '{decoded_name}' (case-insensitive)",
                    "message": "Please specify customer_id parameter or set update_all=true",
                    "available_accounts": accounts_info,
                    "total_count": len(customer_records)
                })
            
            if customer_id:
                # Verify the specified customer_id exists in the list
                customer_ids = [rec['id'] for rec in customer_records]
                if customer_id not in customer_ids:
                    raise HTTPException(400, f"Customer ID {customer_id} not found among accounts with name '{decoded_name}'. Available IDs: {customer_ids}")
                
                # Update only the specified customer
                target_customers = [customer_id]
            else:  # update_all is True
                # Update all customers with this name
                target_customers = [rec['id'] for rec in customer_records]
        else:
            # Only one account found
            target_customers = [customer_records[0]['id']]
        
        # Build update query dynamically
        update_fields = []
        values = []
        param_count = 1
        
        for field, value in account_update.dict(exclude_unset=True).items():
            if value is not None:
                update_fields.append(f"{field} = ${param_count}")
                # Convert custom_fields dict to JSON string for JSONB column
                if field == "custom_fields" and isinstance(value, dict):
                    values.append(json.dumps(value))
                else:
                    values.append(value)
                param_count += 1
        
        if not update_fields:
            await conn.close()
            return {"message": "No fields to update"}
        
        # Perform updates
        updated_accounts = []
        for target_id in target_customers:
            query_values = values + [target_id]
            query = f"""
                UPDATE customer_accounts 
                SET {', '.join(update_fields)}
                WHERE id = ${param_count}
            """
            await conn.execute(query, *query_values)
            updated_accounts.append(target_id)
        
        await conn.close()
        
        return {
            "message": f"Successfully updated {len(updated_accounts)} customer account(s) with name '{decoded_name}' (case-insensitive)",
            "updated_customer_ids": updated_accounts,
            "total_updated": len(updated_accounts)
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error updating customer accounts: {str(e)}")
    

@router.get("/customer-accounts/by-name/{client_name}/orders", dependencies=[Depends(admin_or_manager)])
async def get_client_order_summary(
    client_name: str,
    token: TokenData = Depends(admin_or_manager)
):
    """Get detailed order summary for a client including accounting status - CASE-INSENSITIVE"""
    conn = await connect_to_db()
    try:
        from urllib.parse import unquote
        decoded_name = unquote(client_name)
        
        # Get customer account using case-insensitive search
        similar_customers = await get_similar_customers_by_name(conn, decoded_name)
        if not similar_customers:
            raise HTTPException(404, f"No customer account found for '{decoded_name}' (case-insensitive search)")
        
        # Get the first exact match or the first similar customer
        customer = None
        for cust in similar_customers:
            if cust["client_name"].lower().strip() == decoded_name.lower().strip():
                customer = cust
                break
        
        if not customer:
            customer = similar_customers[0]  # Use first similar customer if no exact match
        
        # Get detailed order accounting information
        order_details = await conn.fetch("""
            SELECT 
                oa.job_order_id,
                jo.order_id,
                jo.product,
                jo.model,
                oa.order_amount,
                oa.amount_invoiced,
                oa.amount_paid,
                oa.outstanding_balance,
                oa.payment_status,
                oa.invoice_status,
                oa.order_date,
                oa.due_date,
                COUNT(DISTINCT i.id) as invoice_count,
                COUNT(DISTINCT r.id) as payment_count
            FROM order_accounting oa
            JOIN job_orders jo ON oa.job_order_id = jo.id
            LEFT JOIN invoices i ON oa.job_order_id = i.job_order_id
            LEFT JOIN receipts r ON oa.job_order_id = r.job_order_id
            WHERE oa.customer_account_id = $1
            GROUP BY oa.id, jo.order_id, jo.product, jo.model
            ORDER BY oa.order_date DESC
        """, customer["id"])
        
        await conn.close()
        return {
            "customer": customer,
            "orders": [dict(order) for order in order_details],
            "summary": {
                "total_orders": len(order_details),
                "total_amount": sum(float(o["order_amount"]) for o in order_details),
                "total_paid": sum(float(o["amount_paid"]) for o in order_details),
                "outstanding_balance": sum(float(o["outstanding_balance"]) for o in order_details)
            }
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving client order summary: {str(e)}")



# -------------------------------------------------------
# Invoices Endpoints
# -------------------------------------------------------
@router.post("/invoices", dependencies=[Depends(admin_or_manager)])
async def create_invoice(
    invoice_data: InvoiceCreate,
    token: TokenData = Depends(admin_or_manager)
):
    """Create invoice from job order"""
    conn = await connect_to_db()
    try:
        # Verify customer account exists
        customer_exists = await conn.fetchval("""
            SELECT id FROM customer_accounts WHERE id = $1
        """, invoice_data.customer_account_id)
        
        if not customer_exists:
            raise HTTPException(404, f"Customer account with ID {invoice_data.customer_account_id} not found")
        
        # Create invoice using stored function
        invoice_id = await conn.fetchval("""
            SELECT create_invoice_from_job_order($1, $2, $3, $4, $5, $6)
        """,
            invoice_data.customer_account_id,
            invoice_data.job_order_id,
            invoice_data.po_reference,
            invoice_data.tax_percentage,
            invoice_data.due_days,
            json.dumps(invoice_data.custom_fields) if invoice_data.custom_fields else None
        )
        
        # Add notes if provided
        if invoice_data.notes:
            await conn.execute("""
                UPDATE invoices SET notes = $1 WHERE id = $2
            """, invoice_data.notes, invoice_id)
        
        # Get created invoice details
        invoice_details = await conn.fetchrow("""
            SELECT i.*, ca.client_name 
            FROM invoices i
            JOIN customer_accounts ca ON i.customer_account_id = ca.id
            WHERE i.id = $1
        """, invoice_id)
        
        await conn.close()
        return {
            "message": "Invoice created successfully",
            "invoice_id": invoice_id,
            "invoice_number": invoice_details["invoice_number"],
            "client_name": invoice_details["client_name"],
            "total_amount": invoice_details["total_amount"],
            "due_date": invoice_details["due_date"]
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error creating invoice: {str(e)}")

@router.get("/invoices", dependencies=[Depends(admin_or_manager)])
async def get_all_invoices(
    token: TokenData = Depends(admin_or_manager),
    status: Optional[PaymentStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get all invoices with optional status filter"""
    conn = await connect_to_db()
    try:
        if status:
            # Query with status filter
            invoices = await conn.fetch("""
                SELECT i.*, ca.client_name 
                FROM invoices i
                JOIN customer_accounts ca ON i.customer_account_id = ca.id
                WHERE i.payment_status = $1
                ORDER BY i.invoice_date DESC
                LIMIT $2 OFFSET $3
            """, status.value, limit, skip)
            
            total_count = await conn.fetchval("""
                SELECT COUNT(*) FROM invoices i WHERE i.payment_status = $1
            """, status.value)
        else:
            # Query without status filter
            invoices = await conn.fetch("""
                SELECT i.*, ca.client_name 
                FROM invoices i
                JOIN customer_accounts ca ON i.customer_account_id = ca.id
                ORDER BY i.invoice_date DESC
                LIMIT $1 OFFSET $2
            """, limit, skip)
            
            total_count = await conn.fetchval("""
                SELECT COUNT(*) FROM invoices
            """)
        
        await conn.close()
        return {
            "invoices": [dict(invoice) for invoice in invoices],
            "total_count": total_count,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving invoices: {str(e)}")

@router.get("/invoices/outstanding", dependencies=[Depends(admin_or_manager)])
async def get_outstanding_invoices(token: TokenData = Depends(admin_or_manager)):
    """Get all outstanding invoices"""
    conn = await connect_to_db()
    try:
        invoices = await conn.fetch("""
            SELECT * FROM outstanding_invoices ORDER BY days_overdue DESC
        """)
        
        await conn.close()
        return [dict(invoice) for invoice in invoices]
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving outstanding invoices: {str(e)}")

@router.get("/invoices/{invoice_id}", dependencies=[Depends(admin_or_manager)])
async def get_invoice(
    invoice_id: int,
    token: TokenData = Depends(admin_or_manager)
):
    """Get specific invoice with details"""
    conn = await connect_to_db()
    try:
        invoice = await conn.fetchrow("""
            SELECT i.*, ca.client_name, ca.contact_email, ca.shipping_address
            FROM invoices i
            JOIN customer_accounts ca ON i.customer_account_id = ca.id
            WHERE i.id = $1
        """, invoice_id)
        
        if not invoice:
            raise HTTPException(404, f"Invoice with ID {invoice_id} not found")
        
        # Get related receipts
        receipts = await conn.fetch("""
            SELECT * FROM receipts 
            WHERE invoice_id = $1 
            ORDER BY payment_date DESC
        """, invoice_id)
        
        await conn.close()
        return {
            "invoice": dict(invoice),
            "receipts": [dict(receipt) for receipt in receipts]
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving invoice: {str(e)}")

# -------------------------------------------------------
# Receipts Endpoints
# -------------------------------------------------------
@router.post("/receipts", dependencies=[Depends(admin_or_manager)])
async def create_receipt(
    receipt_data: ReceiptCreate,
    token: TokenData = Depends(admin_or_manager)
):
    """Create payment receipt"""
    conn = await connect_to_db()
    try:
        # Verify customer account exists
        customer_exists = await conn.fetchval("""
            SELECT id FROM customer_accounts WHERE id = $1
        """, receipt_data.customer_account_id)
        
        if not customer_exists:
            raise HTTPException(404, f"Customer account with ID {receipt_data.customer_account_id} not found")
        
        # If invoice_id is provided, verify it exists and belongs to the customer
        if receipt_data.invoice_id:
            invoice_exists = await conn.fetchval("""
                SELECT id FROM invoices 
                WHERE id = $1 AND customer_account_id = $2
            """, receipt_data.invoice_id, receipt_data.customer_account_id)
            
            if not invoice_exists:
                raise HTTPException(404, f"Invoice with ID {receipt_data.invoice_id} not found for this customer")
        
        # Create receipt using stored function
        receipt_id = await conn.fetchval("""
            SELECT record_receipt($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
            receipt_data.customer_account_id,
            receipt_data.job_order_id,
            receipt_data.amount_received,
            receipt_data.payment_method.value,
            receipt_data.bank_or_cash.value,
            receipt_data.invoice_id,
            receipt_data.transaction_reference,
            receipt_data.bank_name,
            receipt_data.check_number,
            receipt_data.notes,
            json.dumps(receipt_data.custom_fields) if receipt_data.custom_fields else None
        )
        
        # Get created receipt details
        receipt_details = await conn.fetchrow("""
            SELECT r.*, ca.client_name 
            FROM receipts r
            JOIN customer_accounts ca ON r.customer_account_id = ca.id
            WHERE r.id = $1
        """, receipt_id)
        
        await conn.close()
        return {
            "message": "Receipt created successfully",
            "receipt_id": receipt_id,
            "receipt_number": receipt_details["receipt_number"],
            "client_name": receipt_details["client_name"],
            "amount_received": receipt_details["amount_received"],
            "payment_date": receipt_details["payment_date"]
        }
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error creating receipt: {str(e)}")

@router.get("/receipts", dependencies=[Depends(admin_or_manager)])
async def get_all_receipts(
    token: TokenData = Depends(admin_or_manager),
    customer_account_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get all receipts with optional client filter"""
    conn = await connect_to_db()
    try:
        if customer_account_id:
            # Query with client filter
            receipts = await conn.fetch("""
                SELECT r.*, ca.client_name 
                FROM receipts r
                JOIN customer_accounts ca ON r.customer_account_id = ca.id
                WHERE r.customer_account_id = $1
                ORDER BY r.payment_date DESC
                LIMIT $2 OFFSET $3
            """, customer_account_id, limit, skip)
            
            total_count = await conn.fetchval("""
                SELECT COUNT(*) FROM receipts r WHERE r.customer_account_id = $1
            """, customer_account_id)
        else:
            # Query without client filter
            receipts = await conn.fetch("""
                SELECT r.*, ca.client_name 
                FROM receipts r
                JOIN customer_accounts ca ON r.customer_account_id = ca.id
                ORDER BY r.payment_date DESC
                LIMIT $1 OFFSET $2
            """, limit, skip)
            
            total_count = await conn.fetchval("""
                SELECT COUNT(*) FROM receipts
            """)
        
        await conn.close()
        return {
            "receipts": [dict(receipt) for receipt in receipts],
            "total_count": total_count,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving receipts: {str(e)}")

@router.get("/receipts/{receipt_id}", dependencies=[Depends(admin_or_manager)])
async def get_receipt(
    receipt_id: int,
    token: TokenData = Depends(admin_or_manager)
):
    """Get specific receipt with details"""
    conn = await connect_to_db()
    try:
        receipt = await conn.fetchrow("""
            SELECT r.*, ca.client_name, ca.contact_email
            FROM receipts r
            JOIN customer_accounts ca ON r.customer_account_id = ca.id
            WHERE r.id = $1
        """, receipt_id)
        
        if not receipt:
            raise HTTPException(404, f"Receipt with ID {receipt_id} not found")
        
        await conn.close()
        return dict(receipt)
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving receipt: {str(e)}")

# -------------------------------------------------------
# Analytics and Reports Endpoints
# -------------------------------------------------------
@router.get("/analytics/summary", dependencies=[Depends(admin_or_manager)])
async def get_accounting_summary(token: TokenData = Depends(admin_or_manager)):
    """Get accounting summary analytics"""
    conn = await connect_to_db()
    try:
        # Total outstanding balance
        total_outstanding = await conn.fetchval("""
            SELECT COALESCE(SUM(outstanding_balance), 0) FROM customer_accounts
        """)
        
        # Total paid this month
        total_paid_month = await conn.fetchval("""
            SELECT COALESCE(SUM(amount_received), 0) 
            FROM receipts 
            WHERE EXTRACT(MONTH FROM payment_date) = EXTRACT(MONTH FROM CURRENT_DATE)
            AND EXTRACT(YEAR FROM payment_date) = EXTRACT(YEAR FROM CURRENT_DATE)
        """)
        
        # Outstanding invoices count
        outstanding_invoices_count = await conn.fetchval("""
            SELECT COUNT(*) FROM invoices 
            WHERE payment_status IN ('unpaid', 'partial', 'overdue')
        """)
        
        # Overdue invoices count
        overdue_invoices_count = await conn.fetchval("""
            SELECT COUNT(*) FROM invoices 
            WHERE payment_status = 'overdue' OR 
                  (payment_status IN ('unpaid', 'partial') AND due_date < CURRENT_DATE)
        """)
        
        # Top customers by outstanding balance
        top_customers = await conn.fetch("""
            SELECT client_name, outstanding_balance 
            FROM customer_accounts 
            WHERE outstanding_balance > 0
            ORDER BY outstanding_balance DESC 
            LIMIT 5
        """)
        
        await conn.close()
        return {
            "total_outstanding": float(total_outstanding),
            "total_paid_this_month": float(total_paid_month),
            "outstanding_invoices_count": outstanding_invoices_count,
            "overdue_invoices_count": overdue_invoices_count,
            "top_customers_by_outstanding": [dict(customer) for customer in top_customers]
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving accounting summary: {str(e)}")

@router.get("/analytics/aging-report", dependencies=[Depends(admin_or_manager)])
async def get_aging_report(token: TokenData = Depends(admin_or_manager)):
    """Get accounts receivable aging report"""
    conn = await connect_to_db()
    try:
        aging_report = await conn.fetch("""
            SELECT 
                ca.client_name,
                ca.outstanding_balance,
                i.invoice_number,
                i.invoice_date,
                i.due_date,
                i.total_amount,
                CASE 
                    WHEN i.due_date >= CURRENT_DATE THEN 'Current'
                    WHEN CURRENT_DATE - i.due_date <= 30 THEN '1-30 Days'
                    WHEN CURRENT_DATE - i.due_date <= 60 THEN '31-60 Days'
                    WHEN CURRENT_DATE - i.due_date <= 90 THEN '61-90 Days'
                    ELSE '90+ Days'
                END as aging_bucket
            FROM invoices i
            JOIN customer_accounts ca ON i.customer_account_id = ca.id
            WHERE i.payment_status IN ('unpaid', 'partial', 'overdue')
            ORDER BY ca.client_name, i.due_date
        """)
        
        await conn.close()
        return [dict(record) for record in aging_report]
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error generating aging report: {str(e)}")

# -------------------------------------------------------
# Custom Fields Management
# -------------------------------------------------------
@router.post("/custom-fields", dependencies=[Depends(admin_or_manager)])
async def create_custom_field(
    field_def: CustomFieldDefinition,
    token: TokenData = Depends(admin_or_manager)
):
    """Create custom field definition"""
    conn = await connect_to_db()
    try:
        field_id = await conn.fetchval("""
            INSERT INTO custom_field_definitions (
                table_name, field_name, field_type, field_label,
                field_options, is_required, default_value, validation_rules, display_order
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """,
            field_def.table_name,
            field_def.field_name,
            field_def.field_type,
            field_def.field_label,
            json.dumps(field_def.field_options) if field_def.field_options else None,
            field_def.is_required,
            field_def.default_value,
            json.dumps(field_def.validation_rules) if field_def.validation_rules else None,
            field_def.display_order
        )
        
        await conn.close()
        return {
            "message": "Custom field created successfully",
            "field_id": field_id
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error creating custom field: {str(e)}")

@router.get("/custom-fields/{table_name}", dependencies=[Depends(admin_or_manager)])
async def get_custom_fields(
    table_name: str,
    token: TokenData = Depends(admin_or_manager)
):
    """Get custom field definitions for a table"""
    conn = await connect_to_db()
    try:
        fields = await conn.fetch("""
            SELECT * FROM custom_field_definitions 
            WHERE table_name = $1 AND is_active = true
            ORDER BY display_order, field_label
        """, table_name)
        
        await conn.close()
        return [dict(field) for field in fields]
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving custom fields: {str(e)}")

# -------------------------------------------------------
# Quick Actions
# -------------------------------------------------------
# @router.post("/quick-actions/create-full-workflow", dependencies=[Depends(admin_or_manager)])
# async def create_full_accounting_workflow(
#     job_order_id: int,
#     customer_data: CustomerAccountCreate,
#     invoice_data: Optional[InvoiceCreate] = None,
#     token: TokenData = Depends(admin_or_manager)
# ):
#     """Create customer account and optionally invoice in one action"""
#     conn = await connect_to_db()
#     try:
#         # Ensure job_order_id matches
#         if customer_data.job_order_id != job_order_id:
#             raise HTTPException(400, "Job order ID mismatch")
        
#         # Check if customer account already exists
#         existing_account = await check_customer_account_exists(conn, job_order_id)
#         if existing_account:
#             raise HTTPException(400, f"Customer account already exists for job order {job_order_id}")
        
#         # Create customer account
#         customer_id = await conn.fetchval("""
#             SELECT create_customer_account_from_job_order($1, $2, $3, $4, $5, $6, $7, $8)
#         """,
#             customer_data.job_order_id,
#             customer_data.contact_email,
#             customer_data.contact_phone,
#             customer_data.contact_person_name,
#             customer_data.shipping_address,
#             customer_data.currency,
#             customer_data.payment_terms,
#             json.dumps(customer_data.custom_fields) if customer_data.custom_fields else None
#         )
        
        
#         result = {
#             "message": "Customer account created successfully",
#             "customer_id": customer_id,
#             "job_order_id": job_order_id
#         }
        
#         # Create invoice if requested
#         invoice_id = None
#         if invoice_data:
#             # Update invoice data with created customer_id
#             invoice_data.customer_account_id = customer_id
#             invoice_data.job_order_id = job_order_id
            
#             invoice_id = await conn.fetchval("""
#                 SELECT create_invoice_from_job_order($1, $2, $3, $4, $5, $6)
#             """,
#                 invoice_data.customer_account_id,
#                 invoice_data.job_order_id,
#                 invoice_data.po_reference,
#                 invoice_data.tax_percentage,
#                 invoice_data.due_days,
#                 json.dumps(invoice_data.custom_fields) if invoice_data.custom_fields else None
#             )
            
#             # Add notes if provided
#             if invoice_data.notes:
#                 await conn.execute("""
#                     UPDATE invoices SET notes = $1 WHERE id = $2
#                 """, invoice_data.notes, invoice_id)
            
#             # Get invoice details
#             invoice_details = await conn.fetchrow("""
#                 SELECT invoice_number, total_amount, due_date 
#                 FROM invoices WHERE id = $1
#             """, invoice_id)
            
#             result["invoice_created"] = True
#             result["invoice_id"] = invoice_id
#             result["invoice_number"] = invoice_details["invoice_number"]
#             result["invoice_total"] = invoice_details["total_amount"]
#             result["invoice_due_date"] = invoice_details["due_date"]
        
#         await conn.close()
#         return result
        
#     except HTTPException as e:
#         await conn.close()
#         raise e
#     except Exception as e:
#         await conn.close()
#         raise HTTPException(400, f"Error creating accounting workflow: {str(e)}")

@router.get("/job-orders/{job_order_id}/accounting-status", dependencies=[Depends(admin_or_manager)])
async def get_job_order_accounting_status(
    job_order_id: int,
    token: TokenData = Depends(admin_or_manager)
):
    """Get accounting status for a specific job order"""
    conn = await connect_to_db()
    try:
        # Get job order data
        job_order = await get_job_order_data(conn, job_order_id)
        
        # Check if customer account exists
        customer_account = await conn.fetchrow("""
            SELECT id, client_name, total_amount, amount_received, outstanding_balance
            FROM customer_accounts WHERE job_order_id = $1
        """, job_order_id)
        
        result = {
            "job_order": job_order,
            "has_customer_account": customer_account is not None,
            "customer_account": dict(customer_account) if customer_account else None,
            "invoices": [],
            "receipts": [],
            "total_invoiced": 0,
            "total_received": 0,
            "outstanding_balance": 0
        }
        
        if customer_account:
            # Get invoices
            invoices = await conn.fetch("""
                SELECT * FROM invoices WHERE customer_account_id = $1 ORDER BY invoice_date DESC
            """, customer_account["id"])
            
            # Get receipts
            receipts = await conn.fetch("""
                SELECT * FROM receipts WHERE customer_account_id = $1 ORDER BY payment_date DESC
            """, customer_account["id"])
            
            result["invoices"] = [dict(inv) for inv in invoices]
            result["receipts"] = [dict(rec) for rec in receipts]
            result["total_invoiced"] = sum(float(inv["total_amount"]) for inv in invoices)
            result["total_received"] = float(customer_account["amount_received"])
            result["outstanding_balance"] = float(customer_account["outstanding_balance"])
        
        await conn.close()
        return result
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving accounting status: {str(e)}")

@router.get("/job-orders/without-accounts", dependencies=[Depends(admin_or_manager)])
async def get_job_orders_without_accounts(
    token: TokenData = Depends(admin_or_manager),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200)
):
    """Get job orders that don't have customer accounts yet"""
    conn = await connect_to_db()
    try:
        job_orders = await conn.fetch("""
            SELECT jo.id, jo.order_id, jo.client_name, jo.product, jo.model, 
                   jo.total_price, jo.assigned_date, jo.status
            FROM job_orders jo
            LEFT JOIN customer_accounts ca ON jo.id = ca.job_order_id
            WHERE ca.id IS NULL
            AND jo.status != 'cancelled'
            ORDER BY jo.assigned_date DESC
            LIMIT $1 OFFSET $2
        """, limit, skip)
        
        total_count = await conn.fetchval("""
            SELECT COUNT(*)
            FROM job_orders jo
            LEFT JOIN customer_accounts ca ON jo.id = ca.job_order_id
            WHERE ca.id IS NULL AND jo.status != 'cancelled'
        """)
        
        await conn.close()
        return {
            "job_orders": [dict(jo) for jo in job_orders],
            "total_count": total_count,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving job orders: {str(e)}")

# -------------------------------------------------------
# Payment Tracking and Reconciliation
# -------------------------------------------------------
@router.post("/reconciliation/match-payment", dependencies=[Depends(admin_or_manager)])
async def match_payment_to_invoice(
    receipt_id: int,
    invoice_id: int,
    token: TokenData = Depends(admin_or_manager)
):
    """Match a payment receipt to a specific invoice"""
    conn = await connect_to_db()
    try:
        # Verify receipt and invoice exist and belong to same customer
        match_check = await conn.fetchrow("""
            SELECT r.customer_account_id as receipt_client, i.customer_account_id as invoice_client,
                   r.amount_received, i.total_amount
            FROM receipts r, invoices i
            WHERE r.id = $1 AND i.id = $2
        """, receipt_id, invoice_id)
        
        if not match_check:
            raise HTTPException(404, "Receipt or invoice not found")
        
        if match_check["receipt_client"] != match_check["invoice_client"]:
            raise HTTPException(400, "Receipt and invoice belong to different customers")
        
        # Update receipt to link to invoice
        await conn.execute("""
            UPDATE receipts SET invoice_id = $1 WHERE id = $2
        """, invoice_id, receipt_id)
        
        await conn.close()
        return {"message": "Payment matched to invoice successfully"}
        
    except HTTPException as e:
        await conn.close()
        raise e
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error matching payment: {str(e)}")

@router.get("/reconciliation/unmatched-payments", dependencies=[Depends(admin_or_manager)])
async def get_unmatched_payments(token: TokenData = Depends(admin_or_manager)):
    """Get payments that are not matched to specific invoices"""
    conn = await connect_to_db()
    try:
        unmatched = await conn.fetch("""
            SELECT r.*, ca.client_name
            FROM receipts r
            JOIN customer_accounts ca ON r.customer_account_id = ca.id
            WHERE r.invoice_id IS NULL
            ORDER BY r.payment_date DESC
        """)
        
        await conn.close()
        return [dict(receipt) for receipt in unmatched]
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error retrieving unmatched payments: {str(e)}")

# -------------------------------------------------------
# Bulk Operations
# -------------------------------------------------------
# @router.post("/bulk/create-accounts-from-job-orders", dependencies=[Depends(admin_or_manager)])
# async def bulk_create_accounts_from_job_orders(
#     job_order_ids: List[int],
#     default_currency: str = "USD",
#     default_payment_terms: str = "Net 30",
#     token: TokenData = Depends(admin_or_manager)
# ):
#     """Bulk create customer accounts from multiple job orders"""
#     conn = await connect_to_db()
#     try:
#         created_accounts = []
#         errors = []
        
#         for job_order_id in job_order_ids:
#             try:
#                 # Check if account already exists
#                 existing = await check_customer_account_exists(conn, job_order_id)
#                 if existing:
#                     errors.append(f"Job order {job_order_id}: Account already exists")
#                     continue
                
#                 # Create account with default values
#                 customer_id = await conn.fetchval("""
#                     SELECT create_customer_account_from_job_order($1, $2, $3, $4, $5, $6, $7, $8)
#                 """,
#                     job_order_id, None, None, None, None, 
#                     default_currency, default_payment_terms, None
#                 )
                
#                 created_accounts.append({
#                     "job_order_id": job_order_id,
#                     "customer_id": customer_id
#                 })
                
#             except Exception as e:
#                 errors.append(f"Job order {job_order_id}: {str(e)}")
        
#         await conn.close()
#         return {
#             "message": f"Bulk operation completed. Created {len(created_accounts)} accounts.",
#             "created_accounts": created_accounts,
#             "errors": errors
#         }
        
#     except Exception as e:
#         await conn.close()
#         raise HTTPException(400, f"Error in bulk operation: {str(e)}")

@router.post("/bulk/send-overdue-notices", dependencies=[Depends(admin_or_manager)])
async def mark_overdue_invoices(token: TokenData = Depends(admin_or_manager)):
    """Mark invoices as overdue and get list for notice sending"""
    conn = await connect_to_db()
    try:
        # Update overdue invoices
        updated_count = await conn.fetchval("""
            UPDATE invoices 
            SET payment_status = 'overdue'
            WHERE payment_status IN ('unpaid', 'partial') 
            AND due_date < CURRENT_DATE
            RETURNING COUNT(*)
        """)
        
        # Get overdue invoices with customer details
        overdue_invoices = await conn.fetch("""
            SELECT i.*, ca.client_name, ca.contact_email, ca.contact_phone
            FROM invoices i
            JOIN customer_accounts ca ON i.customer_account_id = ca.id
            WHERE i.payment_status = 'overdue'
            ORDER BY i.due_date ASC
        """)
        
        await conn.close()
        return {
            "message": f"Marked {updated_count} invoices as overdue",
            "overdue_invoices": [dict(inv) for inv in overdue_invoices]
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error processing overdue invoices: {str(e)}")

# -------------------------------------------------------
# Export and Reporting
# -------------------------------------------------------
@router.get("/export/customer-statements", dependencies=[Depends(admin_or_manager)])
async def export_customer_statements(
    customer_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    token: TokenData = Depends(admin_or_manager)
):
    """Export customer statements for specified period"""
    conn = await connect_to_db()
    try:
        where_conditions = []
        params = []
        param_count = 1
        
        if customer_id:
            where_conditions.append(f"ca.id = ${param_count}")
            params.append(customer_id)
            param_count += 1
        
        if date_from:
            where_conditions.append(f"i.invoice_date >= ${param_count}")
            params.append(date_from)
            param_count += 1
        
        if date_to:
            where_conditions.append(f"i.invoice_date <= ${param_count}")
            params.append(date_to)
            param_count += 1
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        statements = await conn.fetch(f"""
            SELECT 
                ca.id as customer_id,
                ca.client_name,
                ca.contact_email,
                ca.total_amount,
                ca.amount_received,
                ca.outstanding_balance,
                i.invoice_number,
                i.invoice_date,
                i.total_amount as invoice_amount,
                i.payment_status,
                i.due_date
            FROM customer_accounts ca
            LEFT JOIN invoices i ON ca.id = i.customer_account_id
            {where_clause}
            ORDER BY ca.client_name, i.invoice_date DESC
        """, *params)
        
        await conn.close()
        return [dict(statement) for statement in statements]
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error exporting customer statements: {str(e)}")

@router.get("/reports/cash-flow", dependencies=[Depends(admin_or_manager)])
async def get_cash_flow_report(
    months_back: int = Query(12, ge=1, le=24),
    token: TokenData = Depends(admin_or_manager)
):
    """Get cash flow report for specified number of months"""
    conn = await connect_to_db()
    try:
        cash_flow = await conn.fetch("""
            SELECT 
                TO_CHAR(payment_date, 'YYYY-MM') as month,
                SUM(amount_received) as total_received,
                COUNT(*) as transaction_count
            FROM receipts
            WHERE payment_date >= CURRENT_DATE - INTERVAL '%s months'
            GROUP BY TO_CHAR(payment_date, 'YYYY-MM')
            ORDER BY month DESC
        """ % months_back)
        
        # Get monthly invoiced amounts
        invoiced = await conn.fetch("""
            SELECT 
                TO_CHAR(invoice_date, 'YYYY-MM') as month,
                SUM(total_amount) as total_invoiced,
                COUNT(*) as invoice_count
            FROM invoices
            WHERE invoice_date >= CURRENT_DATE - INTERVAL '%s months'
            GROUP BY TO_CHAR(invoice_date, 'YYYY-MM')
            ORDER BY month DESC
        """ % months_back)
        
        await conn.close()
        return {
            "cash_received": [dict(cf) for cf in cash_flow],
            "invoiced_amounts": [dict(inv) for inv in invoiced]
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error generating cash flow report: {str(e)}")

# -------------------------------------------------------
# Health Check and Validation
# -------------------------------------------------------
@router.get("/health-check", dependencies=[Depends(admin_or_manager)])
async def accounting_health_check(token: TokenData = Depends(admin_or_manager)):
    """Check accounting system health and data consistency"""
    conn = await connect_to_db()
    try:
        checks = {}
        
        # Check for orphaned records
        orphaned_invoices = await conn.fetchval("""
            SELECT COUNT(*) FROM invoices i
            LEFT JOIN customer_accounts ca ON i.customer_account_id = ca.id
            WHERE ca.id IS NULL
        """)
        checks["orphaned_invoices"] = orphaned_invoices
        
        orphaned_receipts = await conn.fetchval("""
            SELECT COUNT(*) FROM receipts r
            LEFT JOIN customer_accounts ca ON r.customer_account_id = ca.id
            WHERE ca.id IS NULL
        """)
        checks["orphaned_receipts"] = orphaned_receipts
        
        # Check balance calculations
        balance_mismatches = await conn.fetchval("""
            SELECT COUNT(*) FROM customer_accounts ca
            WHERE ABS(ca.outstanding_balance - (ca.total_amount - ca.amount_received)) > 0.01
        """)
        checks["balance_calculation_errors"] = balance_mismatches
        
        # Check for invoices without job orders
        invoices_without_job_orders = await conn.fetchval("""
            SELECT COUNT(*) FROM invoices i
            LEFT JOIN job_orders jo ON i.job_order_id = jo.id
            WHERE jo.id IS NULL
        """)
        checks["invoices_without_job_orders"] = invoices_without_job_orders
        
        await conn.close()
        return {
            "status": "healthy" if all(count == 0 for count in checks.values()) else "issues_found",
            "checks": checks
        }
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error running health check: {str(e)}")

# -------------------------------------------------------
# Search and Filter Functions
# -------------------------------------------------------
@router.get("/search/customers", dependencies=[Depends(admin_or_manager)])
async def search_customers(
    query: str = Query(..., min_length=2),
    token: TokenData = Depends(admin_or_manager)
):
    """Search customers by name, email, or phone"""
    conn = await connect_to_db()
    try:
        search_pattern = f"%{query.lower()}%"
        
        customers = await conn.fetch("""
            SELECT id, client_name, contact_email, contact_phone, outstanding_balance
            FROM customer_accounts
            WHERE LOWER(client_name) LIKE $1 
               OR LOWER(contact_email) LIKE $1 
               OR LOWER(contact_phone) LIKE $1
               OR LOWER(contact_person_name) LIKE $1
            ORDER BY client_name
            LIMIT 20
        """, search_pattern)
        
        await conn.close()
        return [dict(customer) for customer in customers]
        
    except Exception as e:
        await conn.close()
        raise HTTPException(400, f"Error searching customers: {str(e)}")