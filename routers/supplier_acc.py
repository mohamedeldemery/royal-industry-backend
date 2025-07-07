from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from decimal import Decimal
import asyncpg
import json
from routers.employees import admin_or_manager, TokenData


# Remove the duplicate router definition and keep only this one
router = APIRouter(
    prefix="/api/supplier-acc", 
    tags=["Supplier Accounting"],  # Changed from "Supplier Accounts" to "Supplier Accounting"
    responses={404: {"description": "Not found"}}
)

# Database connection
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)

# ============================================
# PYDANTIC MODELS
# ============================================

class SupplierAccountFromInventory(BaseModel):
    group_id: int
    # Optional fields that user can override or add
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_name: Optional[str] = None
    currency: str = "USD"
    payment_terms: Optional[str] = None
    additional_fields: Optional[Dict[str, Any]] = {}

class PurchaseOrderFromInventory(BaseModel):
    group_id: int
    # Optional fields that user can override or add
    po_number: Optional[str] = None  # Will auto-generate if not provided
    vat_percentage: float = 0.0
    additional_fields: Optional[Dict[str, Any]] = {}

class RawInvoiceFromInventory(BaseModel):
    group_id: int
    # Optional fields that user can override or add
    invoice_number: Optional[str] = None  # Will auto-generate if not provided
    status: str = "unpaid"
    due_date: Optional[date] = None
    additional_fields: Optional[Dict[str, Any]] = {}

class SupplierAccountCreate(BaseModel):
    group_id: Optional[int] = None  # Optional - only used for inventory order creation
    supplier_name: str
    supplier_code: str
    contact_email: str
    contact_phone: str
    contact_name: str
    currency: str = "USD"
    payment_terms: str
    additional_fields: Dict[str, Any] = {}

class InventoryOrderItem(BaseModel):
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




class PurchaseOrderCreate(BaseModel):
    group_id: Optional[int] = None  # Make optional if needed
    supplier_id: int
    supplier_name: str
    po_number: Optional[str] = None  # Make optional - will auto-generate if not provided
    material_type: Optional[str] = None
    delivery_date: Optional[date] = None
    quantity_ordered: int
    unit_price: float
    vat_percentage: float = 0.0
    additional_fields: Optional[Dict[str, Any]] = {}

class PurchaseOrderResponse(BaseModel):
    id: int
    group_id: Optional[int] = None
    supplier_id: int
    po_number: str
    delivery_date: Optional[date]
    quantity_ordered: int
    unit_price: float
    vat_percentage: float
    vat_amount: float
    total_po_value: float
    additional_fields: Dict[str, Any]
    created_at: datetime
    updated_at: datetime



class RawInvoiceCreate(BaseModel):
    supplier_id: int
    group_id: Optional[int] = None
    supplier_name: str  # Add this field
    invoice_number: Optional[str] = None
    total_amount: float
    status: str = "unpaid"
    invoice_date: date = Field(default_factory=date.today)
    due_date: Optional[date] = None
    additional_fields: Optional[Dict[str, Any]] = {}

class RawInvoiceResponse(BaseModel):
    id: int
    supplier_id: int
    group_id: Optional[int] = None
    supplier_name: str  # Add this field
    invoice_number: Optional[str]
    total_amount: float
    status: str
    invoice_date: date
    due_date: Optional[date]
    additional_fields: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class PaymentCreate(BaseModel):
    supplier_id: int
    group_id: Optional[int] = None  # Make this optional
    supplier_name: str
    invoice_id: Optional[int] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    amount_paid: float
    currency: str = "USD"
    payment_date: date = Field(default_factory=date.today)
    additional_fields: Optional[Dict[str, Any]] = {}

# Updated PaymentResponse model with optional group_id
class PaymentResponse(BaseModel):
    id: int
    supplier_id: int
    group_id: Optional[int]  # Make this optional too
    supplier_name: str
    invoice_id: Optional[int]
    payment_method: Optional[str]
    reference_number: Optional[str]
    amount_paid: float
    currency: str
    payment_date: date
    additional_fields: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class SupplierAccountResponse(BaseModel):
    id: int
    group_id: Optional[int]
    supplier_name: str
    supplier_code: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    contact_name: Optional[str]
    currency: str
    payment_terms: Optional[str]
    outstanding_balance: float
    additional_fields: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    orders: List[InventoryOrderItem] = []
    purchase_orders: List[PurchaseOrderResponse] = []
    invoices: List[RawInvoiceResponse] = []  # Add this field
    payments: List[PaymentResponse] = []     # Add this field
# ============================================
# HELPER FUNCTIONS
# ============================================

def parse_db_record(record) -> dict:
    """Convert database record to dict and parse JSONB fields"""
    if not record:
        return None
    
    result = dict(record)
    
    # Parse JSONB fields back to dictionaries
    if 'additional_fields' in result and isinstance(result['additional_fields'], str):
        try:
            result['additional_fields'] = json.loads(result['additional_fields'])
        except (json.JSONDecodeError, TypeError):
            result['additional_fields'] = {}
    elif 'additional_fields' not in result:
        result['additional_fields'] = {}
    
    return result

async def get_inventory_order_data(group_id: int, conn: asyncpg.Connection):
    """Get inventory order data by group_id"""
    inventory_order = await conn.fetchrow("""
        SELECT * FROM inventory_orders WHERE group_id = $1
    """, str(group_id))
    
    if not inventory_order:
        raise HTTPException(404, f"Inventory order with group_id {group_id} not found")
    
    return inventory_order
async def generate_po_number(conn, supplier_id: int) -> str:
    """Generate unique PO number in format: PO-YYYYMMDD-{supplier_id}-{sequence}"""
    from datetime import date
    
    today = date.today()
    date_str = today.strftime("%Y%m%d")  # YYYYMMDD format
    
    # Get the next sequence number for today and this supplier
    sequence = await conn.fetchval("""
        SELECT COALESCE(MAX(
            CAST(
                SUBSTRING(po_number FROM 'PO-[0-9]{8}-[0-9]+-([0-9]+)$') AS INTEGER
            )
        ), 0) + 1
        FROM purchase_orders 
        WHERE po_number LIKE $1
        AND supplier_id = $2
    """, f"PO-{date_str}-{supplier_id}-%", supplier_id)
    
    if sequence is None:
        sequence = 1
    
    po_number = f"PO-{date_str}-{supplier_id}-{sequence:03d}"
    
    # Double-check uniqueness (just to be extra safe)
    exists = await conn.fetchval("""
        SELECT 1 FROM purchase_orders WHERE po_number = $1
    """, po_number)
    
    if exists:
        # If somehow it exists, try next number
        sequence += 1
        po_number = f"PO-{date_str}-{supplier_id}-{sequence:03d}"
    
    return po_number

async def create_supplier_account_from_inventory(group_id: int, user_data: SupplierAccountCreate, conn: asyncpg.Connection):
    """Create supplier account using inventory order data (optional enhancement)"""
    # Get inventory order data
    inventory_order = await get_inventory_order_data(group_id, conn)
    
    # Create or update supplier account (removed material_type)
    supplier_id = await conn.fetchval("""
        INSERT INTO supplier_accounts (
            group_id, supplier_name, supplier_code, contact_email, 
            contact_phone, contact_name, currency, payment_terms, additional_fields
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (supplier_code) 
        DO UPDATE SET 
            group_id = EXCLUDED.group_id,
            supplier_name = EXCLUDED.supplier_name,
            contact_email = COALESCE(EXCLUDED.contact_email, supplier_accounts.contact_email),
            contact_phone = COALESCE(EXCLUDED.contact_phone, supplier_accounts.contact_phone),
            contact_name = COALESCE(EXCLUDED.contact_name, supplier_accounts.contact_name),
            currency = EXCLUDED.currency,
            payment_terms = COALESCE(EXCLUDED.payment_terms, supplier_accounts.payment_terms),
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
    """, 
    group_id, 
    inventory_order['supplier'],  # From inventory_orders
    user_data.supplier_code,  # User input - required
    user_data.contact_email,  # User input
    user_data.contact_phone,  # User input
    user_data.contact_name,  # User input
    user_data.currency,  # User input
    user_data.payment_terms,  # User input
    json.dumps(user_data.additional_fields or {}))

    if not supplier_id:
        # Get existing supplier_id if conflict occurred
        supplier_id = await conn.fetchval("""
            SELECT id FROM supplier_accounts 
            WHERE supplier_code = $1
        """, user_data.supplier_code)
    
    return supplier_id, inventory_order


async def create_supplier_account_manual(user_data: SupplierAccountCreate, conn: asyncpg.Connection):
    """Create supplier account with manual data entry"""
    supplier_id = await conn.fetchval("""
        INSERT INTO supplier_accounts (
            group_id, supplier_name, supplier_code, contact_email, 
            contact_phone, contact_name, currency, payment_terms, additional_fields
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
    """, 
    user_data.group_id,  # Optional - can be None
    user_data.supplier_name,  # User input
    user_data.supplier_code,  # User input - required and unique
    user_data.contact_email,  # User input
    user_data.contact_phone,  # User input
    user_data.contact_name,  # User input
    user_data.currency,  # User input
    user_data.payment_terms,  # User input
    json.dumps(user_data.additional_fields or {}))
    
    return supplier_id
async def create_purchase_order_from_inventory(supplier_id: int, inventory_order: dict, user_data: PurchaseOrderFromInventory, conn: asyncpg.Connection):
    """Create purchase order using inventory order data"""
    # Auto-generate PO number if not provided
    po_number = user_data.po_number or f"PO-{user_data.group_id}-{datetime.now().year}-{datetime.now().month:02d}"
    
    order_id = await conn.fetchval("""
        INSERT INTO purchase_orders (
            group_id, supplier_id, po_number, delivery_date,
            quantity_ordered, unit_price, vat_percentage, additional_fields
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (po_number) DO NOTHING
        RETURNING id
    """, 
    user_data.group_id,
    supplier_id,
    po_number,
    inventory_order['received_date'],  # From inventory_orders
    inventory_order['quantity'],  # From inventory_orders
    inventory_order['unit_price'],  # From inventory_orders
    user_data.vat_percentage,  # User input
    json.dumps(user_data.additional_fields or {}))
    
    return order_id

async def create_invoice_from_inventory(supplier_id: int, inventory_order: dict, user_data: RawInvoiceFromInventory, conn: asyncpg.Connection):
    """Create invoice using inventory order data"""
    # Auto-generate invoice number if not provided
    invoice_number = user_data.invoice_number or f"INV-{user_data.group_id}-{datetime.now().year}-{datetime.now().month:02d}"
    
    invoice_id = await conn.fetchval("""
        INSERT INTO raw_invoices (
            supplier_id, group_id, total_amount, invoice_number,
            status, invoice_date, due_date, additional_fields
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (invoice_number) DO NOTHING
        RETURNING id
    """, 
    supplier_id,
    user_data.group_id,
    inventory_order['total_price'],  # From inventory_orders
    invoice_number,
    user_data.status,  # User input
    date.today(),  # Current date
    user_data.due_date,  # User input
    json.dumps(user_data.additional_fields or {}))
    
    return invoice_id

# ============================================
# SUPPLIER ACCOUNTS ENDPOINTS
# ============================================

@router.get("/supplier-accounts-efficient")
async def get_supplier_accounts_efficient(current_user: TokenData = Depends(admin_or_manager)):
    """Get supplier accounts with inventory totals - most efficient version"""
    conn = await connect_to_db()
    try:
        result = await conn.fetch("""
            SELECT 
                sa.id,
                sa.group_id,
                sa.supplier_name,
                sa.supplier_code,
                sa.contact_email,
                sa.contact_phone,
                sa.contact_name,
                -- sa.material_type,  ❌ REMOVE THIS LINE
                sa.currency,
                sa.payment_terms,
                sa.outstanding_balance,
                sa.additional_fields,
                sa.created_at,
                sa.updated_at,
                COALESCE(inv_totals.total_orders_count, 0) as total_orders_count,
                COALESCE(inv_totals.total_amount_due, 0) as total_amount_due,
                inv_totals.latest_order_date
            FROM supplier_accounts sa
            LEFT JOIN (
                SELECT 
                    LOWER(supplier) as supplier_lower,
                    COUNT(*) as total_orders_count,
                    SUM(total_price) as total_amount_due,
                    MAX(received_date) as latest_order_date
                FROM inventory_orders 
                GROUP BY LOWER(supplier)
            ) inv_totals ON LOWER(sa.supplier_name) = inv_totals.supplier_lower
            ORDER BY inv_totals.total_amount_due DESC NULLS LAST, sa.supplier_name ASC
        """)
        
        return [
            {
                **parse_db_record(account),
                "orders": []  # Empty for efficiency
            }
            for account in result
        ]
        
    except Exception as e:
        raise HTTPException(500, f"Error fetching supplier accounts: {e}")
    finally:
        await conn.close()

@router.get("/supplier-accounts/{supplier_name}", response_model=SupplierAccountResponse)
async def get_supplier_account(supplier_name: str, current_user: TokenData = Depends(admin_or_manager)):
    """Get complete supplier account with all related data: inventory orders, purchase orders, invoices, and payments"""
    conn = await connect_to_db()
    try:
        # Fetch supplier account details by name (case insensitive)
        account = await conn.fetchrow("""
            SELECT * FROM supplier_accounts WHERE LOWER(supplier_name) = LOWER($1)
        """, supplier_name)
        
        if not account:
            raise HTTPException(404, f"Supplier account with name '{supplier_name}' not found")
        
        # Fetch all inventory orders for this supplier (case insensitive)
        orders = await conn.fetch("""
            SELECT * FROM inventory_orders WHERE LOWER(supplier) = LOWER($1)
            ORDER BY received_date DESC, created_at DESC
        """, supplier_name)
        
        # Fetch all purchase orders for this supplier using supplier_name column
        purchase_orders = await conn.fetch("""
            SELECT 
                po.id,
                po.group_id,
                po.supplier_id,
                po.po_number,
                po.supplier_name,
                po.material_type,
                po.delivery_date,
                po.quantity_ordered,
                po.unit_price,
                po.vat_percentage,
                po.vat_amount,
                po.total_po_value,
                po.additional_fields,
                po.created_at,
                po.updated_at
            FROM purchase_orders po
            WHERE LOWER(po.supplier_name) = LOWER($1)
            ORDER BY po.created_at DESC
        """, supplier_name)
        
        # Fetch all invoices for this supplier using supplier_name column
        invoices = await conn.fetch("""
            SELECT 
                inv.id,
                inv.supplier_id,
                inv.group_id,
                inv.supplier_name,
                inv.invoice_number,
                inv.total_amount,
                inv.status,
                inv.invoice_date,
                inv.due_date,
                inv.additional_fields,
                inv.created_at,
                inv.updated_at
            FROM raw_invoices inv
            WHERE LOWER(inv.supplier_name) = LOWER($1)
            ORDER BY inv.invoice_date DESC, inv.created_at DESC
        """, supplier_name)
        
        # Fetch all payments for this supplier using supplier_name column
        payments = await conn.fetch("""
            SELECT 
                pay.id,
                pay.supplier_id,
                pay.group_id,
                pay.supplier_name,
                pay.invoice_id,
                pay.payment_method,
                pay.reference_number,
                pay.amount_paid,
                pay.currency,
                pay.payment_date,
                pay.additional_fields,
                pay.created_at,
                pay.updated_at
            FROM payments pay
            WHERE LOWER(pay.supplier_name) = LOWER($1)
            ORDER BY pay.payment_date DESC, pay.created_at DESC
        """, supplier_name)
        
        # Parse the account data
        account_data = parse_db_record(account)
        
        # Add all related data to the response
        account_data['orders'] = [parse_db_record(order) for order in orders]
        account_data['purchase_orders'] = [parse_db_record(po) for po in purchase_orders]
        account_data['invoices'] = [parse_db_record(inv) for inv in invoices]
        account_data['payments'] = [parse_db_record(pay) for pay in payments]
        
        # Add comprehensive summary statistics to additional_fields
        if 'additional_fields' not in account_data:
            account_data['additional_fields'] = {}
        
        # Inventory orders summary
        if orders:
            total_inventory_value = sum(float(order['total_price']) for order in orders)
            total_inventory_quantity = sum(int(order['quantity']) for order in orders)
            
            account_data['additional_fields']['inventory_summary'] = {
                'total_orders': len(orders),
                'total_value': total_inventory_value,
                'total_quantity': total_inventory_quantity,
                'latest_order_date': orders[0]['received_date'].isoformat() if orders[0]['received_date'] else None
            }
        
        # Purchase orders summary
        if purchase_orders:
            total_po_value = sum(float(po['total_po_value']) for po in purchase_orders)
            total_po_quantity = sum(int(po['quantity_ordered']) for po in purchase_orders)
            
            account_data['additional_fields']['purchase_orders_summary'] = {
                'total_pos': len(purchase_orders),
                'total_po_value': total_po_value,
                'total_po_quantity': total_po_quantity,
                'latest_po_date': purchase_orders[0]['created_at'].isoformat() if purchase_orders[0]['created_at'] else None
            }
        
        # Invoices summary
        if invoices:
            total_invoice_amount = sum(float(inv['total_amount']) for inv in invoices)
            unpaid_invoices = [inv for inv in invoices if inv['status'] == 'unpaid']
            paid_invoices = [inv for inv in invoices if inv['status'] == 'paid']
            partial_invoices = [inv for inv in invoices if inv['status'] == 'partial']
            
            unpaid_amount = sum(float(inv['total_amount']) for inv in unpaid_invoices)
            paid_amount = sum(float(inv['total_amount']) for inv in paid_invoices)
            partial_amount = sum(float(inv['total_amount']) for inv in partial_invoices)
            
            # Find overdue invoices
            from datetime import date
            today = date.today()
            overdue_invoices = [inv for inv in unpaid_invoices if inv['due_date'] and inv['due_date'] < today]
            overdue_amount = sum(float(inv['total_amount']) for inv in overdue_invoices)
            
            account_data['additional_fields']['invoices_summary'] = {
                'total_invoices': len(invoices),
                'total_amount': total_invoice_amount,
                'unpaid_count': len(unpaid_invoices),
                'unpaid_amount': unpaid_amount,
                'paid_count': len(paid_invoices),
                'paid_amount': paid_amount,
                'partial_count': len(partial_invoices),
                'partial_amount': partial_amount,
                'overdue_count': len(overdue_invoices),
                'overdue_amount': overdue_amount,
                'latest_invoice_date': invoices[0]['invoice_date'].isoformat() if invoices[0]['invoice_date'] else None
            }
        
        # Payments summary
        if payments:
            total_payments_amount = sum(float(pay['amount_paid']) for pay in payments)
            
            # Group by currency
            currency_summary = {}
            for payment in payments:
                currency = payment['currency']
                if currency not in currency_summary:
                    currency_summary[currency] = {'count': 0, 'amount': 0}
                currency_summary[currency]['count'] += 1
                currency_summary[currency]['amount'] += float(payment['amount_paid'])
            
            # Group by payment method
            method_summary = {}
            for payment in payments:
                method = payment['payment_method'] or 'Unknown'
                if method not in method_summary:
                    method_summary[method] = {'count': 0, 'amount': 0}
                method_summary[method]['count'] += 1
                method_summary[method]['amount'] += float(payment['amount_paid'])
            
            account_data['additional_fields']['payments_summary'] = {
                'total_payments': len(payments),
                'total_amount': total_payments_amount,
                'currency_breakdown': currency_summary,
                'payment_method_breakdown': method_summary,
                'latest_payment_date': payments[0]['payment_date'].isoformat() if payments[0]['payment_date'] else None
            }
        
        # Overall financial summary
        total_invoiced = account_data['additional_fields'].get('invoices_summary', {}).get('total_amount', 0)
        total_paid = account_data['additional_fields'].get('payments_summary', {}).get('total_amount', 0)
        outstanding_balance = total_invoiced - total_paid
        
        account_data['additional_fields']['financial_summary'] = {
            'total_business_value': account_data['additional_fields'].get('inventory_summary', {}).get('total_value', 0),
            'total_invoiced': total_invoiced,
            'total_paid': total_paid,
            'outstanding_balance': outstanding_balance,
            'payment_completion_rate': (total_paid / total_invoiced * 100) if total_invoiced > 0 else 0
        }
        
        return SupplierAccountResponse(**account_data)
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching supplier data: {e}")
    finally:
        await conn.close()


@router.get("/supplier-accounts/{supplier_name}/summary")
async def get_supplier_summary(supplier_name: str, current_user: TokenData = Depends(admin_or_manager)):
    """Get supplier summary with aggregated statistics only (no detailed records)"""
    conn = await connect_to_db()
    try:
        # Check if supplier exists
        account = await conn.fetchrow("""
            SELECT id, supplier_name, supplier_code, currency FROM supplier_accounts 
            WHERE LOWER(supplier_name) = LOWER($1)
        """, supplier_name)
        
        if not account:
            raise HTTPException(404, f"Supplier account with name '{supplier_name}' not found")
        
        # Get inventory orders summary
        inventory_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as order_count,
                COALESCE(SUM(total_price), 0) as total_value,
                COALESCE(SUM(quantity), 0) as total_quantity,
                MAX(received_date) as latest_order_date
            FROM inventory_orders 
            WHERE LOWER(supplier) = LOWER($1)
        """, supplier_name)
        
        # Get purchase orders summary
        po_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as po_count,
                COALESCE(SUM(total_po_value), 0) as total_po_value,
                COALESCE(SUM(quantity_ordered), 0) as total_po_quantity,
                MAX(created_at) as latest_po_date
            FROM purchase_orders 
            WHERE LOWER(supplier_name) = LOWER($1)
        """, supplier_name)
        
        # Get invoices summary
        invoice_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_invoices,
                COALESCE(SUM(total_amount), 0) as total_amount,
                COALESCE(SUM(CASE WHEN status = 'unpaid' THEN total_amount ELSE 0 END), 0) as unpaid_amount,
                COALESCE(SUM(CASE WHEN status = 'paid' THEN total_amount ELSE 0 END), 0) as paid_amount,
                COUNT(CASE WHEN status = 'unpaid' THEN 1 END) as unpaid_count,
                COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count,
                COUNT(CASE WHEN status = 'unpaid' AND due_date < CURRENT_DATE THEN 1 END) as overdue_count,
                MAX(invoice_date) as latest_invoice_date
            FROM raw_invoices 
            WHERE LOWER(supplier_name) = LOWER($1)
        """, supplier_name)
        
        # Get payments summary
        payment_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as payment_count,
                COALESCE(SUM(amount_paid), 0) as total_paid,
                MAX(payment_date) as latest_payment_date
            FROM payments 
            WHERE LOWER(supplier_name) = LOWER($1)
        """, supplier_name)
        
        # Calculate derived metrics
        total_invoiced = float(invoice_stats['total_amount']) if invoice_stats['total_amount'] else 0
        total_paid = float(payment_stats['total_paid']) if payment_stats['total_paid'] else 0
        outstanding_balance = total_invoiced - total_paid
        payment_rate = (total_paid / total_invoiced * 100) if total_invoiced > 0 else 0
        
        return {
            "supplier_info": {
                "id": account['id'],
                "supplier_name": account['supplier_name'],
                "supplier_code": account['supplier_code'],
                "currency": account['currency']
            },
            "inventory_summary": {
                "total_orders": inventory_stats['order_count'],
                "total_value": float(inventory_stats['total_value']),
                "total_quantity": inventory_stats['total_quantity'],
                "latest_order_date": inventory_stats['latest_order_date'].isoformat() if inventory_stats['latest_order_date'] else None
            },
            "purchase_orders_summary": {
                "total_pos": po_stats['po_count'],
                "total_po_value": float(po_stats['total_po_value']),
                "total_po_quantity": po_stats['total_po_quantity'],
                "latest_po_date": po_stats['latest_po_date'].isoformat() if po_stats['latest_po_date'] else None
            },
            "invoices_summary": {
                "total_invoices": invoice_stats['total_invoices'],
                "total_amount": total_invoiced,
                "unpaid_count": invoice_stats['unpaid_count'],
                "unpaid_amount": float(invoice_stats['unpaid_amount']),
                "paid_count": invoice_stats['paid_count'],
                "paid_amount": float(invoice_stats['paid_amount']),
                "overdue_count": invoice_stats['overdue_count'],
                "latest_invoice_date": invoice_stats['latest_invoice_date'].isoformat() if invoice_stats['latest_invoice_date'] else None
            },
            "payments_summary": {
                "total_payments": payment_stats['payment_count'],
                "total_amount": total_paid,
                "latest_payment_date": payment_stats['latest_payment_date'].isoformat() if payment_stats['latest_payment_date'] else None
            },
            "financial_summary": {
                "total_invoiced": total_invoiced,
                "total_paid": total_paid,
                "outstanding_balance": outstanding_balance,
                "payment_completion_rate": round(payment_rate, 2)
            }
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching supplier summary: {e}")
    finally:
        await conn.close()
# ============================================
# NEW ENDPOINTS - CREATE FROM INVENTORY ORDERS
# ============================================

# @router.post("/supplier-accounts/from-inventory", response_model=SupplierAccountResponse)
# async def create_supplier_account_from_inventory_order(
#     account_data: SupplierAccountFromInventory,
#     current_user: TokenData = Depends(admin_or_manager)
# ):
#     """Create supplier account by fetching data from inventory_orders table using group_id"""
#     conn = await connect_to_db()
#     try:
#         supplier_id, inventory_order = await create_supplier_account_from_inventory(
#             account_data.group_id, account_data, conn
#         )
#         return await get_supplier_account(supplier_id, current_user)
#     except Exception as e:
#         raise HTTPException(500, f"Error creating supplier account from inventory: {e}")
#     finally:
#         await conn.close()



@router.post("/supplier-accounts", response_model=SupplierAccountResponse)
async def create_supplier_account(
    account_data: SupplierAccountCreate,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create supplier account with manual data entry or optionally from inventory_orders using group_id"""
    conn = await connect_to_db()
    try:
        if account_data.group_id:
            # Create from inventory order if group_id is provided
            supplier_id, inventory_order = await create_supplier_account_from_inventory(
                account_data.group_id, account_data, conn
            )
        else:
            # Create with manual data entry
            supplier_id = await create_supplier_account_manual(account_data, conn)
        
        return await get_supplier_account(supplier_id, current_user)
    except Exception as e:
        raise HTTPException(500, f"Error creating supplier account: {e}")
    finally:
        await conn.close()

@router.post("/purchase-orders/from-inventory", response_model=PurchaseOrderResponse)
async def create_purchase_order_from_inventory_order(
    order_data: PurchaseOrderFromInventory,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create purchase order by fetching data from inventory_orders table using group_id"""
    conn = await connect_to_db()
    try:
        # Get inventory order data
        inventory_order = await get_inventory_order_data(order_data.group_id, conn)
        
        # Get or create supplier account first
        supplier_id = await conn.fetchval("""
            SELECT id FROM supplier_accounts 
            WHERE group_id = $1 AND LOWER(supplier_name) = LOWER($2)
        """, order_data.group_id, inventory_order['supplier'])
        
        if not supplier_id:
            # Create basic supplier account if it doesn't exist
            supplier_data = SupplierAccountFromInventory(group_id=order_data.group_id)
            supplier_id, _ = await create_supplier_account_from_inventory(
                order_data.group_id, supplier_data, conn
            )
        
        # Create purchase order
        order_id = await create_purchase_order_from_inventory(
            supplier_id, inventory_order, order_data, conn
        )
        
        if not order_id:
            raise HTTPException(400, "Purchase order with this PO number already exists")
            
        return await get_purchase_order(order_id, current_user)
    except Exception as e:
        raise HTTPException(500, f"Error creating purchase order from inventory: {e}")
    finally:
        await conn.close()

@router.post("/invoices/from-inventory", response_model=RawInvoiceResponse)
async def create_invoice_from_inventory_order(
    invoice_data: RawInvoiceFromInventory,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create invoice by fetching data from inventory_orders table using group_id"""
    conn = await connect_to_db()
    try:
        # Get inventory order data
        inventory_order = await get_inventory_order_data(invoice_data.group_id, conn)
        
        # Get or create supplier account first
        supplier_id = await conn.fetchval("""
            SELECT id FROM supplier_accounts 
            WHERE group_id = $1 AND LOWER(supplier_name) = LOWER($2)
        """, invoice_data.group_id, inventory_order['supplier'])
        
        if not supplier_id:
            # Create basic supplier account if it doesn't exist
            supplier_data = SupplierAccountFromInventory(group_id=invoice_data.group_id)
            supplier_id, _ = await create_supplier_account_from_inventory(
                invoice_data.group_id, supplier_data, conn
            )
        
        # Create invoice
        invoice_id = await create_invoice_from_inventory(
            supplier_id, inventory_order, invoice_data, conn
        )
        
        if not invoice_id:
            raise HTTPException(400, "Invoice with this invoice number already exists")
            
        return await get_invoice(invoice_id, current_user)
    except Exception as e:
        raise HTTPException(500, f"Error creating invoice from inventory: {e}")
    finally:
        await conn.close()

@router.post("/accounting/complete-setup/{group_id}")
async def complete_accounting_setup_from_inventory(
    group_id: int,
    supplier_data: Optional[SupplierAccountFromInventory] = None,
    po_data: Optional[PurchaseOrderFromInventory] = None,
    invoice_data: Optional[RawInvoiceFromInventory] = None,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create complete accounting setup (supplier account, PO, and invoice) from inventory order"""
    conn = await connect_to_db()
    try:
        async with conn.transaction():
            # Use provided data or create with defaults
            supplier_data = supplier_data or SupplierAccountFromInventory(group_id=group_id)
            po_data = po_data or PurchaseOrderFromInventory(group_id=group_id)
            invoice_data = invoice_data or RawInvoiceFromInventory(group_id=group_id)
            
            # Ensure all have the same group_id
            supplier_data.group_id = group_id
            po_data.group_id = group_id
            invoice_data.group_id = group_id
            
            # Create supplier account
            supplier_id, inventory_order = await create_supplier_account_from_inventory(
                group_id, supplier_data, conn
            )
            
            # Create purchase order
            order_id = await create_purchase_order_from_inventory(
                supplier_id, inventory_order, po_data, conn
            )
            
            # Create invoice
            invoice_id = await create_invoice_from_inventory(
                supplier_id, inventory_order, invoice_data, conn
            )
            
            return {
                "message": f"Complete accounting setup created for group_id {group_id}",
                "supplier_id": supplier_id,
                "purchase_order_id": order_id,
                "invoice_id": invoice_id,
                "inventory_data": {
                    "supplier": inventory_order['supplier'],
                    "material_type": inventory_order['material_type'],
                    "quantity": inventory_order['quantity'],
                    "unit_price": float(inventory_order['unit_price']),
                    "total_price": float(inventory_order['total_price']),
                    "received_date": inventory_order['received_date'].isoformat() if inventory_order['received_date'] else None
                }
            }
    except Exception as e:
        raise HTTPException(500, f"Error creating complete accounting setup: {e}")
    finally:
        await conn.close()

@router.get("/inventory-preview/{group_id}")
async def preview_inventory_order_data(
    group_id: int,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Preview inventory order data before creating accounting records"""
    conn = await connect_to_db()
    try:
        inventory_order = await get_inventory_order_data(group_id, conn)
        
        return {
            "group_id": group_id,
            "supplier": inventory_order['supplier'],
            "material_type": inventory_order['material_type'],
            "category": inventory_order['category'],
            "quantity": inventory_order['quantity'],
            "unit_price": float(inventory_order['unit_price']),
            "total_price": float(inventory_order['total_price']),
            "received_date": inventory_order['received_date'].isoformat() if inventory_order['received_date'] else None,
            "created_at": inventory_order['created_at'].isoformat() if inventory_order.get('created_at') else None
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching inventory order data: {e}")
    finally:
        await conn.close()

@router.get("/supplier-accounts/{supplier_id}", response_model=SupplierAccountResponse)
async def get_supplier_account(supplier_id: int, current_user: TokenData = Depends(admin_or_manager)):
    """Get specific supplier account and related orders by supplier ID"""
    conn = await connect_to_db()
    try:
        # Fetch supplier account details by ID
        account = await conn.fetchrow("""
            SELECT * FROM supplier_accounts WHERE id = $1
        """, supplier_id)
        
        if not account:
            raise HTTPException(404, f"Supplier account with ID {supplier_id} not found")
        
        # Fetch all inventory orders for this supplier (case insensitive)
        orders = await conn.fetch("""
            SELECT * FROM inventory_orders WHERE LOWER(supplier) = LOWER($1)
        """, account['supplier_name'])
        
        # Parse the account data
        account_data = parse_db_record(account)
        
        # Add orders data to the response
        account_data['orders'] = [parse_db_record(order) for order in orders]
        
        return SupplierAccountResponse(**account_data)
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching supplier data: {e}")
    finally:
        await conn.close()
# ============================================
# PURCHASE ORDERS ENDPOINTS
# ============================================

@router.get("/purchase-orders", response_model=List[PurchaseOrderResponse])
async def get_purchase_orders(current_user: TokenData = Depends(admin_or_manager)):
    """Get all purchase orders"""
    conn = await connect_to_db()
    try:
        orders = await conn.fetch("""
            SELECT * FROM purchase_orders 
            ORDER BY created_at DESC
        """)
        return [PurchaseOrderResponse(**parse_db_record(order)) for order in orders]
    except Exception as e:
        raise HTTPException(500, f"Error fetching purchase orders: {e}")
    finally:
        await conn.close()

@router.get("/purchase-orders/{order_id}", response_model=PurchaseOrderResponse)
async def get_purchase_order(order_id: int, current_user: TokenData = Depends(admin_or_manager)):
    """Get specific purchase order"""
    conn = await connect_to_db()
    try:
        order = await conn.fetchrow("""
            SELECT * FROM purchase_orders WHERE id = $1
        """, order_id)
        
        if not order:
            raise HTTPException(404, f"Purchase order with ID {order_id} not found")
            
        return PurchaseOrderResponse(**parse_db_record(order))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching purchase order: {e}")
    finally:
        await conn.close()

@router.post("/purchase-orders/manual", response_model=PurchaseOrderResponse)
async def create_purchase_order_manual(
    order: PurchaseOrderCreate,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create new purchase order with manual data entry and auto-generated PO number"""
    conn = await connect_to_db()
    try:
        async with conn.transaction():
            # Generate PO number if not provided
            po_number = order.po_number
            if not po_number:
                po_number = await generate_po_number(conn, order.supplier_id)
            else:
                # If PO number is provided, check if it already exists
                exists = await conn.fetchval("""
                    SELECT 1 FROM purchase_orders WHERE po_number = $1
                """, po_number)
                if exists:
                    raise HTTPException(400, f"PO number '{po_number}' already exists")
            
            order_id = await conn.fetchval("""
                INSERT INTO purchase_orders (
                    group_id, supplier_id, supplier_name, po_number, material_type,
                    delivery_date, quantity_ordered, unit_price, vat_percentage, additional_fields
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """, 
            order.group_id, 
            order.supplier_id, 
            order.supplier_name,
            po_number,  # Use generated or provided PO number
            order.material_type,
            order.delivery_date,
            order.quantity_ordered, 
            order.unit_price, 
            order.vat_percentage, 
            json.dumps(order.additional_fields or {}))
        
        return await get_purchase_order(order_id, current_user)
    except Exception as e:
        raise HTTPException(500, f"Error creating purchase order: {e}")
    finally:
        await conn.close()



# ============================================
# RAW INVOICES ENDPOINTS
# ============================================

@router.get("/invoices", response_model=List[RawInvoiceResponse])
async def get_invoices(current_user: TokenData = Depends(admin_or_manager)):
    """Get all invoices"""
    conn = await connect_to_db()
    try:
        invoices = await conn.fetch("""
            SELECT * FROM raw_invoices 
            ORDER BY created_at DESC
        """)
        return [RawInvoiceResponse(**parse_db_record(invoice)) for invoice in invoices]
    except Exception as e:
        raise HTTPException(500, f"Error fetching invoices: {e}")
    finally:
        await conn.close()

@router.get("/invoices/{invoice_id}", response_model=RawInvoiceResponse)
async def get_invoice(invoice_id: int, current_user: TokenData = Depends(admin_or_manager)):
    """Get specific invoice"""
    conn = await connect_to_db()
    try:
        invoice = await conn.fetchrow("""
            SELECT * FROM raw_invoices WHERE id = $1
        """, invoice_id)
        
        if not invoice:
            raise HTTPException(404, f"Invoice with ID {invoice_id} not found")
            
        return RawInvoiceResponse(**parse_db_record(invoice))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching invoice: {e}")
    finally:
        await conn.close()

@router.get("/invoices/supplier/{supplier_name}")
async def get_invoices_by_supplier_name(supplier_name: str, current_user: TokenData = Depends(admin_or_manager)):
    """Get all invoices for a specific supplier by name"""
    conn = await connect_to_db()
    try:
        invoices = await conn.fetch("""
            SELECT * FROM raw_invoices 
            WHERE LOWER(supplier_name) = LOWER($1)
            ORDER BY invoice_date DESC, created_at DESC
        """, supplier_name)
        
        if not invoices:
            return {
                "supplier_name": supplier_name,
                "message": "No invoices found for this supplier",
                "invoices": []
            }
        
        # Calculate summary
        total_amount = sum(float(inv['total_amount']) for inv in invoices)
        unpaid_amount = sum(float(inv['total_amount']) for inv in invoices if inv['status'] == 'unpaid')
        paid_amount = sum(float(inv['total_amount']) for inv in invoices if inv['status'] == 'paid')
        
        return {
            "supplier_name": supplier_name,
            "total_invoices": len(invoices),
            "total_amount": total_amount,
            "unpaid_amount": unpaid_amount,
            "paid_amount": paid_amount,
            "invoices": [parse_db_record(inv) for inv in invoices]
        }
        
    except Exception as e:
        raise HTTPException(500, f"Error fetching supplier invoices: {e}")
    finally:
        await conn.close()

@router.post("/invoices/manual", response_model=RawInvoiceResponse)
async def create_invoice_manual(
    invoice: RawInvoiceCreate,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create new invoice with manual data entry"""
    conn = await connect_to_db()
    try:
        invoice_id = await conn.fetchval("""
            INSERT INTO raw_invoices (
                supplier_id, group_id, supplier_name, invoice_number, total_amount,
                status, invoice_date, due_date, additional_fields
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """, 
        invoice.supplier_id, 
        invoice.group_id, 
        invoice.supplier_name,  # Add supplier_name
        invoice.invoice_number,
        invoice.total_amount, 
        invoice.status, 
        invoice.invoice_date,
        invoice.due_date, 
        json.dumps(invoice.additional_fields or {}))
        
        return await get_invoice(invoice_id, current_user)
    except Exception as e:
        raise HTTPException(500, f"Error creating invoice: {e}")
    finally:
        await conn.close()

@router.put("/invoices/{invoice_id}/status")
async def update_invoice_status(
    invoice_id: int,
    status: str,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Update invoice status"""
    conn = await connect_to_db()
    try:
        await conn.execute("""
            UPDATE raw_invoices SET 
                status = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """, invoice_id, status)
        
        return {"message": f"Invoice {invoice_id} status updated to {status}"}
    except Exception as e:
        raise HTTPException(500, f"Error updating invoice status: {e}")
    finally:
        await conn.close()

# ============================================
# PAYMENTS ENDPOINTS
# ============================================

@router.get("/payments", response_model=List[PaymentResponse])
async def get_payments(current_user: TokenData = Depends(admin_or_manager)):
    """Get all payments"""
    conn = await connect_to_db()
    try:
        payments = await conn.fetch("""
            SELECT * FROM payments 
            ORDER BY payment_date DESC, created_at DESC
        """)
        return [PaymentResponse(**parse_db_record(payment)) for payment in payments]
    except Exception as e:
        raise HTTPException(500, f"Error fetching payments: {e}")
    finally:
        await conn.close()


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: int, current_user: TokenData = Depends(admin_or_manager)):
    """Get specific payment"""
    conn = await connect_to_db()
    try:
        payment = await conn.fetchrow("""
            SELECT * FROM payments WHERE id = $1
        """, payment_id)
        
        if not payment:
            raise HTTPException(404, f"Payment with ID {payment_id} not found")
            
        return PaymentResponse(**parse_db_record(payment))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Error fetching payment: {e}")
    finally:
        await conn.close()


@router.get("/payments/supplier/{supplier_name}")
async def get_payments_by_supplier_name(supplier_name: str, current_user: TokenData = Depends(admin_or_manager)):
    """Get all payments for a specific supplier by name"""
    conn = await connect_to_db()
    try:
        payments = await conn.fetch("""
            SELECT * FROM payments 
            WHERE LOWER(supplier_name) = LOWER($1)
            ORDER BY payment_date DESC, created_at DESC
        """, supplier_name)
        
        if not payments:
            return {
                "supplier_name": supplier_name,
                "message": "No payments found for this supplier",
                "payments": []
            }
        
        # Calculate summary
        total_amount = sum(float(payment['amount_paid']) for payment in payments)
        payment_count = len(payments)
        
        # Group by currency if multiple currencies exist
        currency_summary = {}
        for payment in payments:
            currency = payment['currency']
            if currency not in currency_summary:
                currency_summary[currency] = 0
            currency_summary[currency] += float(payment['amount_paid'])
        
        return {
            "supplier_name": supplier_name,
            "total_payments": payment_count,
            "total_amount": total_amount,
            "currency_summary": currency_summary,
            "latest_payment_date": payments[0]['payment_date'].isoformat() if payments[0]['payment_date'] else None,
            "payments": [parse_db_record(payment) for payment in payments]
        }
        
    except Exception as e:
        raise HTTPException(500, f"Error fetching supplier payments: {e}")
    finally:
        await conn.close()       


@router.post("/payments", response_model=PaymentResponse)
async def create_payment(
    payment: PaymentCreate,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create new payment"""
    conn = await connect_to_db()
    try:
        async with conn.transaction():
            # Create payment record
            payment_id = await conn.fetchval("""
                INSERT INTO payments (
                    supplier_id, group_id, supplier_name, invoice_id, payment_method,
                    reference_number, amount_paid, currency, payment_date, additional_fields
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """, 
            payment.supplier_id, 
            payment.group_id,  # Can now be None/NULL
            payment.supplier_name,
            payment.invoice_id,
            payment.payment_method, 
            payment.reference_number, 
            payment.amount_paid,
            payment.currency, 
            payment.payment_date, 
            json.dumps(payment.additional_fields or {}))
            
            # Update invoice status if fully paid
            if payment.invoice_id:
                total_payments = await conn.fetchval("""
                    SELECT SUM(amount_paid) FROM payments WHERE invoice_id = $1
                """, payment.invoice_id)
                
                invoice_amount = await conn.fetchval("""
                    SELECT total_amount FROM raw_invoices WHERE id = $1
                """, payment.invoice_id)
                
                if total_payments >= invoice_amount:
                    await conn.execute("""
                        UPDATE raw_invoices SET 
                            status = 'paid', updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                    """, payment.invoice_id)
                elif total_payments > 0:
                    await conn.execute("""
                        UPDATE raw_invoices SET 
                            status = 'partial', updated_at = CURRENT_TIMESTAMP
                        WHERE id = $1
                    """, payment.invoice_id)
        
        return await get_payment(payment_id, current_user)
    except Exception as e:
        raise HTTPException(500, f"Error creating payment: {e}")
    finally:
        await conn.close()

# ============================================
# SYNC ENDPOINTS (Updated to use new functions)
# ============================================

@router.post("/sync/inventory-order/{group_id}")
async def sync_inventory_order(
    group_id: int,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Sync specific inventory order to accounting system"""
    conn = await connect_to_db()
    try:
        async with conn.transaction():
            # Create default data objects
            supplier_data = SupplierAccountFromInventory(group_id=group_id)
            po_data = PurchaseOrderFromInventory(group_id=group_id)
            invoice_data = RawInvoiceFromInventory(group_id=group_id)
            
            # Create supplier account
            supplier_id, inventory_order = await create_supplier_account_from_inventory(
                group_id, supplier_data, conn
            )
            
            # Create purchase order
            order_id = await create_purchase_order_from_inventory(
                supplier_id, inventory_order, po_data, conn
            )
            
            # Create invoice
            invoice_id = await create_invoice_from_inventory(
                supplier_id, inventory_order, invoice_data, conn
            )
            
            return {
                "message": f"Successfully synced inventory order {group_id} to accounting system",
                "supplier_id": supplier_id,
                "purchase_order_id": order_id,
                "invoice_id": invoice_id,
                "supplier_name": inventory_order['supplier']
            }
    except Exception as e:
        raise HTTPException(500, f"Error syncing inventory order: {e}")
    finally:
        await conn.close()

@router.post("/sync/all-inventory-orders")
async def sync_all_inventory_orders(current_user: TokenData = Depends(admin_or_manager)):
    """Sync all inventory orders to accounting system"""
    conn = await connect_to_db()
    try:
        # Get all inventory orders
        inventory_orders = await conn.fetch("SELECT DISTINCT group_id FROM inventory_orders")
        
        synced_count = 0
        errors = []
        successful_syncs = []
        
        for order in inventory_orders:
            try:
                group_id = int(order['group_id'])
                
                async with conn.transaction():
                    # Create default data objects
                    supplier_data = SupplierAccountFromInventory(group_id=group_id)
                    po_data = PurchaseOrderFromInventory(group_id=group_id)
                    invoice_data = RawInvoiceFromInventory(group_id=group_id)
                    
                    # Create supplier account
                    supplier_id, inventory_order_data = await create_supplier_account_from_inventory(
                        group_id, supplier_data, conn
                    )
                    
                    # Create purchase order
                    order_id = await create_purchase_order_from_inventory(
                        supplier_id, inventory_order_data, po_data, conn
                    )
                    
                    # Create invoice
                    invoice_id = await create_invoice_from_inventory(
                        supplier_id, inventory_order_data, invoice_data, conn
                    )
                    
                    successful_syncs.append({
                        "group_id": group_id,
                        "supplier_name": inventory_order_data['supplier'],
                        "supplier_id": supplier_id,
                        "purchase_order_id": order_id,
                        "invoice_id": invoice_id
                    })
                    
                synced_count += 1
                
            except Exception as e:
                errors.append(f"Group {order['group_id']}: {str(e)}")
        
        return {
            "message": f"Synced {synced_count} inventory orders to accounting system",
            "synced_count": synced_count,
            "total_orders": len(inventory_orders),
            "errors": errors,
            "successful_syncs": successful_syncs
        }
    except Exception as e:
        raise HTTPException(500, f"Error syncing all inventory orders: {e}")
    finally:
        await conn.close()

# ============================================
# REPORTING ENDPOINTS
# ============================================

@router.get("/reports/supplier-summary")
async def get_supplier_summary(current_user: TokenData = Depends(admin_or_manager)):
    """Get supplier summary report"""
    conn = await connect_to_db()
    try:
        summary = await conn.fetch("""
            SELECT * FROM supplier_summary ORDER BY outstanding_balance DESC
        """)
        return [dict(row) for row in summary]
    except Exception as e:
        raise HTTPException(500, f"Error fetching supplier summary: {e}")
    finally:
        await conn.close()

@router.get("/reports/pending-payments")
async def get_pending_payments(current_user: TokenData = Depends(admin_or_manager)):
    """Get pending payments report"""
    conn = await connect_to_db()
    try:
        pending = await conn.fetch("""
            SELECT * FROM pending_payments ORDER BY due_date ASC
        """)
        return [dict(row) for row in pending]
    except Exception as e:
        raise HTTPException(500, f"Error fetching pending payments: {e}")
    finally:
        await conn.close()

@router.get("/reports/accounting-overview")
async def get_accounting_overview(current_user: TokenData = Depends(admin_or_manager)):
    """Get overall accounting metrics"""
    conn = await connect_to_db()
    try:
        total_outstanding = await conn.fetchval("""
            SELECT COALESCE(SUM(outstanding_balance), 0) FROM supplier_accounts
        """)
        
        total_invoices = await conn.fetchval("""
            SELECT COALESCE(SUM(total_amount), 0) FROM raw_invoices
        """)
        
        total_payments = await conn.fetchval("""
            SELECT COALESCE(SUM(amount_paid), 0) FROM payments
        """)
        
        unpaid_invoices = await conn.fetchval("""
            SELECT COUNT(*) FROM raw_invoices WHERE status = 'unpaid'
        """)
        
        overdue_invoices = await conn.fetchval("""
            SELECT COUNT(*) FROM raw_invoices 
            WHERE status = 'unpaid' AND due_date < CURRENT_DATE
        """)
        
        return {
            "total_outstanding_balance": float(total_outstanding),
            "total_invoiced_amount": float(total_invoices),
            "total_payments_made": float(total_payments),
            "unpaid_invoices_count": unpaid_invoices,
            "overdue_invoices_count": overdue_invoices,
            "payment_completion_rate": float(total_payments / total_invoices * 100) if total_invoices > 0 else 0
        }
    except Exception as e:
        raise HTTPException(500, f"Error fetching accounting overview: {e}")
    finally:
        await conn.close()


        
# ============================================
# ORIGINAL MANUAL ENDPOINTS (for manual data entry)
# ============================================

@router.post("/supplier-accounts/manual", response_model=SupplierAccountResponse)
async def create_supplier_account_manual_endpoint(
    account: SupplierAccountCreate,
    current_user: TokenData = Depends(admin_or_manager)
):
    """Create new supplier account with manual data entry"""
    conn = await connect_to_db()
    try:
        account_id = await conn.fetchval("""
            INSERT INTO supplier_accounts (
                group_id, supplier_name, supplier_code, contact_email, contact_phone, 
                contact_name, currency, payment_terms, additional_fields
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """, account.group_id, account.supplier_name, account.supplier_code, account.contact_email,
        account.contact_phone, account.contact_name,
        account.currency, account.payment_terms, json.dumps(account.additional_fields or {}))
        
        # Get the created account by ID
        created_account = await conn.fetchrow("""
            SELECT * FROM supplier_accounts WHERE id = $1
        """, account_id)
        
        account_data = parse_db_record(created_account)
        account_data['orders'] = []  # No orders initially
        
        return SupplierAccountResponse(**account_data)
        
    except Exception as e:
        raise HTTPException(500, f"Error creating supplier account: {e}")
    finally:
        await conn.close()