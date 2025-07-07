--
-- PostgreSQL database dump
--

-- Dumped from database version 16.8
-- Dumped by pg_dump version 16.8

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: analytics; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA analytics;


ALTER SCHEMA analytics OWNER TO postgres;

--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: bank_or_cash_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.bank_or_cash_enum AS ENUM (
    'bank',
    'cash'
);


ALTER TYPE public.bank_or_cash_enum OWNER TO postgres;

--
-- Name: field_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.field_type_enum AS ENUM (
    'text',
    'number',
    'date',
    'boolean',
    'select',
    'textarea'
);


ALTER TYPE public.field_type_enum OWNER TO postgres;

--
-- Name: payment_method_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.payment_method_enum AS ENUM (
    'bank_transfer',
    'cash',
    'check',
    'credit_card',
    'online',
    'other'
);


ALTER TYPE public.payment_method_enum OWNER TO postgres;

--
-- Name: payment_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.payment_status_enum AS ENUM (
    'paid',
    'unpaid',
    'partial',
    'overdue'
);


ALTER TYPE public.payment_status_enum OWNER TO postgres;

--
-- Name: ph_stage; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.ph_stage AS ENUM (
    'INJECTION',
    'WEIGHING',
    'METAL_DETECT',
    'SIZING',
    'PLASTIC_CLIPS',
    'METAL_CLIPS',
    'PACKAGING'
);


ALTER TYPE public.ph_stage OWNER TO postgres;

--
-- Name: roll_stage; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.roll_stage AS ENUM (
    'BLOWING',
    'PRINTING',
    'CUTTING',
    'PACKAGING',
    'METAL_DETECT'
);


ALTER TYPE public.roll_stage OWNER TO postgres;

--
-- Name: add_dynamic_field(jsonb, text, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.add_dynamic_field(existing_json jsonb, field_name text, field_value text) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF existing_json IS NULL THEN
        RETURN jsonb_build_object(field_name, field_value);
    ELSE
        RETURN existing_json || jsonb_build_object(field_name, field_value);
    END IF;
END;
$$;


ALTER FUNCTION public.add_dynamic_field(existing_json jsonb, field_name text, field_value text) OWNER TO postgres;

--
-- Name: add_dynamic_field(text, uuid, text, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.add_dynamic_field(table_name text, record_id uuid, field_name text, field_value text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    EXECUTE format('UPDATE %I SET dynamic_fields = COALESCE(dynamic_fields, ''{}''::jsonb) || jsonb_build_object(%L, %L) WHERE id = %L',
                   table_name, field_name, field_value, record_id);
END;
$$;


ALTER FUNCTION public.add_dynamic_field(table_name text, record_id uuid, field_name text, field_value text) OWNER TO postgres;

--
-- Name: add_invoice_dynamic_field(integer, text, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.add_invoice_dynamic_field(p_invoice_id integer, p_field_name text, p_field_value text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE raw_invoices 
    SET dynamic_fields = add_dynamic_field(dynamic_fields, p_field_name, p_field_value)
    WHERE invoice_id = p_invoice_id;
END;
$$;


ALTER FUNCTION public.add_invoice_dynamic_field(p_invoice_id integer, p_field_name text, p_field_value text) OWNER TO postgres;

--
-- Name: add_payment_dynamic_field(integer, text, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.add_payment_dynamic_field(p_payment_id integer, p_field_name text, p_field_value text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE payments 
    SET dynamic_fields = add_dynamic_field(dynamic_fields, p_field_name, p_field_value)
    WHERE payment_id = p_payment_id;
END;
$$;


ALTER FUNCTION public.add_payment_dynamic_field(p_payment_id integer, p_field_name text, p_field_value text) OWNER TO postgres;

--
-- Name: add_po_dynamic_field(integer, text, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.add_po_dynamic_field(p_po_id integer, p_field_name text, p_field_value text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE purchase_orders 
    SET dynamic_fields = add_dynamic_field(dynamic_fields, p_field_name, p_field_value)
    WHERE po_id = p_po_id;
END;
$$;


ALTER FUNCTION public.add_po_dynamic_field(p_po_id integer, p_field_name text, p_field_value text) OWNER TO postgres;

--
-- Name: add_supplier_dynamic_field(integer, text, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.add_supplier_dynamic_field(p_supplier_id integer, p_field_name text, p_field_value text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE suppliers 
    SET dynamic_fields = add_dynamic_field(dynamic_fields, p_field_name, p_field_value)
    WHERE supplier_id = p_supplier_id;
END;
$$;


ALTER FUNCTION public.add_supplier_dynamic_field(p_supplier_id integer, p_field_name text, p_field_value text) OWNER TO postgres;

--
-- Name: auto_fetch_revenue_data(integer, character varying, character varying, jsonb); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.auto_fetch_revenue_data(p_job_order_id integer, p_customer_name character varying DEFAULT NULL::character varying, p_invoice_number character varying DEFAULT NULL::character varying, p_dynamic_fields jsonb DEFAULT NULL::jsonb) RETURNS TABLE(fetched_customer_name character varying, fetched_job_order_id integer, fetched_invoice_number character varying, fetched_product_supplied text, fetched_product_model character varying, fetched_unit_price numeric, fetched_quantity numeric, fetched_total_amount numeric, fetched_currency character varying, merged_dynamic_fields jsonb, fetch_source jsonb)
    LANGUAGE plpgsql
    AS $$
DECLARE
    result_record RECORD;
    source_info JSONB;
    auto_fetched_fields JSONB;
BEGIN
    -- Initialize variables
    source_info := '{}';
    auto_fetched_fields := '{}';
    fetched_job_order_id := p_job_order_id;
    
    -- Fetch customer information from customer_accounts
    SELECT ca.client_name, ca.total_amount, ca.currency, ca.custom_fields
    INTO result_record
    FROM customer_accounts ca
    WHERE ca.job_order_id = p_job_order_id
    AND (p_customer_name IS NULL OR LOWER(ca.client_name) = LOWER(p_customer_name))
    LIMIT 1;
    
    IF FOUND THEN
        fetched_customer_name := result_record.client_name;
        fetched_total_amount := result_record.total_amount;
        fetched_currency := result_record.currency;
        
        -- Merge custom fields from customer accounts
        IF result_record.custom_fields IS NOT NULL THEN
            auto_fetched_fields := auto_fetched_fields || result_record.custom_fields;
        END IF;
        
        source_info := source_info || jsonb_build_object(
            'customer_name', 'customer_accounts',
            'total_amount', 'customer_accounts',
            'currency', 'customer_accounts',
            'customer_custom_fields', 'customer_accounts'
        );
    ELSE
        fetched_customer_name := p_customer_name;
    END IF;
    
    -- Fetch job order information (unit_price, order_quantity) - no dynamic fields
    SELECT jo.unit_price, jo.order_quantity
    INTO result_record
    FROM job_orders jo
    WHERE jo.id = p_job_order_id
    LIMIT 1;
    
    IF FOUND THEN
        fetched_unit_price := result_record.unit_price;
        fetched_quantity := result_record.order_quantity;
        
        source_info := source_info || jsonb_build_object(
            'unit_price', 'job_orders',
            'quantity', 'job_orders'
        );
    END IF;
    
    -- Fetch invoice information if invoice_number is provided
    IF p_invoice_number IS NOT NULL THEN
        SELECT i.invoice_number, i.products_supplied, i.model, i.custom_fields
        INTO result_record
        FROM invoices i
        WHERE i.invoice_number = p_invoice_number
        LIMIT 1;
        
        IF FOUND THEN
            fetched_invoice_number := result_record.invoice_number;
            fetched_product_supplied := result_record.products_supplied;
            fetched_product_model := result_record.model;
            
            -- Merge dynamic fields from invoices if they exist
            IF result_record.custom_fields IS NOT NULL THEN
                auto_fetched_fields := auto_fetched_fields || result_record.custom_fields;
            END IF;
            
            source_info := source_info || jsonb_build_object(
                'invoice_number', 'invoices',
                'product_supplied', 'invoices',
                'product_model', 'invoices',
                'invoice_custom_fields', 'invoices'
            );
        ELSE
            fetched_invoice_number := p_invoice_number;
        END IF;
    ELSE
        -- Try to find invoice by job_order_id if available
        SELECT i.invoice_number, i.products_supplied, i.model, i.custom_fields
        INTO result_record
        FROM invoices i
        INNER JOIN job_orders jo ON jo.id = p_job_order_id
        WHERE i.invoice_number IS NOT NULL
        ORDER BY i.created_at DESC
        LIMIT 1;
        
        IF FOUND THEN
            fetched_invoice_number := result_record.invoice_number;
            fetched_product_supplied := result_record.products_supplied;
            fetched_product_model := result_record.model;
            
            -- Merge dynamic fields from invoices if they exist
            IF result_record.dynamic_fields IS NOT NULL THEN
                auto_fetched_fields := auto_fetched_fields || result_record.dynamic_fields;
            END IF;
            
            source_info := source_info || jsonb_build_object(
                'invoice_number', 'invoices_by_job_order',
                'product_supplied', 'invoices_by_job_order',
                'product_model', 'invoices_by_job_order',
                'invoice_dynamic_fields', 'invoices_by_job_order'
            );
        END IF;
    END IF;
    
    -- Merge user-provided dynamic fields with auto-fetched ones
    -- User-provided fields take precedence over auto-fetched ones
    IF p_dynamic_fields IS NOT NULL THEN
        merged_dynamic_fields := auto_fetched_fields || p_dynamic_fields;
    ELSE
        merged_dynamic_fields := auto_fetched_fields;
    END IF;
    
    fetch_source := source_info;
    
    RETURN NEXT;
END;
$$;


ALTER FUNCTION public.auto_fetch_revenue_data(p_job_order_id integer, p_customer_name character varying, p_invoice_number character varying, p_dynamic_fields jsonb) OWNER TO postgres;

--
-- Name: create_customer_account_from_job_order(integer, character varying, character varying, character varying, text, character varying, character varying, jsonb); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.create_customer_account_from_job_order(p_job_order_id integer, p_contact_email character varying DEFAULT NULL::character varying, p_contact_phone character varying DEFAULT NULL::character varying, p_contact_person character varying DEFAULT NULL::character varying, p_shipping_address text DEFAULT NULL::text, p_currency character varying DEFAULT 'USD'::character varying, p_payment_terms character varying DEFAULT NULL::character varying, p_custom_fields jsonb DEFAULT NULL::jsonb) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_client_name VARCHAR(255);
    v_total_price DECIMAL(15,2);
    v_customer_id INTEGER;
BEGIN
    -- Fetch data from job_orders table
    SELECT client_name, total_price 
    INTO v_client_name, v_total_price
    FROM job_orders 
    WHERE id = p_job_order_id;
    
    -- Check if job order exists
    IF v_client_name IS NULL THEN
        RAISE EXCEPTION 'Job order with ID % not found', p_job_order_id;
    END IF;
    
    -- Insert new customer account
    INSERT INTO customer_accounts (
        client_name, job_order_id, contact_email, contact_phone, 
        contact_person_name, shipping_address, currency, payment_terms,
        total_amount, custom_fields
    ) VALUES (
        v_client_name, p_job_order_id, p_contact_email, p_contact_phone,
        p_contact_person, p_shipping_address, 
        COALESCE(p_currency, 'USD'), p_payment_terms,
        v_total_price, p_custom_fields
    )
    RETURNING id INTO v_customer_id;
    
    RETURN v_customer_id;
END;
$$;


ALTER FUNCTION public.create_customer_account_from_job_order(p_job_order_id integer, p_contact_email character varying, p_contact_phone character varying, p_contact_person character varying, p_shipping_address text, p_currency character varying, p_payment_terms character varying, p_custom_fields jsonb) OWNER TO postgres;

--
-- Name: create_invoice_from_job_order(integer, integer, character varying, numeric, integer, jsonb); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.create_invoice_from_job_order(p_customer_account_id integer, p_job_order_id integer, p_po_reference character varying DEFAULT NULL::character varying, p_tax_percentage numeric DEFAULT 0.00, p_due_days integer DEFAULT 30, p_custom_fields jsonb DEFAULT NULL::jsonb) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_invoice_id INTEGER;
    v_invoice_number VARCHAR(50);
    v_client_name VARCHAR(255);
    v_order_total DECIMAL(15,2);
    v_tax_amount DECIMAL(15,2);
    v_total_amount DECIMAL(15,2);
    v_due_date DATE;
BEGIN
    -- Get client name from customer account
    SELECT client_name INTO v_client_name
    FROM customer_accounts
    WHERE id = p_customer_account_id;
    
    -- Get order total from job order
    SELECT total_price INTO v_order_total
    FROM job_orders
    WHERE id = p_job_order_id;
    
    -- Calculate tax and total
    v_tax_amount := v_order_total * (p_tax_percentage / 100);
    v_total_amount := v_order_total + v_tax_amount;
    
    -- Calculate due date
    v_due_date := CURRENT_DATE + p_due_days;
    
    -- Generate invoice number
    v_invoice_number := 'INV-' || TO_CHAR(CURRENT_DATE, 'YYYY') || '-' || 
                       LPAD(COALESCE((SELECT COUNT(*) + 1 FROM invoices 
                                      WHERE EXTRACT(YEAR FROM invoice_date) = EXTRACT(YEAR FROM CURRENT_DATE)), 1)::TEXT, 6, '0');
    
    -- Insert invoice with correct column names
    INSERT INTO invoices (
        invoice_number,
        customer_account_id,  -- Correct column name
        job_order_id,
        client_name,
        invoice_date,
        due_date,
        po_reference,
        subtotal,
        tax_percentage,
        tax_amount,
        total_amount,
        outstanding_balance,
        payment_status,
        invoice_status,
        custom_fields
    )
    VALUES (
        v_invoice_number,
        p_customer_account_id,  -- Correct parameter
        p_job_order_id,
        v_client_name,
        CURRENT_DATE,
        v_due_date,
        p_po_reference,
        v_order_total,
        p_tax_percentage,
        v_tax_amount,
        v_total_amount,
        v_total_amount,
        'unpaid',
        'draft',
        p_custom_fields
    )
    RETURNING id INTO v_invoice_id;
    
    -- Update order_accounting if it exists
    UPDATE order_accounting
    SET amount_invoiced = amount_invoiced + v_total_amount,
        invoice_status = 'invoiced',
        first_invoice_date = COALESCE(first_invoice_date, CURRENT_DATE)
    WHERE job_order_id = p_job_order_id;
    
    RETURN v_invoice_id;
END;
$$;


ALTER FUNCTION public.create_invoice_from_job_order(p_customer_account_id integer, p_job_order_id integer, p_po_reference character varying, p_tax_percentage numeric, p_due_days integer, p_custom_fields jsonb) OWNER TO postgres;

--
-- Name: generate_barcode(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.generate_barcode() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO barcodes (raw_material_id, barcode_label) 
    VALUES (NEW.raw_material_id, CONCAT('RM-', NEW.raw_material_id, '-', EXTRACT(YEAR FROM CURRENT_DATE)));
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.generate_barcode() OWNER TO postgres;

--
-- Name: get_all_dynamic_field_keys(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.get_all_dynamic_field_keys() RETURNS TABLE(field_key text, usage_count bigint)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT jsonb_object_keys(dynamic_fields) as field_key,
           COUNT(*) as usage_count
    FROM revenues
    WHERE dynamic_fields IS NOT NULL AND jsonb_typeof(dynamic_fields) = 'object'
    GROUP BY jsonb_object_keys(dynamic_fields)
    ORDER BY usage_count DESC, field_key;
END;
$$;


ALTER FUNCTION public.get_all_dynamic_field_keys() OWNER TO postgres;

--
-- Name: populate_supplier_from_inventory(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.populate_supplier_from_inventory() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    supplier_exists INTEGER DEFAULT 0;
    existing_supplier_id INTEGER;
    inv_supplier_name VARCHAR(255);
    inv_material_type VARCHAR(255);
BEGIN
    -- Note: Uncomment and modify when inventory_orders table exists
    /*
    -- Get supplier info from inventory_orders
    SELECT supplier, material_type 
    INTO inv_supplier_name, inv_material_type
    FROM inventory_orders 
    WHERE order_id = NEW.order_id;
    
    -- Check if supplier already exists
    SELECT COUNT(*), MAX(supplier_id)
    INTO supplier_exists, existing_supplier_id
    FROM suppliers 
    WHERE supplier_name = inv_supplier_name;
    
    -- If supplier doesn't exist, create new one
    IF supplier_exists = 0 THEN
        INSERT INTO suppliers (supplier_name, material_type) 
        VALUES (inv_supplier_name, inv_material_type)
        RETURNING supplier_id INTO NEW.supplier_id;
    ELSE
        NEW.supplier_id := existing_supplier_id;
    END IF;
    */
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.populate_supplier_from_inventory() OWNER TO postgres;

--
-- Name: record_receipt(integer, integer, numeric, character varying, character varying, integer, character varying, character varying, character varying, text, jsonb); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.record_receipt(p_customer_account_id integer, p_job_order_id integer, p_amount_received numeric, p_payment_method character varying, p_bank_or_cash character varying, p_invoice_id integer DEFAULT NULL::integer, p_transaction_reference character varying DEFAULT NULL::character varying, p_bank_name character varying DEFAULT NULL::character varying, p_check_number character varying DEFAULT NULL::character varying, p_notes text DEFAULT NULL::text, p_custom_fields jsonb DEFAULT NULL::jsonb) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_receipt_id INTEGER;
    v_receipt_number VARCHAR(50);
    v_client_name VARCHAR(255);
BEGIN
    -- Get client name from customer account
    SELECT client_name INTO v_client_name
    FROM customer_accounts
    WHERE id = p_customer_account_id;
    
    IF v_client_name IS NULL THEN
        RAISE EXCEPTION 'Customer account % not found', p_customer_account_id;
    END IF;
    
    -- Generate receipt number
    v_receipt_number := 'RCP-' || TO_CHAR(CURRENT_DATE, 'YYYY') || '-' || 
                       LPAD(COALESCE((SELECT COUNT(*) + 1 FROM receipts 
                                      WHERE EXTRACT(YEAR FROM payment_date) = EXTRACT(YEAR FROM CURRENT_DATE)), 1)::TEXT, 6, '0');
    
    -- Insert receipt with client_name
    INSERT INTO receipts (
        receipt_number,
        customer_account_id,
        job_order_id,
        client_name,
        amount_received,
        payment_date,
        payment_method,
        bank_or_cash,
        invoice_id,
        transaction_reference,
        bank_name,
        check_number,
        notes,
        custom_fields
    )
    VALUES (
        v_receipt_number,
        p_customer_account_id,
        p_job_order_id,
        v_client_name,
        p_amount_received,
        CURRENT_DATE,
        p_payment_method,
        p_bank_or_cash,
        p_invoice_id,
        p_transaction_reference,
        p_bank_name,
        p_check_number,
        p_notes,
        p_custom_fields
    )
    RETURNING id INTO v_receipt_id;
    
    -- Update customer account outstanding balance
    UPDATE customer_accounts
    SET outstanding_balance = GREATEST(0, outstanding_balance - p_amount_received)
    WHERE id = p_customer_account_id;
    
    -- Update order_accounting if exists
    UPDATE order_accounting
    SET amount_paid = COALESCE(amount_paid, 0) + p_amount_received,
        outstanding_balance = GREATEST(0, COALESCE(outstanding_balance, 0) - p_amount_received),
        payment_status = CASE 
            WHEN COALESCE(outstanding_balance, 0) - p_amount_received <= 0 THEN 'paid'
            ELSE 'partial'
        END,
        last_payment_date = CURRENT_DATE
    WHERE customer_account_id = p_customer_account_id 
    AND job_order_id = p_job_order_id;
    
    -- Update invoice if linked
    IF p_invoice_id IS NOT NULL THEN
        UPDATE invoices
        SET amount_paid = COALESCE(amount_paid, 0) + p_amount_received,
            outstanding_balance = GREATEST(0, COALESCE(outstanding_balance, 0) - p_amount_received),
            payment_status = CASE 
                WHEN COALESCE(outstanding_balance, 0) - p_amount_received <= 0 THEN 'paid'
                ELSE 'partial'
            END
        WHERE id = p_invoice_id;
    END IF;
    
    RETURN v_receipt_id;
END;
$$;


ALTER FUNCTION public.record_receipt(p_customer_account_id integer, p_job_order_id integer, p_amount_received numeric, p_payment_method character varying, p_bank_or_cash character varying, p_invoice_id integer, p_transaction_reference character varying, p_bank_name character varying, p_check_number character varying, p_notes text, p_custom_fields jsonb) OWNER TO postgres;

--
-- Name: record_receipt(integer, integer, numeric, public.payment_method_enum, public.bank_or_cash_enum, integer, character varying, character varying, character varying, text, jsonb); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.record_receipt(p_customer_account_id integer, p_job_order_id integer, p_amount_received numeric, p_payment_method public.payment_method_enum, p_bank_or_cash public.bank_or_cash_enum, p_invoice_id integer DEFAULT NULL::integer, p_transaction_reference character varying DEFAULT NULL::character varying, p_bank_name character varying DEFAULT NULL::character varying, p_check_number character varying DEFAULT NULL::character varying, p_notes text DEFAULT NULL::text, p_custom_fields jsonb DEFAULT NULL::jsonb) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_receipt_id INTEGER;
    v_receipt_number VARCHAR(100);
BEGIN
    -- Generate receipt number
    v_receipt_number := 'RCP-' || TO_CHAR(CURRENT_DATE, 'YYYY') || '-' || 
                       LPAD(nextval('receipts_id_seq')::TEXT, 6, '0');
    
    -- Insert new receipt
    INSERT INTO receipts (
        customer_account_id, job_order_id, invoice_id, amount_received, payment_method,
        bank_or_cash, transaction_reference, bank_name, check_number,
        receipt_number, notes, custom_fields
    ) VALUES (
        p_customer_account_id, p_job_order_id, p_invoice_id, p_amount_received, p_payment_method,
        p_bank_or_cash, p_transaction_reference, p_bank_name, p_check_number,
        v_receipt_number, p_notes, p_custom_fields
    )
    RETURNING id INTO v_receipt_id;
    
    RETURN v_receipt_id;
END;
$$;


ALTER FUNCTION public.record_receipt(p_customer_account_id integer, p_job_order_id integer, p_amount_received numeric, p_payment_method public.payment_method_enum, p_bank_or_cash public.bank_or_cash_enum, p_invoice_id integer, p_transaction_reference character varying, p_bank_name character varying, p_check_number character varying, p_notes text, p_custom_fields jsonb) OWNER TO postgres;

--
-- Name: refresh_revenue_costs(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.refresh_revenue_costs(p_job_order_id integer DEFAULT NULL::integer) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    updated_count INTEGER := 0;
BEGIN
    IF p_job_order_id IS NOT NULL THEN
        -- Update specific job order
        UPDATE revenues 
        SET updated_at = CURRENT_TIMESTAMP
        WHERE job_order_id = p_job_order_id;
        
        GET DIAGNOSTICS updated_count = ROW_COUNT;
    ELSE
        -- Update all records
        UPDATE revenues 
        SET updated_at = CURRENT_TIMESTAMP;
        
        GET DIAGNOSTICS updated_count = ROW_COUNT;
    END IF;
    
    RETURN updated_count;
END;
$$;


ALTER FUNCTION public.refresh_revenue_costs(p_job_order_id integer) OWNER TO postgres;

--
-- Name: release_machines_on_order_completion(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.release_machines_on_order_completion() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Only proceed if the status changed to 'completed'
    IF NEW.status = 'completed' AND 
       (OLD.status != 'completed' OR OLD.status IS NULL) THEN
        
        -- Update machines that are linked to this order
        UPDATE machines
        SET status = 'available',
            current_job_order = NULL,
            updated_at = NOW() AT TIME ZONE 'UTC'
        WHERE current_job_order = NEW.id
          AND status = 'in_use';
        
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.release_machines_on_order_completion() OWNER TO postgres;

--
-- Name: remove_dynamic_field(jsonb, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.remove_dynamic_field(existing_json jsonb, field_name text) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF existing_json IS NULL THEN
        RETURN NULL;
    ELSE
        RETURN existing_json - field_name;
    END IF;
END;
$$;


ALTER FUNCTION public.remove_dynamic_field(existing_json jsonb, field_name text) OWNER TO postgres;

--
-- Name: remove_dynamic_field(text, uuid, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.remove_dynamic_field(table_name text, record_id uuid, field_name text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    EXECUTE format('UPDATE %I SET dynamic_fields = dynamic_fields - %L WHERE id = %L',
                   table_name, field_name, record_id);
END;
$$;


ALTER FUNCTION public.remove_dynamic_field(table_name text, record_id uuid, field_name text) OWNER TO postgres;

--
-- Name: search_revenues_by_dynamic_field(text, text, boolean); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.search_revenues_by_dynamic_field(field_name text, field_value text, exact_match boolean DEFAULT true) RETURNS TABLE(id integer, customer_name character varying, job_order_id integer, dynamic_field_value text, net_revenue numeric, net_profit numeric)
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF exact_match THEN
        RETURN QUERY
        SELECT r.id, r.customer_name, r.job_order_id, 
               (r.dynamic_fields->>field_name) as dynamic_field_value,
               r.net_revenue, r.net_profit
        FROM revenues r
        WHERE r.dynamic_fields->>field_name = field_value;
    ELSE
        RETURN QUERY
        SELECT r.id, r.customer_name, r.job_order_id,
               (r.dynamic_fields->>field_name) as dynamic_field_value,
               r.net_revenue, r.net_profit
        FROM revenues r
        WHERE r.dynamic_fields->>field_name ILIKE '%' || field_value || '%';
    END IF;
END;
$$;


ALTER FUNCTION public.search_revenues_by_dynamic_field(field_name text, field_value text, exact_match boolean) OWNER TO postgres;

--
-- Name: sync_customer_accounts_revenue(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.sync_customer_accounts_revenue() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update amount_received in customer_accounts based on revenues
    UPDATE customer_accounts 
    SET amount_received = (
        SELECT COALESCE(SUM(net_revenue), 0)
        FROM revenues 
        WHERE job_order_id = NEW.job_order_id
    ),
    updated_at = CURRENT_TIMESTAMP
    WHERE job_order_id = NEW.job_order_id;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.sync_customer_accounts_revenue() OWNER TO postgres;

--
-- Name: trg_job_orders_completed(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.trg_job_orders_completed() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.remaining_target_g = 0
       AND NEW.status = 'in_progress'          -- only once
       AND (OLD.remaining_target_g IS NULL OR OLD.remaining_target_g <> 0) THEN
        NEW.status       := 'completed';
        NEW.completed_at := NOW();
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.trg_job_orders_completed() OWNER TO postgres;

--
-- Name: update_customer_balance(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_customer_balance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update the customer account balance based on receipts
    UPDATE customer_accounts 
    SET amount_received = (
        SELECT COALESCE(SUM(amount_received), 0) 
        FROM receipts 
        WHERE client_id = COALESCE(NEW.client_id, OLD.client_id)
    )
    WHERE id = COALESCE(NEW.client_id, OLD.client_id);
    
    RETURN COALESCE(NEW, OLD);
END;
$$;


ALTER FUNCTION public.update_customer_balance() OWNER TO postgres;

--
-- Name: update_daily_waste_summary(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_daily_waste_summary() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO daily_waste_summary (machine_id, waste_date, total_waste_g, total_orders)
    VALUES (NEW.machine_id, NEW.waste_date, NEW.waste_amount_g, 1)
    ON CONFLICT (machine_id, waste_date) 
    DO UPDATE SET 
        total_waste_g = daily_waste_summary.total_waste_g + NEW.waste_amount_g,
        total_orders = daily_waste_summary.total_orders + 
            CASE WHEN EXISTS (
                SELECT 1 FROM machine_waste 
                WHERE machine_id = NEW.machine_id 
                AND job_order_id = NEW.job_order_id 
                AND waste_date = NEW.waste_date
                AND index_number != NEW.index_number -- Only count as new order if this is a different index
            ) THEN 0 ELSE 1 END;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_daily_waste_summary() OWNER TO postgres;

--
-- Name: update_invoice_payment_status(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_invoice_payment_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    invoice_total DECIMAL(15,2);
    total_paid DECIMAL(15,2);
BEGIN
    IF NEW.invoice_id IS NOT NULL THEN
        -- Get invoice total
        SELECT total_amount INTO invoice_total 
        FROM invoices 
        WHERE id = NEW.invoice_id;
        
        -- Calculate total paid for this invoice
        SELECT COALESCE(SUM(amount_received), 0) INTO total_paid
        FROM receipts 
        WHERE invoice_id = NEW.invoice_id;
        
        -- Update invoice payment status
        UPDATE invoices 
        SET payment_status = CASE 
            WHEN total_paid >= invoice_total THEN 'paid'::payment_status_enum
            WHEN total_paid > 0 THEN 'partial'::payment_status_enum
            ELSE 'unpaid'::payment_status_enum
        END
        WHERE id = NEW.invoice_id;
    END IF;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_invoice_payment_status() OWNER TO postgres;

--
-- Name: update_invoice_status_after_payment(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_invoice_status_after_payment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    total_paid DECIMAL(12,2);
    invoice_total DECIMAL(12,2);
BEGIN
    -- Calculate total payments for this invoice
    SELECT COALESCE(SUM(payment_amount), 0) INTO total_paid
    FROM payments 
    WHERE invoice_id = NEW.invoice_id AND payment_status = 'completed';
    
    -- Get invoice total
    SELECT total_amount INTO invoice_total
    FROM raw_invoices 
    WHERE invoice_id = NEW.invoice_id;
    
    -- Update invoice status based on payment
    IF total_paid >= invoice_total THEN
        UPDATE raw_invoices 
        SET invoice_status = 'paid', updated_date = CURRENT_TIMESTAMP
        WHERE invoice_id = NEW.invoice_id;
    END IF;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_invoice_status_after_payment() OWNER TO postgres;

--
-- Name: update_outstanding_balance(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_outstanding_balance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Update outstanding balance for the supplier
    UPDATE supplier_accounts 
    SET outstanding_balance = (
        COALESCE((
            SELECT SUM(total_amount) 
            FROM raw_invoices 
            WHERE supplier_id = NEW.supplier_id AND status != 'paid'
        ), 0) - 
        COALESCE((
            SELECT SUM(amount_paid) 
            FROM payments 
            WHERE supplier_id = NEW.supplier_id
        ), 0)
    ),
    updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.supplier_id;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_outstanding_balance() OWNER TO postgres;

--
-- Name: update_recycling_line_timestamp(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_recycling_line_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    
    -- Automatically calculate recycling time when packaging is completed
    IF NEW.packaging_process_timestamp IS NOT NULL AND OLD.packaging_process_timestamp IS NULL THEN
        NEW.calculated_recycling_time = NEW.packaging_process_timestamp - NEW.timestamp_start;
        NEW.status = 'COMPLETED';
    END IF;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_recycling_line_timestamp() OWNER TO postgres;

--
-- Name: update_revenue_costs(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_revenue_costs() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- Calculate raw materials cost for this job order
    SELECT COALESCE(SUM(costs), 0) INTO NEW.raw_materials_cost
    FROM raw_materials_costs 
    WHERE job_order_id = NEW.job_order_id;
    
    -- Calculate operational cost for this job order
    SELECT COALESCE(SUM(costs), 0) INTO NEW.operational_cost
    FROM operational_costs 
    WHERE job_order_id = NEW.job_order_id;
    
    -- Calculate general cost for this job order
    SELECT COALESCE(SUM(costs), 0) INTO NEW.general_cost
    FROM general_costs 
    WHERE job_order_id = NEW.job_order_id;
    
    -- Calculate depreciation cost for this job order
    SELECT COALESCE(SUM(costs), 0) INTO NEW.depreciation_cost
    FROM depreciation_costs 
    WHERE job_order_id = NEW.job_order_id;
    
    -- Calculate unexpected cost for this job order
    SELECT COALESCE(SUM(costs), 0) INTO NEW.unexpected_cost
    FROM unexpected_costs 
    WHERE job_order_id = NEW.job_order_id;
    
    -- Update the updated_at timestamp
    NEW.updated_at = CURRENT_TIMESTAMP;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_revenue_costs() OWNER TO postgres;

--
-- Name: update_revenue_dynamic_fields(integer, jsonb, boolean); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_revenue_dynamic_fields(p_revenue_id integer, p_new_fields jsonb, p_merge_mode boolean DEFAULT true) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
DECLARE
    updated_fields JSONB;
BEGIN
    IF p_merge_mode THEN
        -- Merge new fields with existing ones
        SELECT CASE 
            WHEN dynamic_fields IS NULL THEN p_new_fields
            ELSE dynamic_fields || p_new_fields
        END
        INTO updated_fields
        FROM revenues
        WHERE id = p_revenue_id;
    ELSE
        -- Replace all dynamic fields
        updated_fields := p_new_fields;
    END IF;
    
    UPDATE revenues
    SET dynamic_fields = updated_fields,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_revenue_id;
    
    RETURN FOUND;
END;
$$;


ALTER FUNCTION public.update_revenue_dynamic_fields(p_revenue_id integer, p_new_fields jsonb, p_merge_mode boolean) OWNER TO postgres;

--
-- Name: update_supplier_accounts_updated_at(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_supplier_accounts_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_supplier_accounts_updated_at() OWNER TO postgres;

--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_updated_at_column() OWNER TO postgres;

--
-- Name: update_updated_date(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_updated_date() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_date = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_updated_date() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: inv_kpi_history; Type: TABLE; Schema: analytics; Owner: postgres
--

CREATE TABLE analytics.inv_kpi_history (
    snapshot_date date NOT NULL,
    material_type text NOT NULL,
    on_hand_kg numeric,
    kg_per_batch numeric,
    batches integer,
    avg_density numeric,
    forecast_accuracy numeric,
    days_of_supply integer,
    reorder_point numeric
);


ALTER TABLE analytics.inv_kpi_history OWNER TO postgres;

--
-- Name: inv_risk_assessment; Type: TABLE; Schema: analytics; Owner: postgres
--

CREATE TABLE analytics.inv_risk_assessment (
    material_type text NOT NULL,
    assessment_date date NOT NULL,
    stockout_risk numeric,
    excess_stock_risk numeric,
    aging_risk numeric,
    cost_opportunity numeric
);


ALTER TABLE analytics.inv_risk_assessment OWNER TO postgres;

--
-- Name: inv_seasonality; Type: TABLE; Schema: analytics; Owner: postgres
--

CREATE TABLE analytics.inv_seasonality (
    material_type text NOT NULL,
    month integer NOT NULL,
    seasonal_factor numeric,
    confidence_level numeric
);


ALTER TABLE analytics.inv_seasonality OWNER TO postgres;

--
-- Name: attendance; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.attendance (
    id integer NOT NULL,
    employee_id integer,
    "timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.attendance OWNER TO postgres;

--
-- Name: attendance_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.attendance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.attendance_id_seq OWNER TO postgres;

--
-- Name: attendance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.attendance_id_seq OWNED BY public.attendance.id;


--
-- Name: comp_inventory; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.comp_inventory (
    id integer NOT NULL,
    material_name text NOT NULL,
    type text NOT NULL,
    quantity integer NOT NULL,
    weight double precision NOT NULL,
    supplier text NOT NULL,
    serial_number text NOT NULL,
    date_added timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    unit_price numeric(10,2),
    total_price numeric(10,2)
);


ALTER TABLE public.comp_inventory OWNER TO postgres;

--
-- Name: comp_inventory_attributes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.comp_inventory_attributes (
    id integer NOT NULL,
    comp_inventory_id integer,
    key text NOT NULL,
    value text NOT NULL
);


ALTER TABLE public.comp_inventory_attributes OWNER TO postgres;

--
-- Name: comp_inventory_attributes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.comp_inventory_attributes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.comp_inventory_attributes_id_seq OWNER TO postgres;

--
-- Name: comp_inventory_attributes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.comp_inventory_attributes_id_seq OWNED BY public.comp_inventory_attributes.id;


--
-- Name: comp_inventory_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.comp_inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.comp_inventory_id_seq OWNER TO postgres;

--
-- Name: comp_inventory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.comp_inventory_id_seq OWNED BY public.comp_inventory.id;


--
-- Name: custom_field_definitions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.custom_field_definitions (
    id integer NOT NULL,
    table_name character varying(100) NOT NULL,
    field_name character varying(100) NOT NULL,
    field_type public.field_type_enum NOT NULL,
    field_label character varying(255) NOT NULL,
    field_options jsonb,
    is_required boolean DEFAULT false,
    default_value text,
    validation_rules jsonb,
    display_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.custom_field_definitions OWNER TO postgres;

--
-- Name: custom_field_definitions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.custom_field_definitions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.custom_field_definitions_id_seq OWNER TO postgres;

--
-- Name: custom_field_definitions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.custom_field_definitions_id_seq OWNED BY public.custom_field_definitions.id;


--
-- Name: customer_accounts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customer_accounts (
    id integer NOT NULL,
    client_name character varying(255) NOT NULL,
    contact_email character varying(255),
    contact_phone character varying(50),
    contact_person_name character varying(255),
    company_address text,
    billing_address text,
    shipping_address text,
    payment_terms character varying(100) DEFAULT 'Net 30'::character varying,
    currency character varying(10) DEFAULT 'USD'::character varying,
    tax_id character varying(100),
    industry character varying(100),
    total_orders_count integer DEFAULT 0,
    total_amount_due numeric(15,2) DEFAULT 0.00,
    total_amount_paid numeric(15,2) DEFAULT 0.00,
    outstanding_balance numeric(15,2) DEFAULT 0.00,
    credit_limit numeric(15,2) DEFAULT 0.00,
    account_status character varying(20) DEFAULT 'active'::character varying,
    last_order_date timestamp without time zone,
    last_payment_date timestamp without time zone,
    last_invoice_date timestamp without time zone,
    custom_fields jsonb,
    notes text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.customer_accounts OWNER TO postgres;

--
-- Name: customer_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.customer_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.customer_accounts_id_seq OWNER TO postgres;

--
-- Name: customer_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.customer_accounts_id_seq OWNED BY public.customer_accounts.id;


--
-- Name: invoices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.invoices (
    id integer NOT NULL,
    invoice_number character varying(50) NOT NULL,
    customer_account_id integer NOT NULL,
    job_order_id integer,
    client_name character varying(255) NOT NULL,
    invoice_date date DEFAULT CURRENT_DATE,
    due_date date NOT NULL,
    po_reference character varying(100),
    subtotal numeric(15,2) NOT NULL,
    tax_percentage numeric(5,2) DEFAULT 0.00,
    tax_amount numeric(15,2) DEFAULT 0.00,
    total_amount numeric(15,2) NOT NULL,
    amount_paid numeric(15,2) DEFAULT 0.00,
    outstanding_balance numeric(15,2) NOT NULL,
    payment_status character varying(20) DEFAULT 'unpaid'::character varying,
    invoice_status character varying(20) DEFAULT 'draft'::character varying,
    notes text,
    custom_fields jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.invoices OWNER TO postgres;

--
-- Name: job_orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_orders (
    id integer NOT NULL,
    order_id character varying(50) NOT NULL,
    client_name character varying(100) NOT NULL,
    product character varying(20) NOT NULL,
    model character varying(50),
    raw_degree character varying(20),
    order_quantity integer NOT NULL,
    length_cm double precision DEFAULT 0,
    width_cm double precision DEFAULT 0,
    micron_mm double precision DEFAULT 0,
    density double precision DEFAULT 0,
    flap_cm double precision DEFAULT 0,
    gusset1_cm double precision DEFAULT 0,
    gusset2_cm double precision DEFAULT 0,
    unit_weight double precision DEFAULT 0,
    stretch_quantity integer DEFAULT 0,
    target_weight_no_waste double precision DEFAULT 0,
    target_weight_with_waste double precision DEFAULT 0,
    assigned_date timestamp with time zone DEFAULT now(),
    operator_id integer,
    machine_type character varying(50),
    machine_id character varying(50),
    status text DEFAULT 'pending'::text,
    start_time timestamp with time zone,
    remaining_target_g integer DEFAULT 0,
    completed_at timestamp without time zone,
    completed_weight double precision DEFAULT 0,
    total_waste_g integer DEFAULT 0,
    unit_price numeric(10,2),
    total_price numeric(10,2),
    notes text,
    customer_account_id integer,
    accounting_status character varying(20) DEFAULT 'pending'::character varying,
    progress numeric(5,2) DEFAULT 0.00,
    CONSTRAINT job_orders_remaining_nonneg CHECK ((remaining_target_g >= 0))
);


ALTER TABLE public.job_orders OWNER TO postgres;

--
-- Name: receipts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.receipts (
    id integer NOT NULL,
    receipt_number character varying(50) NOT NULL,
    customer_account_id integer NOT NULL,
    job_order_id integer,
    invoice_id integer,
    client_name character varying(255) NOT NULL,
    amount_received numeric(15,2) NOT NULL,
    payment_date date DEFAULT CURRENT_DATE,
    payment_method character varying(50) NOT NULL,
    bank_or_cash character varying(10) NOT NULL,
    transaction_reference character varying(100),
    bank_name character varying(100),
    check_number character varying(50),
    allocated_to_order boolean DEFAULT false,
    allocated_to_invoice boolean DEFAULT false,
    notes text,
    custom_fields jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.receipts OWNER TO postgres;

--
-- Name: customer_summary; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.customer_summary AS
 SELECT ca.id,
    ca.client_name,
    ca.contact_email,
    ca.contact_phone,
    ca.account_status,
    count(DISTINCT jo.id) AS total_orders,
    COALESCE(sum(jo.total_price), (0)::numeric) AS total_order_value,
    COALESCE(sum(i.total_amount), (0)::numeric) AS total_invoiced,
    COALESCE(sum(r.amount_received), (0)::numeric) AS total_received,
    (COALESCE(sum(i.total_amount), (0)::numeric) - COALESCE(sum(r.amount_received), (0)::numeric)) AS current_balance,
    max(jo.assigned_date) AS last_order_date,
    max(r.payment_date) AS last_payment_date,
    max(i.invoice_date) AS last_invoice_date
   FROM (((public.customer_accounts ca
     LEFT JOIN public.job_orders jo ON ((ca.id = jo.customer_account_id)))
     LEFT JOIN public.invoices i ON ((ca.id = i.customer_account_id)))
     LEFT JOIN public.receipts r ON ((ca.id = r.customer_account_id)))
  GROUP BY ca.id, ca.client_name, ca.contact_email, ca.contact_phone, ca.account_status;


ALTER VIEW public.customer_summary OWNER TO postgres;

--
-- Name: daily_waste_summary; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.daily_waste_summary (
    id integer NOT NULL,
    machine_id character varying(50) NOT NULL,
    waste_date date NOT NULL,
    total_waste_g numeric(12,2) DEFAULT 0 NOT NULL,
    total_orders integer DEFAULT 0 NOT NULL,
    avg_waste_per_order_g numeric(10,2) GENERATED ALWAYS AS (
CASE
    WHEN (total_orders > 0) THEN (total_waste_g / (total_orders)::numeric)
    ELSE (0)::numeric
END) STORED
);


ALTER TABLE public.daily_waste_summary OWNER TO postgres;

--
-- Name: daily_waste_summary_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.daily_waste_summary_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.daily_waste_summary_id_seq OWNER TO postgres;

--
-- Name: daily_waste_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.daily_waste_summary_id_seq OWNED BY public.daily_waste_summary.id;


--
-- Name: depreciation_costs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.depreciation_costs (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    cost numeric(15,2) NOT NULL,
    quantity integer,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    type character varying(100),
    dynamic_fields jsonb,
    submission_date date DEFAULT CURRENT_DATE NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.depreciation_costs OWNER TO postgres;

--
-- Name: depreciation_costs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.depreciation_costs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.depreciation_costs_id_seq OWNER TO postgres;

--
-- Name: depreciation_costs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.depreciation_costs_id_seq OWNED BY public.depreciation_costs.id;


--
-- Name: employees; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.employees (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    password text NOT NULL,
    role character varying(50) NOT NULL,
    barcode character varying(255),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(20) DEFAULT 'available'::character varying NOT NULL,
    current_job_order integer,
    CONSTRAINT employees_role_check CHECK (((role)::text = ANY ((ARRAY['Admin'::character varying, 'Manager'::character varying, 'Operator'::character varying])::text[])))
);


ALTER TABLE public.employees OWNER TO postgres;

--
-- Name: employees_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.employees_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.employees_id_seq OWNER TO postgres;

--
-- Name: employees_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.employees_id_seq OWNED BY public.employees.id;


--
-- Name: general_costs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.general_costs (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    cost numeric(15,2) NOT NULL,
    quantity integer,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    type character varying(100),
    dynamic_fields jsonb,
    submission_date date DEFAULT CURRENT_DATE NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.general_costs OWNER TO postgres;

--
-- Name: general_costs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.general_costs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.general_costs_id_seq OWNER TO postgres;

--
-- Name: general_costs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.general_costs_id_seq OWNED BY public.general_costs.id;


--
-- Name: inventory; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory (
    id integer NOT NULL,
    category character varying(50),
    material_type character varying(100) NOT NULL,
    weight numeric(10,2) DEFAULT 0.00,
    quantity integer NOT NULL,
    supplier character varying(255),
    received_date date DEFAULT CURRENT_DATE,
    group_id character varying(255),
    barcode character varying(255),
    density double precision,
    grade character varying(100),
    color character varying(100),
    kind text,
    status character varying(20) DEFAULT 'available'::character varying NOT NULL,
    job_order_id integer,
    cost_per_kg numeric,
    order_date date,
    unit_price numeric(10,2),
    total_price numeric(10,2),
    CONSTRAINT inventory_category_check CHECK (((category)::text = ANY ((ARRAY['1st Degree'::character varying, '2nd Degree'::character varying])::text[])))
);


ALTER TABLE public.inventory OWNER TO postgres;

--
-- Name: inventory_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.inventory_id_seq OWNER TO postgres;

--
-- Name: inventory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.inventory_id_seq OWNED BY public.inventory.id;


--
-- Name: inventory_orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory_orders (
    id integer NOT NULL,
    group_id character varying(50) NOT NULL,
    received_date date NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    quantity integer NOT NULL,
    total_price numeric(12,2) NOT NULL,
    supplier character varying(255) NOT NULL,
    category character varying(50) NOT NULL,
    material_type character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT inventory_orders_quantity_check CHECK ((quantity > 0)),
    CONSTRAINT inventory_orders_total_price_check CHECK ((total_price > (0)::numeric)),
    CONSTRAINT inventory_orders_unit_price_check CHECK ((unit_price > (0)::numeric))
);


ALTER TABLE public.inventory_orders OWNER TO postgres;

--
-- Name: inventory_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.inventory_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.inventory_orders_id_seq OWNER TO postgres;

--
-- Name: inventory_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.inventory_orders_id_seq OWNED BY public.inventory_orders.id;


--
-- Name: invoices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.invoices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.invoices_id_seq OWNER TO postgres;

--
-- Name: invoices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.invoices_id_seq OWNED BY public.invoices.id;


--
-- Name: job_order_bags; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_bags (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    bag_size character varying(50) NOT NULL,
    quantity integer NOT NULL
);


ALTER TABLE public.job_order_bags OWNER TO postgres;

--
-- Name: job_order_bags_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_bags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_bags_id_seq OWNER TO postgres;

--
-- Name: job_order_bags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_bags_id_seq OWNED BY public.job_order_bags.id;


--
-- Name: job_order_cardboards; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_cardboards (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    size character varying(50) NOT NULL,
    quantity integer NOT NULL
);


ALTER TABLE public.job_order_cardboards OWNER TO postgres;

--
-- Name: job_order_cardboards_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_cardboards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_cardboards_id_seq OWNER TO postgres;

--
-- Name: job_order_cardboards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_cardboards_id_seq OWNED BY public.job_order_cardboards.id;


--
-- Name: job_order_clips; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_clips (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    clip_type character varying(50) NOT NULL,
    quantity integer NOT NULL,
    weight double precision DEFAULT 0
);


ALTER TABLE public.job_order_clips OWNER TO postgres;

--
-- Name: job_order_clips_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_clips_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_clips_id_seq OWNER TO postgres;

--
-- Name: job_order_clips_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_clips_id_seq OWNED BY public.job_order_clips.id;


--
-- Name: job_order_component_attributes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_component_attributes (
    id integer NOT NULL,
    job_order_component_id integer,
    key text NOT NULL,
    value text NOT NULL,
    job_order_id integer
);


ALTER TABLE public.job_order_component_attributes OWNER TO postgres;

--
-- Name: job_order_component_attributes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_component_attributes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_component_attributes_id_seq OWNER TO postgres;

--
-- Name: job_order_component_attributes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_component_attributes_id_seq OWNED BY public.job_order_component_attributes.id;


--
-- Name: job_order_components; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_components (
    id integer NOT NULL,
    job_order_id integer,
    material_name text NOT NULL,
    type text NOT NULL,
    quantity numeric(12,2) DEFAULT 0,
    deducted boolean DEFAULT false
);


ALTER TABLE public.job_order_components OWNER TO postgres;

--
-- Name: job_order_components_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_components_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_components_id_seq OWNER TO postgres;

--
-- Name: job_order_components_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_components_id_seq OWNED BY public.job_order_components.id;


--
-- Name: job_order_inks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_inks (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    color character varying(50) NOT NULL,
    liters double precision NOT NULL
);


ALTER TABLE public.job_order_inks OWNER TO postgres;

--
-- Name: job_order_inks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_inks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_inks_id_seq OWNER TO postgres;

--
-- Name: job_order_inks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_inks_id_seq OWNED BY public.job_order_inks.id;


--
-- Name: job_order_machines; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_machines (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    machine_type character varying(50) NOT NULL,
    machine_id character varying(50) NOT NULL
);


ALTER TABLE public.job_order_machines OWNER TO postgres;

--
-- Name: job_order_machines_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_machines_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_machines_id_seq OWNER TO postgres;

--
-- Name: job_order_machines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_machines_id_seq OWNED BY public.job_order_machines.id;


--
-- Name: job_order_materials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_materials (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    material_type character varying(100) NOT NULL,
    percentage double precision NOT NULL,
    calculated_weight double precision NOT NULL,
    degree character varying(20)
);


ALTER TABLE public.job_order_materials OWNER TO postgres;

--
-- Name: job_order_materials_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_materials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_materials_id_seq OWNER TO postgres;

--
-- Name: job_order_materials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_materials_id_seq OWNED BY public.job_order_materials.id;


--
-- Name: job_order_sizers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_sizers (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    size_label character varying(20) NOT NULL,
    quantity integer NOT NULL
);


ALTER TABLE public.job_order_sizers OWNER TO postgres;

--
-- Name: job_order_sizers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_sizers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_sizers_id_seq OWNER TO postgres;

--
-- Name: job_order_sizers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_sizers_id_seq OWNED BY public.job_order_sizers.id;


--
-- Name: job_order_solvents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_solvents (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    color character varying(50) NOT NULL,
    liters double precision NOT NULL
);


ALTER TABLE public.job_order_solvents OWNER TO postgres;

--
-- Name: job_order_solvents_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_solvents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_solvents_id_seq OWNER TO postgres;

--
-- Name: job_order_solvents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_solvents_id_seq OWNED BY public.job_order_solvents.id;


--
-- Name: job_order_tapes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_order_tapes (
    id integer NOT NULL,
    job_order_id integer NOT NULL,
    tape_size character varying(50) NOT NULL,
    quantity integer NOT NULL
);


ALTER TABLE public.job_order_tapes OWNER TO postgres;

--
-- Name: job_order_tapes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_order_tapes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_order_tapes_id_seq OWNER TO postgres;

--
-- Name: job_order_tapes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_order_tapes_id_seq OWNED BY public.job_order_tapes.id;


--
-- Name: job_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_orders_id_seq OWNER TO postgres;

--
-- Name: job_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_orders_id_seq OWNED BY public.job_orders.id;


--
-- Name: machine_production_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.machine_production_history (
    id integer NOT NULL,
    machine_id character varying(20) NOT NULL,
    order_id integer NOT NULL,
    roll_index integer NOT NULL,
    stage character varying(20) NOT NULL,
    production_weight_g integer,
    waste_weight_g integer,
    recorded_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.machine_production_history OWNER TO postgres;

--
-- Name: machine_production_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.machine_production_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.machine_production_history_id_seq OWNER TO postgres;

--
-- Name: machine_production_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.machine_production_history_id_seq OWNED BY public.machine_production_history.id;


--
-- Name: machine_production_history_ph; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.machine_production_history_ph (
    id integer NOT NULL,
    machine_id character varying(20) NOT NULL,
    order_id integer NOT NULL,
    batch_index integer NOT NULL,
    stage character varying(20) NOT NULL,
    production_weight_g integer,
    waste_weight_g integer,
    recorded_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.machine_production_history_ph OWNER TO postgres;

--
-- Name: machine_production_history_ph_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.machine_production_history_ph_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.machine_production_history_ph_id_seq OWNER TO postgres;

--
-- Name: machine_production_history_ph_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.machine_production_history_ph_id_seq OWNED BY public.machine_production_history_ph.id;


--
-- Name: machine_waste; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.machine_waste (
    id integer NOT NULL,
    machine_id character varying(50) NOT NULL,
    job_order_id integer NOT NULL,
    waste_amount_g numeric(10,2) NOT NULL,
    waste_type character varying(50) NOT NULL,
    waste_date date NOT NULL,
    waste_timestamp timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    recorded_by integer,
    index_number integer DEFAULT 1 NOT NULL
);


ALTER TABLE public.machine_waste OWNER TO postgres;

--
-- Name: machine_waste_backup; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.machine_waste_backup (
    id integer,
    machine_id character varying(50),
    job_order_id integer,
    waste_amount_g numeric(10,2),
    waste_type character varying(50),
    waste_date date,
    waste_timestamp timestamp without time zone,
    recorded_by integer
);


ALTER TABLE public.machine_waste_backup OWNER TO postgres;

--
-- Name: machine_waste_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.machine_waste_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.machine_waste_id_seq OWNER TO postgres;

--
-- Name: machine_waste_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.machine_waste_id_seq OWNED BY public.machine_waste.id;


--
-- Name: machines; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.machines (
    id integer NOT NULL,
    production_line text NOT NULL,
    machine_type text NOT NULL,
    machine_id text NOT NULL,
    status character varying(20) DEFAULT 'available'::character varying NOT NULL,
    current_job_order integer,
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.machines OWNER TO postgres;

--
-- Name: machines_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.machines_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.machines_id_seq OWNER TO postgres;

--
-- Name: machines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.machines_id_seq OWNED BY public.machines.id;


--
-- Name: material_types; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.material_types (
    id integer NOT NULL,
    category character varying(50) NOT NULL,
    material_type character varying(100) NOT NULL
);


ALTER TABLE public.material_types OWNER TO postgres;

--
-- Name: material_types_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.material_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.material_types_id_seq OWNER TO postgres;

--
-- Name: material_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.material_types_id_seq OWNED BY public.material_types.id;


--
-- Name: mv_inv_flow_daily; Type: MATERIALIZED VIEW; Schema: public; Owner: postgres
--

CREATE MATERIALIZED VIEW public.mv_inv_flow_daily AS
 WITH movements AS (
         SELECT inventory.received_date AS day,
            (inventory.weight)::numeric AS qty
           FROM public.inventory
          WHERE (inventory.received_date IS NOT NULL)
        UNION ALL
         SELECT (j.start_time)::date AS day,
            (- (i.weight)::numeric) AS qty
           FROM (public.inventory i
             JOIN public.job_orders j ON ((i.job_order_id = j.id)))
          WHERE (((i.status)::text = 'used'::text) AND (j.start_time IS NOT NULL))
        )
 SELECT day,
    sum(
        CASE
            WHEN (qty > (0)::numeric) THEN qty
            ELSE (0)::numeric
        END) AS total_receipts,
    sum(
        CASE
            WHEN (qty < (0)::numeric) THEN (- qty)
            ELSE (0)::numeric
        END) AS total_withdrawals
   FROM movements
  GROUP BY day
  ORDER BY day
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.mv_inv_flow_daily OWNER TO postgres;

--
-- Name: mv_inv_live; Type: MATERIALIZED VIEW; Schema: public; Owner: postgres
--

CREATE MATERIALIZED VIEW public.mv_inv_live AS
 SELECT category,
    material_type,
    sum(weight) AS total_weight,
    sum(quantity) AS total_quantity
   FROM public.inventory
  WHERE ((status)::text = 'available'::text)
  GROUP BY category, material_type
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.mv_inv_live OWNER TO postgres;

--
-- Name: operational_costs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.operational_costs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    title character varying(255) NOT NULL,
    cost numeric(15,2) NOT NULL,
    quantity integer,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    type character varying(100),
    dynamic_fields jsonb,
    submission_date date DEFAULT CURRENT_DATE NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.operational_costs OWNER TO postgres;

--
-- Name: order_accounting; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_accounting (
    id integer NOT NULL,
    customer_account_id integer NOT NULL,
    job_order_id integer NOT NULL,
    client_name character varying(255) NOT NULL,
    order_amount numeric(15,2) NOT NULL,
    amount_invoiced numeric(15,2) DEFAULT 0.00,
    amount_paid numeric(15,2) DEFAULT 0.00,
    outstanding_balance numeric(15,2) DEFAULT 0.00,
    payment_status character varying(20) DEFAULT 'unpaid'::character varying,
    invoice_status character varying(20) DEFAULT 'not_invoiced'::character varying,
    order_date timestamp without time zone,
    first_invoice_date timestamp without time zone,
    last_payment_date timestamp without time zone,
    due_date timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.order_accounting OWNER TO postgres;

--
-- Name: order_accounting_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.order_accounting_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_accounting_id_seq OWNER TO postgres;

--
-- Name: order_accounting_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.order_accounting_id_seq OWNED BY public.order_accounting.id;


--
-- Name: order_details_view; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.order_details_view AS
SELECT
    NULL::integer AS id,
    NULL::integer AS customer_account_id,
    NULL::integer AS job_order_id,
    NULL::character varying(255) AS client_name,
    NULL::numeric(15,2) AS order_amount,
    NULL::numeric(15,2) AS amount_invoiced,
    NULL::numeric(15,2) AS amount_paid,
    NULL::numeric(15,2) AS outstanding_balance,
    NULL::character varying(20) AS payment_status,
    NULL::character varying(20) AS invoice_status,
    NULL::timestamp without time zone AS order_date,
    NULL::timestamp without time zone AS first_invoice_date,
    NULL::timestamp without time zone AS last_payment_date,
    NULL::timestamp without time zone AS due_date,
    NULL::timestamp without time zone AS created_at,
    NULL::timestamp without time zone AS updated_at,
    NULL::character varying(50) AS order_id,
    NULL::character varying(20) AS product,
    NULL::character varying(50) AS model,
    NULL::integer AS order_quantity,
    NULL::timestamp with time zone AS assigned_date,
    NULL::text AS order_status,
    NULL::bigint AS invoice_count,
    NULL::bigint AS payment_count;


ALTER VIEW public.order_details_view OWNER TO postgres;

--
-- Name: payment_allocations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.payment_allocations (
    id integer NOT NULL,
    receipt_id integer NOT NULL,
    customer_account_id integer NOT NULL,
    job_order_id integer,
    invoice_id integer,
    allocated_amount numeric(15,2) NOT NULL,
    allocation_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    notes text,
    CONSTRAINT positive_allocation CHECK ((allocated_amount > (0)::numeric))
);


ALTER TABLE public.payment_allocations OWNER TO postgres;

--
-- Name: payment_allocations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.payment_allocations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.payment_allocations_id_seq OWNER TO postgres;

--
-- Name: payment_allocations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.payment_allocations_id_seq OWNED BY public.payment_allocations.id;


--
-- Name: payments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.payments (
    id integer NOT NULL,
    supplier_id integer NOT NULL,
    group_id integer NOT NULL,
    invoice_id integer,
    payment_method character varying(50),
    reference_number character varying(100),
    amount_paid numeric(15,2) NOT NULL,
    currency character varying(10) DEFAULT 'USD'::character varying,
    payment_date date DEFAULT CURRENT_DATE,
    additional_fields jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    supplier_name character varying(255)
);


ALTER TABLE public.payments OWNER TO postgres;

--
-- Name: payments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.payments_id_seq OWNER TO postgres;

--
-- Name: payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.payments_id_seq OWNED BY public.payments.id;


--
-- Name: production_hangers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.production_hangers (
    id integer NOT NULL,
    order_id integer NOT NULL,
    batch_index integer NOT NULL,
    stage public.ph_stage DEFAULT 'INJECTION'::public.ph_stage NOT NULL,
    model text,
    injection_weight_g integer,
    packaged_weight_g integer,
    injection_weight_ts timestamp with time zone,
    packaged_weight_ts timestamp with time zone,
    metal_detect_ts timestamp with time zone,
    sizing_ts timestamp with time zone,
    plastic_clips_ts timestamp with time zone,
    metal_clips_ts timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    waste_of_im_g integer,
    waste_of_im_ts timestamp without time zone,
    waste_of_metaldetect_g integer,
    waste_of_metaldetect_ts timestamp without time zone,
    injection_machine_id character varying(20),
    metal_detect_machine_id character varying(20)
);


ALTER TABLE public.production_hangers OWNER TO postgres;

--
-- Name: production_hangers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.production_hangers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.production_hangers_id_seq OWNER TO postgres;

--
-- Name: production_hangers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.production_hangers_id_seq OWNED BY public.production_hangers.id;


--
-- Name: production_rolls; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.production_rolls (
    id integer NOT NULL,
    order_id integer NOT NULL,
    tmp_index integer,
    stage public.roll_stage DEFAULT 'BLOWING'::public.roll_stage NOT NULL,
    roll_weight_g integer,
    printed_weight_g integer,
    cut_weight_g integer,
    packaged_weight_g integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    roll_weight_ts timestamp with time zone,
    printed_weight_ts timestamp with time zone,
    cut_weight_ts timestamp with time zone,
    packaged_weight_ts timestamp with time zone,
    metal_detect_ts timestamp with time zone,
    waste_of_blowing_g integer,
    waste_of_blowing_ts timestamp without time zone,
    waste_of_printing_g integer,
    waste_of_printing_ts timestamp without time zone,
    waste_of_cutting_g integer,
    waste_of_cutting_ts timestamp without time zone,
    waste_of_metal_detect_g integer,
    waste_of_metal_detect_ts timestamp without time zone,
    blowing_machine_id character varying(20),
    printing_machine_id character varying(20),
    cutting_machine_id character varying(20),
    metal_detect_machine_id character varying(20)
);


ALTER TABLE public.production_rolls OWNER TO postgres;

--
-- Name: production_rolls_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.production_rolls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.production_rolls_id_seq OWNER TO postgres;

--
-- Name: production_rolls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.production_rolls_id_seq OWNED BY public.production_rolls.id;


--
-- Name: purchase_orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.purchase_orders (
    id integer NOT NULL,
    group_id integer NOT NULL,
    supplier_id integer NOT NULL,
    po_number character varying(100) NOT NULL,
    delivery_date date,
    quantity_ordered integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    vat_percentage numeric(5,2) DEFAULT 0.00,
    vat_amount numeric(10,2) GENERATED ALWAYS AS (((((quantity_ordered)::numeric * unit_price) * vat_percentage) / (100)::numeric)) STORED,
    total_po_value numeric(15,2) GENERATED ALWAYS AS ((((quantity_ordered)::numeric * unit_price) + ((((quantity_ordered)::numeric * unit_price) * vat_percentage) / (100)::numeric))) STORED,
    additional_fields jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    material_type character varying(255),
    supplier_name character varying(255)
);


ALTER TABLE public.purchase_orders OWNER TO postgres;

--
-- Name: purchase_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.purchase_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.purchase_orders_id_seq OWNER TO postgres;

--
-- Name: purchase_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.purchase_orders_id_seq OWNED BY public.purchase_orders.id;


--
-- Name: raw_invoices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.raw_invoices (
    id integer NOT NULL,
    supplier_id integer NOT NULL,
    group_id integer NOT NULL,
    invoice_number character varying(100),
    total_amount numeric(15,2) NOT NULL,
    status character varying(20) DEFAULT 'unpaid'::character varying,
    invoice_date date DEFAULT CURRENT_DATE,
    due_date date,
    additional_fields jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    supplier_name character varying(255),
    CONSTRAINT raw_invoices_status_check CHECK (((status)::text = ANY ((ARRAY['paid'::character varying, 'unpaid'::character varying, 'partial'::character varying, 'overdue'::character varying])::text[])))
);


ALTER TABLE public.raw_invoices OWNER TO postgres;

--
-- Name: raw_invoices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.raw_invoices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.raw_invoices_id_seq OWNER TO postgres;

--
-- Name: raw_invoices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.raw_invoices_id_seq OWNED BY public.raw_invoices.id;


--
-- Name: raw_materials_costs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.raw_materials_costs (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    cost numeric(15,2) NOT NULL,
    quantity integer,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    type character varying(100),
    dynamic_fields jsonb,
    submission_date date DEFAULT CURRENT_DATE NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.raw_materials_costs OWNER TO postgres;

--
-- Name: raw_materials_costs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.raw_materials_costs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.raw_materials_costs_id_seq OWNER TO postgres;

--
-- Name: raw_materials_costs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.raw_materials_costs_id_seq OWNED BY public.raw_materials_costs.id;


--
-- Name: receipts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.receipts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.receipts_id_seq OWNER TO postgres;

--
-- Name: receipts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.receipts_id_seq OWNED BY public.receipts.id;


--
-- Name: recycling_line; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.recycling_line (
    id integer NOT NULL,
    recycling_material_type character varying(100) NOT NULL,
    input_weight numeric(10,3) NOT NULL,
    timestamp_start timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    final_weight_recycled numeric(10,3),
    packaging_process_timestamp timestamp with time zone,
    calculated_recycling_time interval,
    count_packaged_bags integer DEFAULT 0,
    status character varying(20) DEFAULT 'IN_PROGRESS'::character varying,
    efficiency_percentage numeric(5,2) GENERATED ALWAYS AS (
CASE
    WHEN ((input_weight > (0)::numeric) AND (final_weight_recycled IS NOT NULL)) THEN round(((final_weight_recycled / input_weight) * (100)::numeric), 2)
    ELSE NULL::numeric
END) STORED,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT recycling_line_count_packaged_bags_check CHECK ((count_packaged_bags >= 0)),
    CONSTRAINT recycling_line_final_weight_recycled_check CHECK ((final_weight_recycled >= (0)::numeric)),
    CONSTRAINT recycling_line_input_weight_check CHECK ((input_weight > (0)::numeric)),
    CONSTRAINT recycling_line_status_check CHECK (((status)::text = ANY ((ARRAY['IN_PROGRESS'::character varying, 'COMPLETED'::character varying, 'CANCELLED'::character varying])::text[])))
);


ALTER TABLE public.recycling_line OWNER TO postgres;

--
-- Name: recycling_line_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.recycling_line_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.recycling_line_id_seq OWNER TO postgres;

--
-- Name: recycling_line_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.recycling_line_id_seq OWNED BY public.recycling_line.id;


--
-- Name: revenue_details; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.revenue_details (
    id integer NOT NULL,
    revenue_id integer NOT NULL,
    invoice_id integer NOT NULL,
    client_name character varying(255) NOT NULL,
    job_order_id integer NOT NULL,
    invoice_date date NOT NULL,
    invoice_number character varying(50) NOT NULL,
    subtotal numeric(15,2) NOT NULL,
    total_amount numeric(15,2) NOT NULL,
    amount_paid numeric(15,2) NOT NULL,
    outstanding_balance numeric(15,2) NOT NULL,
    product character varying(255),
    model character varying(255),
    unit_price numeric(15,2),
    order_quantity integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.revenue_details OWNER TO postgres;

--
-- Name: revenue_details_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.revenue_details_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.revenue_details_id_seq OWNER TO postgres;

--
-- Name: revenue_details_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.revenue_details_id_seq OWNED BY public.revenue_details.id;


--
-- Name: revenues; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.revenues (
    id integer NOT NULL,
    report_name character varying(255) NOT NULL,
    period_type character varying(20) NOT NULL,
    period_start_date date NOT NULL,
    period_end_date date NOT NULL,
    year integer,
    month integer,
    quarter integer,
    total_revenue numeric(15,2) DEFAULT 0.00 NOT NULL,
    total_invoices integer DEFAULT 0 NOT NULL,
    raw_materials_costs numeric(15,2) DEFAULT 0.00 NOT NULL,
    operational_costs numeric(15,2) DEFAULT 0.00 NOT NULL,
    general_costs numeric(15,2) DEFAULT 0.00 NOT NULL,
    depreciation_costs numeric(15,2) DEFAULT 0.00 NOT NULL,
    unexpected_costs numeric(15,2) DEFAULT 0.00 NOT NULL,
    total_costs numeric(15,2) DEFAULT 0.00 NOT NULL,
    profit numeric(15,2) DEFAULT 0.00 NOT NULL,
    net_profit numeric(15,2) DEFAULT 0.00 NOT NULL,
    profit_margin numeric(5,2) DEFAULT 0.00 NOT NULL,
    net_profit_margin numeric(5,2) DEFAULT 0.00 NOT NULL,
    generated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(20) DEFAULT 'active'::character varying,
    notes text
);


ALTER TABLE public.revenues OWNER TO postgres;

--
-- Name: revenues_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.revenues_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.revenues_id_seq OWNER TO postgres;

--
-- Name: revenues_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.revenues_id_seq OWNED BY public.revenues.id;


--
-- Name: storage_management; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.storage_management (
    id integer NOT NULL,
    order_id integer NOT NULL,
    client_name character varying(255),
    product character varying(50),
    model character varying(100),
    order_quantity integer,
    size_specs character varying(100),
    status character varying(20) DEFAULT 'stored'::character varying,
    storage_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    shipping_date timestamp without time zone,
    stored_by character varying(100),
    shipped_by character varying(100),
    notes text
);


ALTER TABLE public.storage_management OWNER TO postgres;

--
-- Name: storage_management_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.storage_management_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.storage_management_id_seq OWNER TO postgres;

--
-- Name: storage_management_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.storage_management_id_seq OWNED BY public.storage_management.id;


--
-- Name: supplier_accounts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.supplier_accounts (
    id integer NOT NULL,
    group_id integer,
    supplier_name character varying(255) NOT NULL,
    supplier_code character varying(100) NOT NULL,
    contact_email character varying(255) NOT NULL,
    contact_phone character varying(50) NOT NULL,
    contact_name character varying(255) NOT NULL,
    currency character varying(10) DEFAULT 'USD'::character varying,
    payment_terms character varying(100) NOT NULL,
    outstanding_balance numeric(15,2) DEFAULT 0.00,
    additional_fields jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_currency_format CHECK ((length((currency)::text) <= 10)),
    CONSTRAINT chk_outstanding_balance_non_negative CHECK ((outstanding_balance >= (0)::numeric))
);


ALTER TABLE public.supplier_accounts OWNER TO postgres;

--
-- Name: supplier_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.supplier_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.supplier_accounts_id_seq OWNER TO postgres;

--
-- Name: supplier_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.supplier_accounts_id_seq OWNED BY public.supplier_accounts.id;


--
-- Name: unexpected_costs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.unexpected_costs (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    cost numeric(15,2) NOT NULL,
    quantity integer,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    type character varying(100),
    dynamic_fields jsonb,
    submission_date date DEFAULT CURRENT_DATE NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.unexpected_costs OWNER TO postgres;

--
-- Name: unexpected_costs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.unexpected_costs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.unexpected_costs_id_seq OWNER TO postgres;

--
-- Name: unexpected_costs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.unexpected_costs_id_seq OWNED BY public.unexpected_costs.id;


--
-- Name: used_materials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.used_materials (
    id integer NOT NULL,
    barcode text NOT NULL,
    job_order_id integer,
    activation_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.used_materials OWNER TO postgres;

--
-- Name: used_materials_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.used_materials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.used_materials_id_seq OWNER TO postgres;

--
-- Name: used_materials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.used_materials_id_seq OWNED BY public.used_materials.id;


--
-- Name: v_inv_aging; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.v_inv_aging AS
 SELECT id,
    material_type,
    weight,
    (CURRENT_DATE - received_date) AS age_days
   FROM public.inventory
  WHERE ((status)::text IS DISTINCT FROM 'scrapped'::text);


ALTER VIEW public.v_inv_aging OWNER TO postgres;

--
-- Name: waste_analysis_view; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.waste_analysis_view AS
 SELECT mw.machine_id,
    mw.job_order_id,
    mw.index_number,
    mw.waste_type,
    mw.waste_date,
    mw.waste_amount_g,
    jom.machine_type,
        CASE
            WHEN ("left"((mw.machine_id)::text, 2) = ANY (ARRAY['BF'::text, 'P_'::text, 'C_'::text])) THEN 'production_rolls'::text
            WHEN ("left"((mw.machine_id)::text, 2) = 'IM'::text) THEN 'production_hangers'::text
            ELSE 'unknown'::text
        END AS production_type
   FROM (public.machine_waste mw
     JOIN public.job_order_machines jom ON ((((mw.machine_id)::text = (jom.machine_id)::text) AND (mw.job_order_id = jom.job_order_id))));


ALTER VIEW public.waste_analysis_view OWNER TO postgres;

--
-- Name: withdrawals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.withdrawals (
    id integer NOT NULL,
    material_type text NOT NULL,
    withdrawn_weight numeric(10,2) NOT NULL,
    withdrawn_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    job_order_id integer,
    operator_id integer
);


ALTER TABLE public.withdrawals OWNER TO postgres;

--
-- Name: withdrawals_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.withdrawals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.withdrawals_id_seq OWNER TO postgres;

--
-- Name: withdrawals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.withdrawals_id_seq OWNED BY public.withdrawals.id;


--
-- Name: attendance id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.attendance ALTER COLUMN id SET DEFAULT nextval('public.attendance_id_seq'::regclass);


--
-- Name: comp_inventory id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comp_inventory ALTER COLUMN id SET DEFAULT nextval('public.comp_inventory_id_seq'::regclass);


--
-- Name: comp_inventory_attributes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comp_inventory_attributes ALTER COLUMN id SET DEFAULT nextval('public.comp_inventory_attributes_id_seq'::regclass);


--
-- Name: custom_field_definitions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_field_definitions ALTER COLUMN id SET DEFAULT nextval('public.custom_field_definitions_id_seq'::regclass);


--
-- Name: customer_accounts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer_accounts ALTER COLUMN id SET DEFAULT nextval('public.customer_accounts_id_seq'::regclass);


--
-- Name: daily_waste_summary id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.daily_waste_summary ALTER COLUMN id SET DEFAULT nextval('public.daily_waste_summary_id_seq'::regclass);


--
-- Name: depreciation_costs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.depreciation_costs ALTER COLUMN id SET DEFAULT nextval('public.depreciation_costs_id_seq'::regclass);


--
-- Name: employees id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees ALTER COLUMN id SET DEFAULT nextval('public.employees_id_seq'::regclass);


--
-- Name: general_costs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.general_costs ALTER COLUMN id SET DEFAULT nextval('public.general_costs_id_seq'::regclass);


--
-- Name: inventory id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory ALTER COLUMN id SET DEFAULT nextval('public.inventory_id_seq'::regclass);


--
-- Name: inventory_orders id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_orders ALTER COLUMN id SET DEFAULT nextval('public.inventory_orders_id_seq'::regclass);


--
-- Name: invoices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoices ALTER COLUMN id SET DEFAULT nextval('public.invoices_id_seq'::regclass);


--
-- Name: job_order_bags id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_bags ALTER COLUMN id SET DEFAULT nextval('public.job_order_bags_id_seq'::regclass);


--
-- Name: job_order_cardboards id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_cardboards ALTER COLUMN id SET DEFAULT nextval('public.job_order_cardboards_id_seq'::regclass);


--
-- Name: job_order_clips id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_clips ALTER COLUMN id SET DEFAULT nextval('public.job_order_clips_id_seq'::regclass);


--
-- Name: job_order_component_attributes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_component_attributes ALTER COLUMN id SET DEFAULT nextval('public.job_order_component_attributes_id_seq'::regclass);


--
-- Name: job_order_components id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_components ALTER COLUMN id SET DEFAULT nextval('public.job_order_components_id_seq'::regclass);


--
-- Name: job_order_inks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_inks ALTER COLUMN id SET DEFAULT nextval('public.job_order_inks_id_seq'::regclass);


--
-- Name: job_order_machines id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_machines ALTER COLUMN id SET DEFAULT nextval('public.job_order_machines_id_seq'::regclass);


--
-- Name: job_order_materials id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_materials ALTER COLUMN id SET DEFAULT nextval('public.job_order_materials_id_seq'::regclass);


--
-- Name: job_order_sizers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_sizers ALTER COLUMN id SET DEFAULT nextval('public.job_order_sizers_id_seq'::regclass);


--
-- Name: job_order_solvents id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_solvents ALTER COLUMN id SET DEFAULT nextval('public.job_order_solvents_id_seq'::regclass);


--
-- Name: job_order_tapes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_tapes ALTER COLUMN id SET DEFAULT nextval('public.job_order_tapes_id_seq'::regclass);


--
-- Name: job_orders id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_orders ALTER COLUMN id SET DEFAULT nextval('public.job_orders_id_seq'::regclass);


--
-- Name: machine_production_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history ALTER COLUMN id SET DEFAULT nextval('public.machine_production_history_id_seq'::regclass);


--
-- Name: machine_production_history_ph id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history_ph ALTER COLUMN id SET DEFAULT nextval('public.machine_production_history_ph_id_seq'::regclass);


--
-- Name: machine_waste id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_waste ALTER COLUMN id SET DEFAULT nextval('public.machine_waste_id_seq'::regclass);


--
-- Name: machines id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machines ALTER COLUMN id SET DEFAULT nextval('public.machines_id_seq'::regclass);


--
-- Name: material_types id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_types ALTER COLUMN id SET DEFAULT nextval('public.material_types_id_seq'::regclass);


--
-- Name: order_accounting id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_accounting ALTER COLUMN id SET DEFAULT nextval('public.order_accounting_id_seq'::regclass);


--
-- Name: payment_allocations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment_allocations ALTER COLUMN id SET DEFAULT nextval('public.payment_allocations_id_seq'::regclass);


--
-- Name: payments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments ALTER COLUMN id SET DEFAULT nextval('public.payments_id_seq'::regclass);


--
-- Name: production_hangers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_hangers ALTER COLUMN id SET DEFAULT nextval('public.production_hangers_id_seq'::regclass);


--
-- Name: production_rolls id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_rolls ALTER COLUMN id SET DEFAULT nextval('public.production_rolls_id_seq'::regclass);


--
-- Name: purchase_orders id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders ALTER COLUMN id SET DEFAULT nextval('public.purchase_orders_id_seq'::regclass);


--
-- Name: raw_invoices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.raw_invoices ALTER COLUMN id SET DEFAULT nextval('public.raw_invoices_id_seq'::regclass);


--
-- Name: raw_materials_costs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.raw_materials_costs ALTER COLUMN id SET DEFAULT nextval('public.raw_materials_costs_id_seq'::regclass);


--
-- Name: receipts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.receipts ALTER COLUMN id SET DEFAULT nextval('public.receipts_id_seq'::regclass);


--
-- Name: recycling_line id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recycling_line ALTER COLUMN id SET DEFAULT nextval('public.recycling_line_id_seq'::regclass);


--
-- Name: revenue_details id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.revenue_details ALTER COLUMN id SET DEFAULT nextval('public.revenue_details_id_seq'::regclass);


--
-- Name: revenues id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.revenues ALTER COLUMN id SET DEFAULT nextval('public.revenues_id_seq'::regclass);


--
-- Name: storage_management id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.storage_management ALTER COLUMN id SET DEFAULT nextval('public.storage_management_id_seq'::regclass);


--
-- Name: supplier_accounts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_accounts ALTER COLUMN id SET DEFAULT nextval('public.supplier_accounts_id_seq'::regclass);


--
-- Name: unexpected_costs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unexpected_costs ALTER COLUMN id SET DEFAULT nextval('public.unexpected_costs_id_seq'::regclass);


--
-- Name: used_materials id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.used_materials ALTER COLUMN id SET DEFAULT nextval('public.used_materials_id_seq'::regclass);


--
-- Name: withdrawals id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.withdrawals ALTER COLUMN id SET DEFAULT nextval('public.withdrawals_id_seq'::regclass);


--
-- Data for Name: inv_kpi_history; Type: TABLE DATA; Schema: analytics; Owner: postgres
--

COPY analytics.inv_kpi_history (snapshot_date, material_type, on_hand_kg, kg_per_batch, batches, avg_density, forecast_accuracy, days_of_supply, reorder_point) FROM stdin;
\.


--
-- Data for Name: inv_risk_assessment; Type: TABLE DATA; Schema: analytics; Owner: postgres
--

COPY analytics.inv_risk_assessment (material_type, assessment_date, stockout_risk, excess_stock_risk, aging_risk, cost_opportunity) FROM stdin;
\.


--
-- Data for Name: inv_seasonality; Type: TABLE DATA; Schema: analytics; Owner: postgres
--

COPY analytics.inv_seasonality (material_type, month, seasonal_factor, confidence_level) FROM stdin;
\.


--
-- Data for Name: attendance; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.attendance (id, employee_id, "timestamp") FROM stdin;
\.


--
-- Data for Name: comp_inventory; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.comp_inventory (id, material_name, type, quantity, weight, supplier, serial_number, date_added, unit_price, total_price) FROM stdin;
1	plastic	roll	100	12.5	XYZ Supplier	PLA-ROL-20250412-001	2025-04-12 15:11:35.170783	\N	\N
2	FlexoInk	water-based	100	15	Sun Chemicals	FLE-WAT-20250412-002	2025-04-12 15:17:53.230433	\N	\N
3	clips	plastic	1000	100	EEMW	CLI-PLA-20250413-003	2025-04-13 12:56:04.944081	\N	\N
4	clips	metal	1000	100	EEMW	CLI-MET-20250413-004	2025-04-13 12:56:16.567419	\N	\N
5	carton	carton	100	10	AMCO	CAR-CAR-20250413-005	2025-04-13 15:29:51.264254	\N	\N
6	carton	Packaging	10	10	amvv	CAR-PAC-20250413-006	2025-04-13 15:32:36.287499	\N	\N
7	carton	Packaging	10	10	amvv	CAR-PAC-20250413-007	2025-04-13 17:58:28.825458	\N	\N
8	carton	Packaging	10	10	amvv	CAR-PAC-20250413-008	2025-04-13 18:01:17.253813	\N	\N
9	sizer	S	1000	100	EEMW	SIZ-S-20250414-009	2025-04-14 13:11:04.329051	\N	\N
11	Carton	Carton	1000	100	EEMW	CAR-CAR-20250414-011	2025-04-14 13:18:45.919636	\N	\N
12	Carton	Carton	1000	100	EEMW	CAR-CAR-20250414-012	2025-04-14 13:19:19.689063	\N	\N
14	Ink	Flexo	1000	100	EEMW	INK-FLE-20250414-014	2025-04-14 13:28:25.534659	\N	\N
15	Ink	Flexo	1000	100	EEMW	INK-FLE-20250414-015	2025-04-14 13:29:31.294053	\N	\N
10	Sizer	M	900	100	EEMW	SIZ-M-20250414-010	2025-04-14 13:13:09.934954	\N	\N
16	Ink	Water-Based	1000	100	EEMW	INK-WAT-20250414-016	2025-04-14 13:31:01.032614	\N	\N
19	Carton 	CardBoard	97	10	Ahmed	CAR-CAR-20250415-019	2025-04-15 18:04:45.150741	\N	\N
13	Carton	60x10	997	100	EEMW	CAR-60X-20250414-013	2025-04-14 13:20:20.242424	\N	\N
18	Scotch 	PE	98	10	Local Supplier	SCO-PE-20250415-018	2025-04-15 17:02:41.465288	\N	\N
17	OPP Tape	Brown	96	10	Tesa	OPP-BRO-20250415-017	2025-04-15 16:56:44.226167	\N	\N
20	Sizer	L	990	100	Zed	SIZ-L-20250422-020	2025-04-22 17:14:08.149599	\N	\N
21	Carton 	Cardboard	20	20	doks	CAR-CAR-20250527-021	2025-05-27 19:57:36.41657	1.50	30.00
22	carton 	cardboard	10	10	mm	CAR-CAR-20250527-022	2025-05-27 20:07:42.046476	1.20	12.00
23	Tape	Type B	10	10	uuuu	TAP-TYP-20250527-023	2025-05-27 20:29:45.171023	2.10	21.00
24	Tape	Type B	10	10	uuu	TAP-TYP-20250527-024	2025-05-27 20:30:49.180634	2.10	21.00
\.


--
-- Data for Name: comp_inventory_attributes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.comp_inventory_attributes (id, comp_inventory_id, key, value) FROM stdin;
1	1	color	white
2	1	core_size	2 inches
3	1	thickness	45 microns
4	2	color	Black
5	2	Packaging	1Litre
6	3	additionalProp1	string
7	3	additionalProp2	string
8	3	additionalProp3	string
9	4	additionalProp1	string
10	4	additionalProp2	string
11	4	additionalProp3	string
12	8	size	S
13	12	size	10x20
14	13	size	10x20
15	14	color	Blue
16	14	packaging	1Litre
17	15	color	Red
18	15	Packaging	1Litre
19	16	color	Red
20	16	Packaging	1Litre
21	17	Length 	100m
22	17	Width	48mm
23	17	Core Size	3inch
24	18	Width	50cm
25	18	Length 	50cm
26	18	Thickness	23microns
27	19	Lenght 	30cm
28	19	Width	20cm
29	21	Length 	30
30	21	Width	20
31	22	length 	10 cm
32	22	width 	20 cm
33	22	micron 	30 mm
34	23	category	Packaging
35	24	category	Packaging
\.


--
-- Data for Name: custom_field_definitions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.custom_field_definitions (id, table_name, field_name, field_type, field_label, field_options, is_required, default_value, validation_rules, display_order, is_active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: customer_accounts; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.customer_accounts (id, client_name, contact_email, contact_phone, contact_person_name, company_address, billing_address, shipping_address, payment_terms, currency, tax_id, industry, total_orders_count, total_amount_due, total_amount_paid, outstanding_balance, credit_limit, account_status, last_order_date, last_payment_date, last_invoice_date, custom_fields, notes, created_at, updated_at) FROM stdin;
2	Under armor	Nike@gmail.com	01000000	test	test	test	test	Net 30	USD	string	Fashion	2	0.00	0.00	0.00	0.00	active	2025-05-04 17:46:07.162598	\N	\N	\N	\N	2025-06-18 16:09:29.096445	2025-06-18 16:09:29.096445
3	test	test@gmail.com	string	string	string	string	string	Net 30	USD	string	string	3	140.00	0.00	140.00	0.00	active	2025-06-18 18:44:22.571054	\N	\N	\N	\N	2025-06-18 18:41:29.151986	2025-06-18 18:44:22.571054
5	Budget Bags Ltd	bdf@gmail.com	0100013265	Ahmed	\N	\N	westv test22	Net 30	USD	12541220	fashion	2	7200.00	0.00	7200.00	1000.00	active	2025-05-27 14:19:13.517742	\N	\N	\N	\N	2025-06-19 15:16:59.848757	2025-06-19 15:16:59.848757
7	Zebra	zebra@gmail.com	01014785384	hamada	\N	55 west arabella 	zebra new cairo 	Net 30	USD	\N	\N	1	10000.00	0.00	10000.00	0.00	active	2025-06-02 12:33:31.414393	\N	\N	\N	\N	2025-06-19 18:17:20.188845	2025-06-19 18:17:20.188845
9	h&m	SHSH@GMAIL.COM	010001422121	TES	\N	TES	TE	Net 30	USD	\N	\N	1	0.00	0.00	0.00	0.00	active	2025-04-22 14:28:57.500751	\N	\N	\N	\N	2025-06-19 18:46:40.810387	2025-06-19 18:46:40.810387
12	ytdd	ty@gmail.com	10156562	wew	\N	wewed	wews	Net 30	USD	\N	\N	1	100000.00	0.00	100000.00	0.00	active	2025-06-03 13:46:57.42484	\N	\N	\N	\N	2025-06-19 19:12:23.619963	2025-06-19 19:12:23.619963
4	xyz	test@gmail.com	string	string	string	string	string	Net 30	USD	string	string	4	63088.00	0.00	58644.00	0.00	active	2025-05-27 15:34:09.754214	\N	\N	\N	\N	2025-06-18 18:47:03.588823	2025-06-18 18:47:03.588823
8	Fashion House Co	fhco@gmail.com	01002489260	Demery	\N	silicon west california 	55west arabella 	Net 30	USD	\N	\N	2	5000.00	0.00	4500.00	0.00	active	2025-05-27 14:29:16.478118	\N	\N	\N	\N	2025-06-19 18:27:21.022798	2025-06-19 18:27:21.022798
6	www	www@gmail.com	01000000	test	\N	55 west arabella 	To xyz street	Net 30	USD	\N	\N	1	1000000.00	0.00	989119.00	0.00	active	2025-06-03 17:38:00.380638	\N	\N	\N	\N	2025-06-19 18:07:31.15869	2025-06-19 18:07:31.15869
10	APPLE	apple@gmail.com	41411	ysys	\N	EEWD	021DV	Net 30	USD	\N	\N	2	1000.00	0.00	600.00	0.00	active	2025-05-27 10:22:08.506246	\N	\N	\N	\N	2025-06-19 18:47:50.065107	2025-06-19 18:47:50.065107
1	Nike	Nike@gmail.com	01000000	test	test	test	test	Net 30	USD	string	Fashion	4	101464.00	0.00	99647.00	0.00	active	2025-06-25 18:54:02.824346	\N	\N	\N	\N	2025-06-18 15:43:25.819187	2025-06-25 18:54:02.824346
11	adam	adam@gmail.com	4510212	mohsen 	\N	esdjasdhu	weste estst	Net 30	USD	\N	\N	2	120000.00	0.00	118311.00	0.00	active	2025-06-23 12:13:18.074987	\N	\N	\N	\N	2025-06-19 19:07:52.354166	2025-06-23 12:13:18.074987
\.


--
-- Data for Name: daily_waste_summary; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.daily_waste_summary (id, machine_id, waste_date, total_waste_g, total_orders) FROM stdin;
3	IM-001	2025-05-14	13000.00	1
6	IM-001	2025-05-13	5000.00	1
1	BF-002	2025-05-15	2000.00	1
9	BF-002	2025-05-16	1000.00	1
10	P-002	2025-05-16	1000.00	1
11	C-003	2025-05-15	1000.00	1
2	IM-001	2025-05-17	150.00	1
\.


--
-- Data for Name: depreciation_costs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.depreciation_costs (id, title, cost, quantity, currency, type, dynamic_fields, submission_date, created_at, updated_at) FROM stdin;
1	test	250.00	1	USD	test	\N	2025-06-24	2025-06-24 17:12:35.174391+03	2025-06-24 17:12:35.174391+03
\.


--
-- Data for Name: employees; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.employees (id, name, email, password, role, barcode, created_at, status, current_job_order) FROM stdin;
1	mohamed	mohamed.eldemery@eemwco.com	$2b$12$rjv21NVCQnQHunThJkQKyOfGqlwPQAgjgZUYscLcCWhCvQwcQ45XC	Admin	ADM-250317-0001	2025-03-17 15:17:25.563748	available	\N
29	amr	amr@gmail.com	$2b$12$zuxVRY/qeDlCMUI3Eztxuur9sEJUdpf7Z5zHGz0LwV3FW6Adil4we	Manager	MNG-250321-0029	2025-03-21 15:12:17.216959	available	\N
33	eemw	eemw@gmail.com	$2b$12$e78iEd9PhlF63A6FRJlP6.xHRodM/SWT3TxyC1ania5P1YF6cNSwa	Admin	ADM-250321-0033	2025-03-21 16:27:14.516279	available	\N
35	oper	operator@gmail.com	$2b$12$b1t0tZbJxkb4YgFDXIfdIezPXKoErgmUNn9RrVsREOgLZ1xsXQH1W	Operator	OPR-250322-0035	2025-03-22 12:13:25.750201	busy	39
37	Abdo	abdo@gmail.com	$2b$12$5jQbcCG9DlBW/Yp3zKk1GeRBBgpo8u5xHSDadA0FMrJBkoBIFLjBO	Operator	OPR-250323-0037	2025-03-23 16:11:20.328541	busy	52
39	Baza	baza@gmail.com	$2b$12$oqC72v3ABlNBymHeH7YuyuBW.ObqfsDh7s9Uxvsedh/5HHvcTZnp.	Operator	OPR-250323-0039	2025-03-23 16:12:03.351234	busy	53
40	Shawky	shawky@gmail.com	$2b$12$jd/YQGspvxWb1f5Jf31.buthS0o3kpPL7O/LiYXdrjHIRucfqAwWy	Operator	OPR-250323-0040	2025-03-23 16:12:28.056323	busy	54
41	Yassin Abdou	yassin@royal-industry.com	$2b$12$LOOIsn/lJuS5NqnueKzxNuwOp.HZtYsM1y9LADy8OYZFumX9yXcS.	Admin	ADM-250706-0041	2025-07-06 15:33:35.637174	available	\N
42	ahmed	ahmed@gmail.com	$2b$12$pF4c36mFK1wsfZnzG/afSuIL9QSwfyZ6wFi6JKW.Vv3ZcZAgvLG2.	Operator	OPR-250706-0042	2025-07-06 15:37:31.62198	available	\N
43	mostafa	mostafa@gmail.com	$2b$12$yoomCn4q5Y8Sj1E8Po6souvzUP.fzrtIZfN/wR8C8buRa6I40t9hC	Operator	OPR-250706-0043	2025-07-06 15:46:15.586552	available	\N
44	Saied	saied@gmail.com	$2b$12$E1QA1Ran1p0TmAuN/ExU0O88RaElyCkGQqx4k3JRu3OcTZ594melu	Operator	OPR-250706-0044	2025-07-06 15:50:51.975303	available	\N
\.


--
-- Data for Name: general_costs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.general_costs (id, title, cost, quantity, currency, type, dynamic_fields, submission_date, created_at, updated_at) FROM stdin;
1	rent	1000.00	1	USD	rentt	\N	2025-06-24	2025-06-24 17:13:27.804414+03	2025-06-24 17:13:27.804414+03
\.


--
-- Data for Name: inventory; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.inventory (id, category, material_type, weight, quantity, supplier, received_date, group_id, barcode, density, grade, color, kind, status, job_order_id, cost_per_kg, order_date, unit_price, total_price) FROM stdin;
381	1st Degree	HDPE	25.00	1	zeioj	2025-04-08	476	1D-HDP-250408-476-001	\N	\N	\N	\N	available	\N	\N	\N	\N	\N
382	1st Degree	HDPE	25.00	1	zeioj	2025-04-08	476	1D-HDP-250408-476-002	\N	\N	\N	\N	available	\N	\N	\N	\N	\N
383	1st Degree	HDPE	25.00	1	zeioj	2025-04-08	476	1D-HDP-250408-476-003	\N	\N	\N	\N	available	\N	\N	\N	\N	\N
384	1st Degree	HDPE	25.00	1	zeioj	2025-04-08	476	1D-HDP-250408-476-004	\N	\N	\N	\N	available	\N	\N	\N	\N	\N
385	1st Degree	LDPE	25.00	1	uiuiui	2025-04-08	882	1D-LDP-250408-882-001	\N	\N	\N	\N	available	\N	\N	\N	\N	\N
386	1st Degree	LDPE	25.00	1	uiuiui	2025-04-08	882	1D-LDP-250408-882-002	\N	\N	\N	\N	available	\N	\N	\N	\N	\N
387	1st Degree	LLDPE AAB	500.00	1	ABC Plastics	2025-04-10	733	1D-LLDAAB-250409-733-001	0.92	Food Grade	Transparent	\N	available	\N	\N	\N	\N	\N
388	1st Degree	LLDPE AAB	500.00	1	ABC Plastics	2025-04-10	733	1D-LLDAAB-250409-733-002	0.92	Food Grade	Transparent	\N	available	\N	\N	\N	\N	\N
389	1st Degree	LLDPE AAB	500.00	1	ABC Plastics	2025-04-10	733	1D-LLDAAB-250409-733-003	0.92	Food Grade	Transparent	\N	available	\N	\N	\N	\N	\N
391	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-001	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
392	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-002	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
393	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-003	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
394	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-004	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
395	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-005	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
396	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-006	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
397	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-007	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
398	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-008	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
399	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-009	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
400	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-010	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
401	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-011	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
402	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-012	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
403	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-013	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
404	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-014	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
405	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-015	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
406	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-016	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
407	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-017	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
408	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-018	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
409	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-019	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
410	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-020	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
411	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-021	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
412	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-022	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
413	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-023	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
414	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-024	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
415	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-025	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
416	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-026	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
417	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-027	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
418	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-028	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
419	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-029	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
420	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-030	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
421	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-031	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
422	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-032	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
423	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-033	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
424	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-034	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
425	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-035	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
426	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-036	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
427	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-037	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
428	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-038	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
429	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-039	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
430	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-040	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
431	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-041	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
376	1st Degree	PP	25.00	1	eemw	2025-04-08	926	1D-PP-250408-926-001	\N	\N	\N	\N	used	28	\N	\N	\N	\N
378	1st Degree	PP	25.00	1	eemw	2025-04-08	926	1D-PP-250408-926-003	\N	\N	\N	\N	used	31	\N	\N	\N	\N
432	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-042	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
433	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-043	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
434	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-044	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
435	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-045	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
436	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-046	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
437	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-047	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
438	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-048	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
439	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-049	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
440	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-050	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
441	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-051	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
442	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-052	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
443	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-053	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
444	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-054	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
445	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-055	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
446	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-056	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
447	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-057	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
448	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-058	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
449	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-059	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
450	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-060	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
451	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-061	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
452	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-062	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
453	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-063	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
454	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-064	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
455	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-065	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
456	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-066	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
457	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-067	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
458	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-068	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
459	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-069	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
460	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-070	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
461	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-071	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
462	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-072	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
463	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-073	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
464	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-074	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
465	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-075	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
466	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-076	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
467	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-077	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
468	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-078	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
469	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-079	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
470	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-080	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
471	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-081	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
472	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-082	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
473	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-083	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
474	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-084	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
475	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-085	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
476	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-086	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
477	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-087	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
478	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-088	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
479	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-089	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
480	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-090	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
481	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-091	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
482	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-092	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
483	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-093	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
484	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-094	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
485	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-095	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
486	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-096	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
487	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-097	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
488	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-098	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
489	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-099	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
490	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	string	1D-LDP-250410-string-100	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
491	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	372	1D-LDP-250410-372-001	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
492	1st Degree	LDPE	25.00	1	SIDPEC	2025-04-10	372	1D-LDP-250410-372-002	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
493	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-001	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
494	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-002	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
495	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-003	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
496	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-004	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
497	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-005	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
498	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-006	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
499	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-007	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
500	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-008	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
501	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-009	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
502	1st Degree	PP	25.00	1	hamada	2025-04-14	string	1D-PP-250414-string-010	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
503	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-001	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
504	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-002	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
505	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-003	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
506	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-004	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
507	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-005	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
508	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-006	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
509	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-007	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
510	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-008	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
511	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-009	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
512	1st Degree	PP	25.00	1	hamada	2025-04-14	223	1D-PP-250414-223-010	0.92	film grade	natural	Virgin	available	\N	\N	\N	\N	\N
515	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-003	0.98	momtaz	natural	Virgin	available	\N	\N	\N	\N	\N
516	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-004	0.98	momtaz	natural	Virgin	available	\N	\N	\N	\N	\N
531	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-004	0.92	Film Grade	Natural 	Recycled	available	\N	\N	\N	\N	\N
532	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-005	0.92	Film Grade	Natural 	Recycled	available	\N	\N	\N	\N	\N
533	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-006	0.92	Film Grade	Natural 	Recycled	available	\N	\N	\N	\N	\N
534	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-007	0.92	Film Grade	Natural 	Recycled	available	\N	\N	\N	\N	\N
535	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-008	0.92	Film Grade	Natural 	Recycled	available	\N	\N	\N	\N	\N
514	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-002	0.98	momtaz	natural	Virgin	used	26	\N	\N	\N	\N
517	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-005	0.98	momtaz	natural	Virgin	used	30	\N	\N	\N	\N
519	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-007	0.98	momtaz	natural	Virgin	used	30	\N	\N	\N	\N
520	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-008	0.98	momtaz	natural	Virgin	used	30	\N	\N	\N	\N
523	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-011	0.98	momtaz	natural	Virgin	used	30	\N	\N	\N	\N
524	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-012	0.98	momtaz	natural	Virgin	used	30	\N	\N	\N	\N
522	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-010	0.98	momtaz	natural	Virgin	used	31	\N	\N	\N	\N
528	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-001	0.92	Film Grade	Natural 	Recycled	used	32	\N	\N	\N	\N
529	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-002	0.92	Film Grade	Natural 	Recycled	used	32	\N	\N	\N	\N
530	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-003	0.92	Film Grade	Natural 	Recycled	used	32	\N	\N	\N	\N
525	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-013	0.98	momtaz	natural	Virgin	used	34	\N	\N	\N	\N
521	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-009	0.98	momtaz	natural	Virgin	used	34	\N	\N	\N	\N
537	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-010	0.92	Film Grade	Natural 	Recycled	used	36	\N	\N	\N	\N
536	2nd Degree	LLDPE (recycled)	25.00	1	SIDPEC	2025-04-15	993	2D-LLD(RE-250415-993-009	0.92	Film Grade	Natural 	Recycled	used	36	\N	\N	\N	\N
538	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-001	0.92	FILM GRADE	Black	Recycled	available	\N	\N	\N	\N	\N
539	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-002	0.92	FILM GRADE	Black	Recycled	available	\N	\N	\N	\N	\N
540	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-003	0.92	FILM GRADE	Black	Recycled	available	\N	\N	\N	\N	\N
541	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-004	0.92	FILM GRADE	Black	Recycled	available	\N	\N	\N	\N	\N
544	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-007	0.92	FILM GRADE	Black	Recycled	available	\N	\N	\N	\N	\N
551	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-004	0.92	Film Grade	Transparent 	Virgin	available	\N	\N	\N	\N	\N
552	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-005	0.92	Film Grade	Transparent 	Virgin	available	\N	\N	\N	\N	\N
553	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-006	0.92	Film Grade	Transparent 	Virgin	available	\N	\N	\N	\N	\N
554	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-007	0.92	Film Grade	Transparent 	Virgin	available	\N	\N	\N	\N	\N
555	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-008	0.92	Film Grade	Transparent 	Virgin	available	\N	\N	\N	\N	\N
556	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-009	0.92	Film Grade	Transparent 	Virgin	available	\N	\N	\N	\N	\N
557	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-010	0.92	Film Grade	Transparent 	Virgin	available	\N	\N	\N	\N	\N
513	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-001	0.98	momtaz	natural	Virgin	used	28	\N	\N	\N	\N
377	1st Degree	PP	25.00	1	eemw	2025-04-08	926	1D-PP-250408-926-002	\N	\N	\N	\N	used	26	\N	\N	\N	\N
558	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-001	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
559	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-002	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
560	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-003	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
561	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-004	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
562	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-005	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
563	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-006	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
564	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-007	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
565	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-008	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
566	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-009	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
567	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-010	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
568	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-011	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
569	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-012	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
570	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-013	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
571	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-014	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
572	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-015	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
573	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-016	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
574	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-017	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
575	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-018	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
576	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-019	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
577	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-020	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
578	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-021	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
579	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-022	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
580	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-023	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
581	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-024	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
582	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-025	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
583	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-026	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
584	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-027	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
585	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-028	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
586	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-029	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
587	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-030	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
542	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-005	0.92	FILM GRADE	Black	Recycled	used	36	\N	\N	\N	\N
543	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-006	0.92	FILM GRADE	Black	Recycled	used	36	\N	\N	\N	\N
548	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-001	0.92	Film Grade	Transparent 	Virgin	used	52	\N	\N	\N	\N
549	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-002	0.92	Film Grade	Transparent 	Virgin	used	53	\N	\N	\N	\N
550	1st Degree	FILLER	25.00	1	SIDOC	2025-04-15	445	1D-FIL-250415-445-003	0.92	Film Grade	Transparent 	Virgin	used	54	\N	\N	\N	\N
588	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-031	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
589	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-032	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
590	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-033	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
591	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-034	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
592	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-035	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
593	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-036	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
594	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-037	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
595	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-038	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
596	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-039	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
597	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-040	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
598	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-041	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
599	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-042	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
600	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-043	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
601	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-044	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
602	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-045	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
603	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-046	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
604	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-047	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
605	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-048	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
606	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-049	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
607	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-050	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
608	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-051	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
609	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-052	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
610	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-053	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
611	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-054	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
612	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-055	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
613	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-056	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
614	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-057	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
615	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-058	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
616	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-059	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
617	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-060	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
618	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-061	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
619	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-062	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
620	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-063	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
621	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-064	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
622	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-065	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
623	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-066	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
624	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-067	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
625	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-068	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
626	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-069	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
627	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-070	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
628	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-071	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
629	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-072	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
630	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-073	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
631	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-074	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
632	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-075	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
633	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-076	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
634	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-077	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
635	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-078	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
636	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-079	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
637	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-080	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
638	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-081	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
639	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-082	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
640	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-083	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
641	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-084	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
642	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-085	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
643	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-086	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
644	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-087	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
645	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-088	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
646	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-089	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
647	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-090	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
648	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-091	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
649	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-092	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
650	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-093	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
651	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-094	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
652	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-095	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
653	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-096	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
654	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-097	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
655	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-098	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
656	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-099	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
657	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-100	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
658	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-101	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
659	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-102	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
660	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-103	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
661	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-104	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
662	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-105	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
663	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-106	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
664	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-107	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
665	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-108	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
666	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-109	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
667	2nd Degree	EE	25.00	1	Royal 	2025-04-17	875	2D-EE-250417-875-110	0.92	Film grade	black 	Recycled	available	\N	\N	\N	\N	\N
668	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-001	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
669	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-002	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
670	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-003	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
671	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-004	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
672	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-005	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
673	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-006	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
674	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-007	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
675	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-008	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
676	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-009	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
677	2nd Degree	LDPE (recycled)	25.00	1	Plastic	2025-04-17	624	2D-LDP(RE-250417-624-010	0.92	grade	trans	Recycled	available	\N	\N	\N	\N	\N
518	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-006	0.98	momtaz	natural	Virgin	used	29	\N	\N	\N	\N
526	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-014	0.98	momtaz	natural	Virgin	used	31	\N	\N	\N	\N
527	1st Degree	HDPE	25.00	1	mezo	2025-04-14	123	1D-HDP-250414-123-015	0.98	momtaz	natural	Virgin	used	31	\N	\N	\N	\N
379	1st Degree	PP	25.00	1	eemw	2025-04-08	926	1D-PP-250408-926-004	\N	\N	\N	\N	used	31	\N	\N	\N	\N
380	1st Degree	PP	25.00	1	eemw	2025-04-08	926	1D-PP-250408-926-005	\N	\N	\N	\N	used	31	\N	\N	\N	\N
678	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-001	0.92	film grade	transparent 	Recycled	available	\N	\N	\N	\N	\N
679	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-002	0.92	film grade	transparent 	Recycled	available	\N	\N	\N	\N	\N
681	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-004	0.92	film grade	transparent 	Recycled	available	\N	\N	\N	\N	\N
682	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-005	0.92	film grade	transparent 	Recycled	available	\N	\N	\N	\N	\N
683	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-006	0.92	film grade	transparent 	Recycled	available	\N	\N	\N	\N	\N
684	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-007	0.92	film grade	transparent 	Recycled	available	\N	\N	\N	\N	\N
685	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-008	0.92	film grade	transparent 	Recycled	available	\N	\N	\N	\N	\N
688	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-001	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
689	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-002	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
690	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-003	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
691	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-004	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
692	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-005	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
693	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-006	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
694	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-007	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
695	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-008	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
696	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-009	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
697	2nd Degree	HDPP	25.00	1	SIDPEC	2025-05-04	682	2D-HDP-250504-682-010	0.92	grade	light	Recycled	available	\N	\N	\N	\N	\N
546	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-009	0.92	FILM GRADE	Black	Recycled	used	35	\N	\N	\N	\N
547	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-010	0.92	FILM GRADE	Black	Recycled	used	35	\N	\N	\N	\N
545	2nd Degree	HDPP	25.00	1	Qatar Petrochemical 	2025-04-15	969	2D-HDP-250415-969-008	0.92	FILM GRADE	Black	Recycled	used	35	\N	\N	\N	\N
698	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-001	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
699	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-002	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
700	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-003	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
701	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-004	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
702	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-005	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
703	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-006	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
704	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-007	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
705	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-008	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
706	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-009	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
707	1st Degree	LDPE	25.00	1	EEMW	2025-05-04	518	1D-LDP-250504-518-010	0.92	Film Grade	transparent	Virgin	available	\N	\N	\N	\N	\N
708	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-001	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
709	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-002	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
710	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-003	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
711	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-004	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
712	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-005	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
713	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-006	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
714	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-007	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
715	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-008	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
716	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-009	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
717	1st Degree	PP	25.00	1	EEMW	2025-05-04	768	1D-PP-250504-768-010	0.92	grade	trans	Virgin	available	\N	\N	\N	\N	\N
680	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-003	0.92	film grade	transparent 	Recycled	used	37	\N	\N	\N	\N
718	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-001	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
719	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-002	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
720	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-003	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
721	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-004	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
722	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-005	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
723	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-006	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
724	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-007	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
725	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-008	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
726	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-009	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
727	1st Degree	LLDPE AAB	25.00	1	Sabic	2025-05-17	938	1D-LLDAAB-250517-938-010	0.92	Grade A	transparent 	Virgin	available	\N	\N	\N	\N	\N
686	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-009	0.92	film grade	transparent 	Recycled	used	38	\N	\N	\N	\N
687	2nd Degree	PP (recycled)	25.00	1	Zebra	2025-04-30	101	2D-PP(RE-250430-101-010	0.92	film grade	transparent 	Recycled	used	38	\N	\N	\N	\N
728	1st Degree	PLASTIC ROLL	35.00	1	yousserrf	2025-05-17	614	1D-PLAROL-250517-614-001	0.92	A	tran	Virgin	available	\N	\N	\N	\N	\N
729	1st Degree	PLASTIC ROLL	35.00	1	yousserrf	2025-05-17	614	1D-PLAROL-250517-614-002	0.92	A	tran	Virgin	available	\N	\N	\N	\N	\N
730	1st Degree	PLASTIC ROLL	35.00	1	yousserrf	2025-05-17	614	1D-PLAROL-250517-614-003	0.92	A	tran	Virgin	available	\N	\N	\N	\N	\N
731	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-001	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
732	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-002	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
733	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-003	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
734	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-004	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
735	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-005	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
736	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-006	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
737	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-007	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
738	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-008	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
739	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-009	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
740	2nd Degree	EE	25.00	1	SIPEC	2025-05-22	895	2D-EE-250522-895-010	0.92	a	TRANS	Recycled	available	\N	\N	\N	\N	\N
743	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-003	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
744	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-004	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
745	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-005	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
746	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-006	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
747	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-007	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
748	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-008	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
749	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-009	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
750	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-010	0.92	b	trans	Recycled	available	\N	\N	\N	\N	\N
742	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-002	0.92	b	trans	Recycled	used	39	\N	\N	\N	\N
741	2nd Degree	PP (recycled)	25.00	1	EEMW	2025-05-22	657	2D-PP(RE-250522-657-001	0.92	b	trans	Recycled	used	39	\N	\N	\N	\N
751	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-001	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
752	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-002	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
753	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-003	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
754	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-004	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
755	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-005	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
756	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-006	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
757	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-007	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
758	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-008	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
759	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-009	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
760	2nd Degree	LDPE (recycled)	25.00	1	Ethydco	2025-05-24	955	2D-LDP(RE-250524-955-010	0.92	A	Transparent	Recycled	available	\N	\N	\N	\N	\N
761	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-001	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
762	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-002	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
763	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-003	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
764	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-004	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
765	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-005	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
766	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-006	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
767	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-007	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
768	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-008	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
769	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-009	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
770	1st Degree	PP	25.00	1	EEMW	2025-05-24	145	1D-PP-250524-145-010	0.92	A	Transparent 	Virgin	available	\N	\N	\N	\N	\N
771	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-001	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
772	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-002	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
773	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-003	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
774	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-004	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
775	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-005	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
776	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-006	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
777	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-007	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
778	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-008	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
779	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-009	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
780	1st Degree	PP	25.00	1	ABC Plastics	2025-05-27	string	1D-PP-250527-string-010	0.92	A	TRANS	Virgin	available	\N	\N	\N	10.00	10.00
781	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-001	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
782	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-002	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
783	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-003	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
784	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-004	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
785	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-005	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
786	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-006	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
787	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-007	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
788	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-008	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
789	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-009	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
790	1st Degree	HDPE	25.00	1	SIDEVC	2025-05-27	290	1D-HDP-250527-290-010	0.92	A	brown	Virgin	available	\N	\N	\N	25.00	25.00
791	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-001	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
792	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-002	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
793	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-003	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
794	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-004	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
795	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-005	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
796	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-006	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
797	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-007	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
798	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-008	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
799	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-009	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
800	1st Degree	FRESKA	25.00	1	EEMW	2025-06-01	909	1D-FRE-250601-909-010	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
801	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-001	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
802	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-002	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
803	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-003	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
804	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-004	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
805	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-005	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
806	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-006	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
807	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-007	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
808	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-008	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
809	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-009	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
810	2nd Degree	LDPE (recycled)	25.00	1	SIDEC	2025-06-02	929	2D-LDP(RE-250602-929-010	0.92	A	trans	Recycled	available	\N	\N	\N	10.00	10.00
811	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-001	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
812	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-002	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
813	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-003	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
814	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-004	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
815	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-005	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
816	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-006	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
817	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-007	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
818	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-008	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
819	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-009	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
820	1st Degree	LDPE	25.00	1	Abo taleb	2025-06-12	209	1D-LDP-250612-209-010	0.92	A	trans	Virgin	available	\N	\N	\N	10.00	10.00
821	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-001	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
822	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-002	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
823	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-003	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
824	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-004	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
825	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-005	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
826	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-006	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
827	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-007	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
828	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-008	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
829	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-009	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
830	1st Degree	LDPE	25.00	1	EEMW	2025-06-16	241	1D-LDP-250616-241-010	0.92	A	transparent 	Virgin	available	\N	\N	\N	10.00	10.00
831	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-001	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
832	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-002	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
833	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-003	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
834	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-004	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
835	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-005	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
836	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-006	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
837	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-007	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
838	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-008	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
839	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-009	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
840	1st Degree	LLDPE BSB	25.00	1	EEMW	2025-06-16	437	1D-LLDBSB-250616-437-010	0.92	A	tran	Virgin	available	\N	\N	\N	10.00	10.00
841	2nd Degree	LDPE (recycled)	25.00	1	EEMW	2025-06-22	372	2D-LDP(RE-250622-372-001	0.92	B	Brown	Recycled	available	\N	\N	\N	3.00	3.00
842	2nd Degree	LDPE (recycled)	25.00	1	EEMW	2025-06-22	372	2D-LDP(RE-250622-372-002	0.92	B	Brown	Recycled	available	\N	\N	\N	3.00	3.00
843	2nd Degree	LDPE (recycled)	25.00	1	EEMW	2025-06-22	372	2D-LDP(RE-250622-372-003	0.92	B	Brown	Recycled	available	\N	\N	\N	3.00	3.00
844	2nd Degree	LDPE (recycled)	25.00	1	EEMW	2025-06-22	372	2D-LDP(RE-250622-372-004	0.92	B	Brown	Recycled	available	\N	\N	\N	3.00	3.00
845	2nd Degree	LDPE (recycled)	25.00	1	EEMW	2025-06-22	372	2D-LDP(RE-250622-372-005	0.92	B	Brown	Recycled	available	\N	\N	\N	3.00	3.00
846	2nd Degree	LDPE (recycled)	25.00	1	SIDEP	2025-06-22	595	2D-LDP(RE-250622-595-001	0.92	b	brown	Recycled	available	\N	\N	\N	10.00	10.00
847	2nd Degree	LDPE (recycled)	25.00	1	SIDEP	2025-06-22	595	2D-LDP(RE-250622-595-002	0.92	b	brown	Recycled	available	\N	\N	\N	10.00	10.00
848	2nd Degree	LDPE (recycled)	25.00	1	SIDEP	2025-06-22	595	2D-LDP(RE-250622-595-003	0.92	b	brown	Recycled	available	\N	\N	\N	10.00	10.00
849	2nd Degree	LDPE (recycled)	25.00	1	SIDEP	2025-06-22	595	2D-LDP(RE-250622-595-004	0.92	b	brown	Recycled	available	\N	\N	\N	10.00	10.00
850	2nd Degree	LDPE (recycled)	25.00	1	SIDEP	2025-06-22	595	2D-LDP(RE-250622-595-005	0.92	b	brown	Recycled	available	\N	\N	\N	10.00	10.00
851	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-001	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
852	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-002	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
853	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-003	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
854	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-004	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
855	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-005	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
856	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-006	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
857	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-007	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
858	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-008	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
859	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-009	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
860	1st Degree	LLDPE AAB	25.00	1	EEMW	2025-06-25	446	1D-LLDAAB-250625-446-010	0.92	A	Transparent	Virgin	available	\N	\N	\N	10.00	10.00
861	1st Degree	40X11	500.00	1	Ging	2025-06-26	768	1D-40X-250626-768-001	0.92	A	Alum	Virgin	available	\N	\N	\N	220000.00	220000.00
862	1st Degree	40X11	500.00	1	Ging	2025-06-26	768	1D-40X-250626-768-002	0.92	A	Alum	Virgin	available	\N	\N	\N	220000.00	220000.00
863	1st Degree	40X11	500.00	1	Ging	2025-06-26	768	1D-40X-250626-768-003	0.92	A	Alum	Virgin	available	\N	\N	\N	220000.00	220000.00
864	1st Degree	40X11	500.00	1	Ging	2025-06-26	768	1D-40X-250626-768-004	0.92	A	Alum	Virgin	available	\N	\N	\N	220000.00	220000.00
865	1st Degree	40X11	500.00	1	gin	2025-06-26	468	1D-40X-250626-468-001	3	a	trab	Virgin	available	\N	\N	\N	10.00	10.00
866	1st Degree	40X11	500.00	1	gin	2025-06-26	468	1D-40X-250626-468-002	3	a	trab	Virgin	available	\N	\N	\N	10.00	10.00
867	1st Degree	40X11	500.00	1	gin	2025-06-26	468	1D-40X-250626-468-003	3	a	trab	Virgin	available	\N	\N	\N	10.00	10.00
868	1st Degree	40X11	500.00	1	gin	2025-06-26	468	1D-40X-250626-468-004	3	a	trab	Virgin	available	\N	\N	\N	10.00	10.00
\.


--
-- Data for Name: inventory_orders; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.inventory_orders (id, group_id, received_date, unit_price, quantity, total_price, supplier, category, material_type, created_at, updated_at) FROM stdin;
1	string	2025-05-27	10.00	10	100.00	ABC Plastics	1st Degree	PP	2025-05-27 19:39:02.069276	2025-05-27 19:39:02.069276
2	290	2025-05-27	25.00	10	250.00	SIDEVC	1st Degree	HDPE	2025-05-27 19:48:23.073909	2025-05-27 19:48:23.073909
3	909	2025-06-01	10.00	10	100.00	EEMW	1st Degree	FRESKA	2025-06-01 14:21:19.404407	2025-06-01 14:21:19.404407
4	929	2025-06-02	10.00	10	100.00	SIDEC	2nd Degree	LDPE (recycled)	2025-06-02 12:41:33.765503	2025-06-02 12:41:33.765503
5	209	2025-06-12	10.00	10	100.00	Abo taleb	1st Degree	LDPE	2025-06-12 13:15:41.696371	2025-06-12 13:15:41.696371
6	241	2025-06-16	10.00	10	100.00	EEMW	1st Degree	LDPE	2025-06-16 17:37:39.361429	2025-06-16 17:37:39.361429
7	437	2025-06-16	10.00	10	100.00	EEMW	1st Degree	LLDPE BSB	2025-06-16 17:37:59.234849	2025-06-16 17:37:59.234849
8	372	2025-06-22	3.00	5	15.00	EEMW	2nd Degree	LDPE (recycled)	2025-06-22 18:28:05.237894	2025-06-22 18:28:05.237894
9	595	2025-06-22	10.00	5	50.00	SIDEP	2nd Degree	LDPE (recycled)	2025-06-22 18:31:36.554148	2025-06-22 18:31:36.554148
10	446	2025-06-25	10.00	10	100.00	EEMW	1st Degree	LLDPE AAB	2025-06-25 18:46:37.08146	2025-06-25 18:46:37.08146
11	768	2025-06-26	220000.00	4	880000.00	Ging	1st Degree	40X11	2025-06-26 19:10:56.771267	2025-06-26 19:10:56.771267
12	468	2025-06-26	10.00	4	40.00	gin	1st Degree	40X11	2025-06-26 19:11:44.901616	2025-06-26 19:11:44.901616
\.


--
-- Data for Name: invoices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.invoices (id, invoice_number, customer_account_id, job_order_id, client_name, invoice_date, due_date, po_reference, subtotal, tax_percentage, tax_amount, total_amount, amount_paid, outstanding_balance, payment_status, invoice_status, notes, custom_fields, created_at, updated_at) FROM stdin;
7	INV-2025-000002	5	48	Budget Bags Ltd	2025-06-19	2025-07-19	45841	3600.00	10.00	360.00	3960.00	0.00	3960.00	unpaid	draft	no	\N	2025-06-19 17:09:07.410652	2025-06-19 17:09:07.410652
8	INV-2025-000003	5	45	Budget Bags Ltd	2025-06-19	2025-07-19	1422	3600.00	10.00	360.00	3960.00	0.00	3960.00	unpaid	draft	\N	\N	2025-06-19 17:14:36.421472	2025-06-19 17:14:36.421472
9	INV-2025-000004	3	57	test	2025-06-19	2025-07-19	1452	40.00	10.00	4.00	44.00	0.00	44.00	unpaid	draft	quicklyyy	\N	2025-06-19 17:25:35.663778	2025-06-19 17:25:35.663778
10	INV-2025-000005	3	57	test	2025-06-19	2025-07-19	1452	40.00	10.00	4.00	44.00	0.00	44.00	unpaid	draft	quicklyyy	\N	2025-06-19 17:25:46.533532	2025-06-19 17:25:46.533532
11	INV-2025-000006	3	57	test	2025-06-19	2025-07-19	1452	40.00	10.00	4.00	44.00	0.00	44.00	unpaid	draft	quicklyyy	\N	2025-06-19 17:26:05.699339	2025-06-19 17:26:05.699339
12	INV-2025-000007	3	57	test	2025-06-19	2025-07-19	1452	40.00	10.00	4.00	44.00	0.00	44.00	unpaid	draft	quicklyyy	\N	2025-06-19 17:26:14.336382	2025-06-19 17:26:14.336382
13	INV-2025-000008	4	51	xyz	2025-06-19	2025-07-19	58631	2000.00	11.00	220.00	2220.00	0.00	2220.00	unpaid	draft	\N	\N	2025-06-19 17:30:28.078873	2025-06-19 17:30:28.078873
14	INV-2025-000009	4	46	xyz	2025-06-19	2025-07-19	36914	12200.00	10.00	1220.00	13420.00	0.00	13420.00	unpaid	draft	\N	\N	2025-06-19 17:37:19.373498	2025-06-19 17:37:19.373498
16	INV-2025-000011	4	43	xyz	2025-06-19	2025-07-19	14852	24444.00	10.00	2444.40	26888.40	0.00	26888.40	unpaid	draft	\N	\N	2025-06-19 18:00:16.50589	2025-06-19 18:00:16.50589
18	INV-2025-000013	7	52	Zebra	2025-06-19	2025-07-19	951357	10000.00	14.00	1400.00	11400.00	0.00	11400.00	unpaid	draft	\N	\N	2025-06-19 18:18:03.716471	2025-06-19 18:18:03.716471
20	INV-2025-000015	8	49	Fashion House Co	2025-06-19	2025-07-19	5645	2500.00	10.00	250.00	2750.00	0.00	2750.00	unpaid	draft	\N	\N	2025-06-19 18:34:30.250829	2025-06-19 18:34:30.250829
23	INV-2025-000018	12	53	ytdd	2025-06-19	2025-07-19	963	100000.00	14.00	14000.00	114000.00	0.00	114000.00	unpaid	draft	\N	\N	2025-06-19 19:12:44.136404	2025-06-19 19:12:44.136404
6	INV-2025-000001	1	55	Nike	2025-06-18	2025-07-18	1247	1464.00	14.00	204.96	1668.96	1317.00	351.96	partial	draft	string	\N	2025-06-18 16:48:06.838055	2025-06-18 16:48:06.838055
15	INV-2025-000010	4	44	xyz	2025-06-19	2025-07-19	3694	24444.00	2.00	488.88	24932.88	4444.00	20488.88	partial	draft	\N	\N	2025-06-19 17:40:29.620002	2025-06-19 17:40:29.620002
19	INV-2025-000014	8	50	Fashion House Co	2025-06-19	2025-07-19	987654	2500.00	11.00	275.00	2775.00	500.00	2275.00	partial	draft	\N	\N	2025-06-19 18:27:40.615902	2025-06-19 18:27:40.615902
17	INV-2025-000012	6	54	www	2025-06-19	2025-07-19	789456	1000000.00	14.00	140000.00	1140000.00	10881.00	1129119.00	partial	draft	\N	\N	2025-06-19 18:08:01.210134	2025-06-19 18:08:01.210134
21	INV-2025-000016	10	41	APPLE	2025-06-19	2025-07-19	5444	1000.00	14.00	140.00	1140.00	400.00	740.00	partial	draft	string	\N	2025-06-19 18:49:15.877747	2025-06-19 18:49:15.877747
24	INV-2025-000019	1	59	Nike	2025-06-25	2025-07-25	1234	100000.00	14.00	14000.00	114000.00	500.00	113500.00	partial	draft	\N	\N	2025-06-25 19:36:21.488977	2025-06-25 19:36:21.488977
22	INV-2025-000017	11	42	adam	2025-06-19	2025-07-19	851521	20000.00	10.00	2000.00	22000.00	1689.00	20311.00	partial	draft	\N	\N	2025-06-19 19:08:28.584684	2025-06-19 19:08:28.584684
\.


--
-- Data for Name: job_order_bags; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_bags (id, job_order_id, bag_size, quantity) FROM stdin;
1	1	60x70cm	100
2	7	60x70cm	100
\.


--
-- Data for Name: job_order_cardboards; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_cardboards (id, job_order_id, size, quantity) FROM stdin;
\.


--
-- Data for Name: job_order_clips; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_clips (id, job_order_id, clip_type, quantity, weight) FROM stdin;
1	4	Metal	5000	0
2	4	Plastic	5000	0
3	5	Metal	5000	0
4	5	Plastic	5000	0
5	6	Metal	4000	0
6	6	Plastic	4000	0
\.


--
-- Data for Name: job_order_component_attributes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_component_attributes (id, job_order_component_id, key, value, job_order_id) FROM stdin;
1	1	color	Black	\N
2	1	Packaging	1Litre	\N
3	1	quantity	2	\N
4	2	color	Black	\N
5	2	Packaging	1Litre	\N
6	2	quantity	2	\N
7	17	Lenght 	30cm	30
8	17	Width	20cm	30
9	18	Length 	100m	30
10	18	Width	48mm	30
11	18	Core Size	3inch	30
12	20	size	10x20	31
13	21	Width	50cm	31
14	21	Length 	50cm	31
15	21	Thickness	23microns	31
16	22	liters	2	31
17	23	Lenght 	30cm	33
18	23	Width	20cm	33
19	24	Length 	100m	33
20	24	Width	48mm	33
21	24	Core Size	3inch	33
22	25	liters	2	33
23	26	Lenght 	30cm	36
24	26	Width	20cm	36
25	27	Length 	100m	36
26	27	Width	48mm	36
27	27	Core Size	3inch	36
28	28	liters	2	36
29	29	Lenght 	30cm	37
30	29	Width	20cm	37
31	30	Length 	100m	37
32	30	Width	48mm	37
33	30	Core Size	3inch	37
34	31	size	10x20	38
35	32	Width	50cm	38
36	32	Length 	50cm	38
37	32	Thickness	23microns	38
38	33	Length 	100m	39
39	33	Width	48mm	39
40	33	Core Size	3inch	39
41	35	size	10x20	40
42	36	Width	50cm	40
43	36	Length 	50cm	40
44	36	Thickness	23microns	40
45	37	liters	2	40
\.


--
-- Data for Name: job_order_components; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_components (id, job_order_id, material_name, type, quantity, deducted) FROM stdin;
1	10	FlexoInk	water-based	0.00	f
2	11	FlexoInk	water-based	0.00	f
3	12	clips	metal	0.00	f
4	12	clips	plastic	0.00	f
5	13	Carton	Packaging	0.00	f
6	21	clips	metal	0.00	f
7	24	Carton	60x10	1.00	f
8	24	Sizer	M	10.00	f
9	25	Carton	60x10	1.00	f
10	25	Sizer	M	10.00	f
11	26	Carton	60x10	1.00	f
12	26	Sizer	M	10.00	f
13	27	Carton	60x10	1.00	f
14	27	Sizer	M	10.00	f
15	28	Carton	60x10	1.00	f
17	30	Carton 	CardBoard	1.00	t
18	30	OPP Tape	Brown	1.00	t
19	30	Sizer	M	100.00	t
16	29	Carton	60x10	1.00	t
20	31	Carton	60x10	1.00	t
21	31	Scotch 	PE	1.00	t
22	31	Ink	Water-Based	0.00	t
23	33	Carton 	CardBoard	1.00	f
24	33	OPP Tape	Brown	1.00	f
25	33	Ink	Water-Based	0.00	f
26	36	Carton 	CardBoard	1.00	t
27	36	OPP Tape	Brown	1.00	t
28	36	Ink	Water-Based	0.00	t
29	37	Carton 	CardBoard	1.00	t
30	37	OPP Tape	Brown	1.00	t
31	38	Carton	60x10	1.00	t
32	38	Scotch 	PE	1.00	t
33	39	OPP Tape	Brown	1.00	t
34	39	Sizer	L	10.00	t
35	40	Carton	60x10	1.00	f
36	40	Scotch 	PE	1.00	f
37	40	Ink	Water-Based	0.00	f
38	41	Sizer	M	10.00	f
39	59	Sizer	M	10.00	f
\.


--
-- Data for Name: job_order_inks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_inks (id, job_order_id, color, liters) FROM stdin;
1	1	Blue	5
2	7	Blue	5
\.


--
-- Data for Name: job_order_machines; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_machines (id, job_order_id, machine_type, machine_id) FROM stdin;
1	1	blowing_film	BF-001
2	1	printing	PRT-010
3	1	cutting	CUT-007
4	2	injection	IM-001
5	3	injection	IM-001
6	4	injection	IM-001
7	5	injection	IM-001
8	6	injection	IM-001
9	7	blowing_film	BF-001
10	7	printing	PRT-010
11	7	cutting	CUT-007
12	8	Blowing Film	BF-001
13	8	printing	P-001
14	8	cutting	C-001
15	9	Blowing Film	BF-001
16	9	printing	P-001
17	9	cutting	C-001
18	10	Blowing Film	BF-001
19	10	printing	P-001
20	10	cutting	C-001
21	11	Blowing Film	BF-001
22	11	printing	P-001
23	11	cutting	C-001
24	12	Injection Molding	IM-001
25	13	Injection Molding	IM-001
26	14	Injection Molding	IM-001
27	15	Injection Molding	IM-001
28	16	Printing	P-001
29	16	Cutting	C-001
30	16	Blowing Film	BF-001
31	17	Injection Molding	IM-001
32	18	Injection Molding	IM-001
33	19	Injection Molding	IM-001
34	20	Injection Molding	IM-001
35	21	Injection Molding	IM-001
36	22	Injection Molding	IM-001
37	23	Blowing Film	BF-001
38	23	Printing	P-001
39	23	Cutting	C-001
40	24	Injection Molding	IM-001
41	25	Injection Molding	IM-001
42	26	Injection Molding	IM-001
43	27	Injection Molding	IM-001
44	27	Injection Molding	IM-001
45	27	Injection Molding	IM-001
46	27	Injection Molding	IM-001
47	27	Injection Molding	IM-001
48	27	Injection Molding	IM-001
49	27	Injection Molding	IM-001
50	28	Blowing Film	BF-001
51	28	Printing	P-001
52	28	Cutting	C-001
53	29	Injection Molding	IM-001
54	28	Blowing Film	BF-001
55	30	Injection Molding	IM-001
56	29	Injection Molding	IM-001
57	31	Blowing Film	BF-002
58	31	Printing	P-001
59	31	Cutting	C-001
60	31	Blowing Film	BF-003
61	31	Cutting	C-002
62	31	Blowing Film	BF-003
63	31	Blowing Film	BF-001
64	31	Printing	P-001
65	31	Cutting	C-001
66	31	Cutting	C-002
67	32	Blowing Film	BF-002
68	32	Blowing Film	BF-002
69	33	Blowing Film	BF-004
70	33	Printing	P-002
71	33	Cutting	C-003
72	34	Blowing Film	BF-004
73	34	Printing	P-002
74	34	Cutting	C-003
75	34	Blowing Film	BF-004
76	34	Printing	P-002
77	34	Cutting	C-003
78	35	Blowing Film	BF-004
79	35	Blowing Film	BF-004
80	36	Cutting	C-004
81	36	Printing	P-002
82	36	Blowing Film	BF-004
83	36	Cutting	C-004
84	36	Printing	P-002
85	36	Blowing Film	BF-004
86	37	Blowing Film	BF-002
87	37	Printing	P-002
88	37	Cutting	C-003
89	37	Blowing Film	BF-002
90	37	Printing	P-002
91	37	Cutting	C-003
92	38	Injection Molding	IM-001
93	38	Injection Molding	IM-001
94	39	Injection Molding	IM-002
95	39	Injection Molding	IM-002
96	40	Blowing Film	BF-004
97	40	Printing	P-003
98	40	Cutting	C-004
99	41	Injection Molding	IM-003
100	42	Blowing Film	BF-004
101	42	Printing	P-003
102	42	Cutting	C-004
103	43	Injection Molding	IM-003
104	44	Injection Molding	IM-003
105	45	Blowing Film	BF-004
106	45	Printing	P-004
107	45	Cutting	C-004
108	46	Injection Molding	IM-003
109	47	Injection Molding	IM-003
110	48	Blowing Film	BF-004
111	48	Printing	P-004
112	48	Cutting	C-004
113	49	Injection Molding	IM-003
114	50	Injection Molding	IM-003
115	51	Injection Molding	IM-003
116	52	Injection Molding	IM-003
117	52	Injection Molding	IM-003
118	53	Blowing Film	BF-004
119	53	Printing	P-003
120	53	Cutting	C-004
121	53	Blowing Film	BF-005
122	53	Blowing Film	BF-004
123	53	Blowing Film	BF-005
124	53	Printing	P-003
125	53	Cutting	C-004
126	54	Blowing Film	BF-006
127	54	Printing	P-004
128	54	Cutting	C-005
129	54	Blowing Film	BF-007
130	54	Printing	P-005
131	54	Cutting	C-006
132	54	Blowing Film	BF-006
133	54	Printing	P-004
134	54	Cutting	C-005
135	55	Blowing Film	BF-007
136	55	Printing	P-005
137	55	Cutting	C-006
138	56	Blowing Film	BF-007
139	56	Printing	P-005
140	56	Cutting	C-006
141	57	Injection Molding	IM-004
142	58	Injection Molding	IM-004
143	59	Injection Molding	IM-004
144	60	Blowing Film	BF-007
\.


--
-- Data for Name: job_order_materials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_materials (id, job_order_id, material_type, percentage, calculated_weight, degree) FROM stdin;
1	1	PP	0	0	\N
2	1	HDPE	0	0	\N
3	4	PP	40	42	\N
4	4	HDPE	60	63	\N
5	4	PP	0	0	\N
6	4	HDPE	0	0	\N
7	5	PP	40	42	\N
8	5	HDPE	60	63	\N
9	5	PP	0	0	\N
10	5	HDPE	0	0	\N
11	6	PP	60	277.2	\N
12	6	HDPE	40	184.8	\N
13	7	PP	40	66654	\N
14	7	HDPE	40	66654	\N
15	7	LDPE	20	33327	\N
16	8	PP	80	4.79136	\N
17	8	HDPE	20	1.19784	\N
18	9	PP	80	4.79136	\N
19	9	HDPE	20	1.19784	\N
20	10	PP	80	4.79136	\N
21	10	HDPE	20	1.19784	\N
22	11	PP	20	1.19784	\N
23	11	HDPE	80	4.79136	\N
24	12	LDPE	40	1.26	\N
25	12	PP	40	1.26	\N
26	12	HDPE	20	0.63	\N
27	13	PP	20	0.735	\N
28	13	HDPE	40	1.47	\N
29	13	LDPE	40	1.47	\N
30	14	PP	20	4.2	\N
31	14	HDPE	80	16.8	\N
32	15	PP	20	3.1500000000000004	\N
33	15	HDPE	80	12.600000000000001	\N
34	16	PP	20	6.182400000000001	\N
35	16	HDPE	80	24.729600000000005	\N
36	17	PP	20	1.26	\N
37	17	HDPE	80	5.04	\N
38	18	PP	20	1.9119240000000002	\N
39	18	HDPE	80	7.647696000000001	\N
40	19	PP	80	2.418864	\N
41	19	HDPE	20	0.604716	\N
42	20	HDPE	20	3.4917120000000006	\N
43	20	PP	80	13.966848000000002	\N
44	21	PP	20	0.063	\N
45	21	HDPE	80	0.252	\N
46	22	PP	20	17.682	\N
47	22	HDPE	80	70.728	\N
48	23	HDPE	20	1.6359889291200003	\N
49	23	HDPE	80	6.543955716480001	\N
50	24	HDPE	10	12.035625000000001	\N
51	24	PP	90	108.320625	\N
52	25	PP	73	122.64	\N
53	25	HDPE	27	45.36	\N
54	26	HDPE	50	52.5	\N
55	26	PP	50	52.5	\N
56	27	HDPE	50	52.5	\N
57	27	PP	50	52.5	\N
58	28	PP	80	133.53984000000003	\N
59	28	HDPE	20	33.38496000000001	\N
60	29	HDPE	100	84.75915	\N
61	30	HDPE	100	37.8	\N
62	31	HDPE	50	57.96000000000001	\N
63	31	PP	50	57.96000000000001	\N
64	32	LLDPE (recycled)	100	52.5	\N
65	33	PP	100	19.320000000000004	\N
66	34	HDPE	100	27.434400000000004	\N
67	35	HDPP	100	52.5	\N
68	36	LLDPE (recycled)	50	28.980000000000004	\N
69	36	HDPP	50	28.980000000000004	\N
70	37	PP (recycled)	100	23.184000000000005	\N
71	38	PP (recycled)	100	42	\N
72	39	EE	50	26.25	\N
73	39	PP (recycled)	50	26.25	\N
74	40	EE	20	9.50544	\N
75	40	HDPP	40	19.01088	\N
76	40	LLDPE (recycled)	40	19.01088	\N
77	41	FILLER	100	36.75	\N
78	42	HDPE	100	11.592000000000002	\N
79	50	EE	50	65.625	2nd Degree
80	50	HDPE	50	65.625	1st Degree
81	51	FILLER	50	15.75	1st Degree
82	51	PP (recycled)	25	7.875	2nd Degree
83	51	LLDPE (recycled)	25	7.875	2nd Degree
84	52	FILLER	100	10.5	1st Degree
85	53	FILLER	100	19.320000000000004	1st Degree
86	54	FILLER	100	19.320000000000004	1st Degree
87	55	FILLER	100	0.22135679999999996	1st Degree
88	56	FRESKA	100	0.021	1st Degree
89	57	LDPE	100	0.4305	1st Degree
90	58	LLDPE AAB	100	315	1st Degree
91	59	PP	100	367.5	1st Degree
92	60	40X11	100	10.5	1st Degree
\.


--
-- Data for Name: job_order_sizers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_sizers (id, job_order_id, size_label, quantity) FROM stdin;
1	4	S	3000
2	5	S	3000
3	6	S	1000
\.


--
-- Data for Name: job_order_solvents; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_solvents (id, job_order_id, color, liters) FROM stdin;
1	1	red	2
2	7	red	2
\.


--
-- Data for Name: job_order_tapes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_order_tapes (id, job_order_id, tape_size, quantity) FROM stdin;
1	1	2 cm	10
2	7	2 cm	10
\.


--
-- Data for Name: job_orders; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_orders (id, order_id, client_name, product, model, raw_degree, order_quantity, length_cm, width_cm, micron_mm, density, flap_cm, gusset1_cm, gusset2_cm, unit_weight, stretch_quantity, target_weight_no_waste, target_weight_with_waste, assigned_date, operator_id, machine_type, machine_id, status, start_time, remaining_target_g, completed_at, completed_weight, total_waste_g, unit_price, total_price, notes, customer_account_id, accounting_status, progress) FROM stdin;
33	#ORD-20250504-001	kok	AB	regular poly bags	1st Degree	100000	10	10	10	0.92	0	0	0	0	0	18.400000000000002	19.320000000000004	2025-05-04 14:32:23.492904+03	37	\N	\N	pending	\N	18400	\N	0	0	\N	\N	\N	\N	pending	0.00
27	#ORD-20250414-006	NIKE	PH	WHB-14	1st Degree	10000	0	0	0	0	0	0	0	10	0	100	105	2025-04-14 14:44:51.708229+02	40	\N	IM-001	in_progress	2025-04-14 17:09:17.583532+02	3650	\N	0	0	\N	\N	\N	1	pending	96.35
30	#ORD-20250422-001	H&M	PH	WT-19	1st Degree	1000	0	0	0	0	0	0	0	36	0	36	37.8	2025-04-22 16:28:57.500751+02	40	\N	\N	in_progress	2025-04-22 15:11:22.464923+02	36000	\N	0	0	\N	\N	\N	9	pending	0.00
53	#ORD-20250603-001	ytdd	AB	regular poly bags	1st Degree	100000	10	10	10	0.92	0	0	0	0	0	18.400000000000002	19.320000000000004	2025-06-03 16:46:57.42484+03	39	\N	BF-004	in_progress	2025-06-03 13:49:49.865352+03	18400	\N	0	0	1.00	100000.00		12	pending	0.00
46	#ORD-20250527-006	xyz	PH	WT-19	2nd Degree	12200	0	0	0	0	0	0	0	12	0	146.4	153.72	2025-05-27 17:17:31.290241+03	40	\N	\N	pending	\N	146400	\N	0	0	1.00	12200.00	fridayy duee	4	pending	0.00
23	#ORD-20250414-002	hhs	AB	regular poly bags	1st Degree	321	57	26	89	0.92	0	0	0	0	0	7.7904234720000005	8.179944645600001	2025-04-14 11:47:57.266947+02	\N	\N	\N	pending	\N	7790	\N	0	0	\N	\N	\N	\N	pending	0.01
42	#ORD-20250527-002	Adam 	AB	gusset poly bags	1st Degree	10000	10	10	30	0.92	0	5	5	0	0	11.040000000000003	11.592000000000002	2025-05-27 13:54:48.434748+03	39	\N	\N	pending	\N	11040	\N	0	0	2.00	20000.00	make sure its done	11	pending	0.00
29	#ORD-20250415-002	ii	PH	WT-19	1st Degree	907	0	0	0	0	0	0	0	89	0	80.723	84.75915	2025-04-15 15:49:15.571095+02	37	\N	IM-001	completed	2025-04-22 17:39:09.520185+02	0	2025-05-06 15:51:10.873601	0	0	\N	\N	\N	\N	pending	100.00
38	#ORD-20250517-001	Adidas	PH	WHB-12	2nd Degree	40000	0	0	0	0	0	0	0	1	0	40	42	2025-05-17 16:45:51.312518+03	40	\N	IM-001	in_progress	2025-05-17 14:00:31.0509+03	27250	\N	0	0	\N	\N	\N	\N	pending	31.88
40	#ORD-20250524-001	NIke 	AB	flap poly bags	2nd Degree	10000	10	41	30	0.92	20	0	0	0	0	45.264	47.5272	2025-05-24 23:01:46.410931+03	37	\N	\N	pending	\N	45264	\N	0	0	\N	\N	\N	\N	pending	0.00
4	#ORD-20250409-004	XYZ Hangers	PH	WB-12	1st Degree	5000	0	0	0	0	0	0	0	0.02	0	100	105	2025-04-09 17:15:51.382607+02	\N	\N	\N	pending	\N	100000	\N	0	0	\N	\N	\N	\N	pending	0.00
6	#ORD-20250409-006	Zara	PH	WHB-14	1st Degree	2000	0	0	0	0	0	0	0	0.22	0	440	462	2025-04-09 17:36:52.957237+02	\N	\N	\N	pending	\N	440000	\N	0	0	\N	\N	\N	\N	pending	0.00
43	#ORD-20250527-003	xyz	PH	WT-19	2nd Degree	12222	0	0	0	0	0	0	0	12	0	146.664	153.9972	2025-05-27 17:10:19.535169+03	39	\N	\N	pending	\N	146664	\N	0	0	2.00	24444.00	need by friday!	4	pending	0.00
39	#ORD-20250522-001	LV	PH	WT-19	2nd Degree	1000	0	0	0	0	0	0	0	50	0	50	52.5	2025-05-22 18:15:54.504714+03	35	\N	IM-002	in_progress	2025-05-22 15:20:57.822144+03	50000	\N	0	0	\N	\N	\N	\N	pending	0.00
17	#ORD-20250413-006	Merc	PH	WB-14	1st Degree	20000	0	0	0	0	0	0	0	0.3	0	6	6.3	2025-04-13 19:54:32.398362+02	\N	\N	\N	pending	\N	6000	\N	0	0	\N	\N	\N	\N	pending	0.00
54	#ORD-20250603-002	www	AB	regular poly bags	1st Degree	100000	10	10	10	0.92	0	0	0	0	0	18.400000000000002	19.320000000000004	2025-06-03 20:38:00.380638+03	40	\N	BF-006	in_progress	2025-06-03 20:41:25.614575+03	18400	\N	0	0	10.00	1000000.00		6	pending	0.00
50	#ORD-20250527-010	Fashion House Co	PH	WT-19	2nd Degree	5000	0	0	0	0	0	0	0	25	0	125	131.25	2025-05-27 17:29:16.478118+03	\N	\N	\N	pending	\N	125000	\N	0	0	0.50	2500.00	Standard white hangers	8	pending	0.00
8	#ORD-20250412-001	Acme Inc	AB	flap poly bags	1st Degree	1000	30	20	50	0.92	2	0	0	0	0	5.704000000000001	5.9892	2025-04-12 20:56:20.590296+02	35	Blowing Film	BF001	pending	\N	5704	\N	0	0	\N	\N	\N	\N	pending	0.00
60	#ORD-20250626-001	Ahmed 	PR	\N	1st Degree	1000	0	0	0	0	0	0	0	10	0	10	10.5	2025-06-26 19:17:10.36557+03	37	\N	\N	pending	\N	10000	\N	0	0	200.00	200000.00		\N	pending	0.00
55	#ORD-20250618-001	nike	AB	regular poly bags	1st Degree	122	12	12	12	5	0	0	0	0	0	0.21081599999999998	0.22135679999999996	2025-06-18 16:20:15.920368+03	37	\N	\N	pending	\N	210	\N	0	0	12.00	1464.00		1	linked	0.39
36	#ORD-20250504-004	Under Armor	AB	flap poly bags	2nd Degree	100000	10	10	20	0.92	10	0	0	0	0	55.20000000000001	57.96000000000001	2025-05-04 20:46:07.162598+03	39	\N	C-004	completed	2025-05-04 18:26:53.463054+03	0	2025-05-05 14:22:54.906604	0	0	\N	\N	\N	2	pending	100.00
35	#ORD-20250504-003	TEST1	PR	\N	2nd Degree	100	0	0	0	0	0	0	0	50	0	50	52.5	2025-05-04 19:10:06.955238+03	37	\N	BF-004	completed	2025-05-04 16:47:23.883399+03	0	2025-05-04 20:38:24.790567	0	0	\N	\N	\N	\N	pending	100.00
32	#ORD-20250424-002	TEST	PR	\N	2nd Degree	1500	0	0	0	0	0	0	0	50	0	50	52.5	2025-04-24 17:05:00.787169+02	39	\N	BF-002	completed	2025-04-24 16:48:23.673035+02	0	2025-05-05 14:25:40.47689	0	0	\N	\N	\N	3	pending	100.00
13	#ORD-20250413-002	hamada	PH	WB-12	1st Degree	10000	0	0	0	0	0	0	0	0.35	0	3.5	3.675	2025-04-13 15:32:42.386103+02	39	Injection Molding	IM-001	pending	\N	3500	\N	0	0	\N	\N	\N	\N	pending	0.00
14	#ORD-20250413-003	dasani	PH	WB-12	1st Degree	100000	0	0	0	0	0	0	0	0.2	0	20	21	2025-04-13 18:14:24.483335+02	\N	\N	\N	pending	\N	20000	\N	0	0	\N	\N	\N	\N	pending	0.00
9	#ORD-20250412-002	Acme Inc	AB	flap poly bags	1st Degree	1000	30	20	50	0.92	2	0	0	0	0	5.704000000000001	5.9892	2025-04-12 20:56:43.925025+02	35	Blowing Film	BF001	pending	\N	5704	\N	0	0	\N	\N	\N	\N	pending	0.00
45	#ORD-20250527-005	Budget Bags Ltd	AB	flap poly bags	2nd Degree	2000	60	45	40	0.92	10	0	0	0	0	43.056000000000004	45.208800000000004	2025-05-27 17:12:45.214678+03	\N	\N	\N	pending	\N	43056	\N	0	0	1.80	3600.00	\N	5	pending	0.00
58	#ORD-20250623-001	adam	PH	WB-12	1st Degree	10000	0	0	0	0	0	0	0	30	0	300	315	2025-06-23 12:13:18.030196+03	39	\N	\N	pending	\N	300000	\N	0	0	10.00	100000.00		11	linked	0.00
18	#ORD-20250413-007	Dell	PH	WT-19	1st Degree	45522	0	0	0	0	0	0	0	0.2	0	9.1044	9.55962	2025-04-13 20:03:26.423909+02	\N	\N	\N	pending	\N	9104	\N	0	0	\N	\N	\N	\N	pending	0.00
20	#ORD-20250413-009	Tommy	PH	WB-12	1st Degree	55424	0	0	0	0	0	0	0	0.3	0	16.627200000000002	17.458560000000002	2025-04-13 20:16:00.165709+02	\N	\N	\N	pending	\N	16627	\N	0	0	\N	\N	\N	\N	pending	0.00
11	#ORD-20250412-004	HMC	AB	flap poly bags	1st Degree	1000	30	20	50	0.92	2	0	0	0	0	5.704000000000001	5.9892	2025-04-12 21:06:58.251133+02	35	Blowing Film	BF001	pending	\N	5704	\N	0	0	\N	\N	\N	\N	pending	0.00
12	#ORD-20250413-001	NOOR	PH	WB-12	1st Degree	10000	0	0	0	0	0	0	0	0.3	1	3	3.15	2025-04-13 13:51:44.749356+02	35	Injection Molding	IM_001	pending	\N	3000	\N	0	0	\N	\N	\N	\N	pending	0.00
1	#ORD-20250409-001	ABC Clothing	AB	regular poly bags	1st Degree	10000	50	30	25	0.92	0	0	0	0	0	69000	72450	2025-04-09 16:30:13.268544+02	\N	\N	\N	pending	\N	69000000	\N	0	0	\N	\N	\N	\N	pending	0.00
2	#ORD-20250409-002	XYZ Hangers	PH	WB-12	1st Degree	5000	0	0	0	0	0	0	0	0.02	0	100	105	2025-04-09 17:05:38.697666+02	\N	\N	\N	pending	\N	100000	\N	0	0	\N	\N	\N	\N	pending	0.00
3	#ORD-20250409-003	XYZ Hangers	PH	WB-12	1st Degree	5000	0	0	0	0	0	0	0	0.02	0	100	105	2025-04-09 17:06:50.695193+02	\N	\N	\N	pending	\N	100000	\N	0	0	\N	\N	\N	\N	pending	0.00
16	#ORD-20250413-005	UNDER ARMOR	AB	gusset poly bags	1st Degree	10000	10	60	20	0.92	0	10	10	0	0	29.440000000000005	30.912000000000006	2025-04-13 19:45:40.33353+02	\N	\N	\N	pending	\N	29440	\N	0	0	\N	\N	\N	2	pending	0.00
10	#ORD-20250412-003	Acme Inc	AB	flap poly bags	1st Degree	1000	30	20	50	0.92	2	0	0	0	0	5.704000000000001	5.9892	2025-04-12 20:59:55.373994+02	35	Blowing Film	BF001	pending	\N	5704	\N	0	0	\N	\N	\N	\N	pending	0.00
59	#ORD-20250625-001	Nike	PH	WT-19	1st Degree	10000	0	0	0	0	0	0	0	35	0	350	367.5	2025-06-25 18:54:02.756355+03	35	\N	\N	pending	\N	350000	\N	0	0	10.00	100000.00		1	linked	0.00
52	#ORD-20250602-001	Zebra	PH	WT-19	1st Degree	1000	0	0	0	0	0	0	0	10	0	10	10.5	2025-06-02 15:33:31.414393+03	37	\N	IM-003	in_progress	2025-06-02 12:35:35.520669+03	3650	\N	0	0	10.00	10000.00		7	pending	63.50
51	#ORD-20250527-011	xyz	PH	WT-19	2nd Degree	1000	0	0	0	0	0	0	0	30	0	30	31.5	2025-05-27 18:34:09.754214+03	39	\N	\N	pending	\N	30000	\N	0	0	2.00	2000.00	fridayyy	4	pending	0.00
57	#ORD-20250618-003	test	PH	WT-19	1st Degree	10	0	0	0	0	0	0	0	41	0	0.41	0.4305	2025-06-18 18:44:22.015723+03	37	\N	\N	pending	\N	410	\N	0	0	4.00	40.00		3	linked	0.00
47	#ORD-20250527-007	wyz	PH	WT-19	2nd Degree	1250	0	0	0	0	0	0	0	12	0	15	15.75	2025-05-27 17:18:41.749937+03	35	\N	\N	pending	\N	15000	\N	0	0	12.00	15000.00	quiccc	\N	pending	0.00
41	#ORD-20250527-001	Apple	PH	WT-19	1st Degree	1000	0	0	0	0	0	0	0	35	0	35	36.75	2025-05-27 13:22:08.506246+03	37	\N	\N	pending	\N	35000	\N	0	0	1.00	1000.00	\N	10	pending	0.00
22	#ORD-20250414-001	Alex	PH	WB-12	1st Degree	4210	0	0	0	0	0	0	0	20	0	84.2	88.41	2025-04-14 11:04:59.286709+02	\N	\N	\N	pending	\N	84200	\N	0	0	\N	\N	\N	\N	pending	0.00
21	#ORD-20250413-010	KIA	PH	WT-19	1st Degree	1000	0	0	0	0	0	0	0	0.3	0	0.3	0.315	2025-04-13 20:34:43.768594+02	35	Injection Molding	IM-001	pending	\N	300	\N	0	0	\N	\N	\N	\N	pending	0.00
34	#ORD-20250504-002	WOW	AB	regular poly bags	1st Degree	71000	10	20	10	0.92	0	0	0	0	0	26.128000000000004	27.434400000000004	2025-05-04 14:43:21.890906+03	35	\N	BF-004	completed	2025-05-04 11:45:54.286801+03	0	2025-05-04 13:16:14.297911	0	0	\N	\N	\N	\N	pending	100.00
31	#ORD-20250424-001	Rognta	AB	regular poly bags	1st Degree	100000	10	20	30	0.92	0	0	0	0	0	110.40000000000002	115.92000000000002	2025-04-24 14:57:44.205949+02	40	\N	BF-003	COMPLETED	2025-04-24 14:34:56.022916+02	110400	2025-05-04 14:24:15.374062	0	0	\N	\N	\N	\N	pending	0.00
15	#ORD-20250413-004	PUMA	PH	WB-12	1st Degree	50000	0	0	0	0	0	0	0	0.3	0	15	15.75	2025-04-13 19:14:01.655065+02	\N	\N	\N	pending	\N	15000	\N	0	0	\N	\N	\N	\N	pending	0.00
37	#ORD-20250514-001	hp	AB	regular poly bags	2nd Degree	40000	10	10	30	0.92	0	0	0	0	0	22.080000000000005	23.184000000000005	2025-05-14 18:27:45.07905+03	35	\N	BF-002	in_progress	2025-05-15 09:58:25.669915+03	7380	\N	0	0	\N	\N	\N	\N	pending	66.58
48	#ORD-20250527-008	Budget Bags Ltd	AB	flap poly bags	2nd Degree	2000	60	45	40	0.92	10	0	0	0	0	43.056000000000004	45.208800000000004	2025-05-27 17:19:13.517742+03	\N	\N	\N	pending	\N	43056	\N	0	0	1.80	3600.00	\N	5	pending	0.00
49	#ORD-20250527-009	Fashion House Co	PH	WT-19	2nd Degree	5000	0	0	0	0	0	0	0	25	0	125	131.25	2025-05-27 17:23:10.662884+03	\N	\N	\N	pending	\N	125000	\N	0	0	0.50	2500.00	Standard white hangers	8	pending	0.00
24	#ORD-20250414-003	utu	PH	WB-12	1st Degree	4585	0	0	0	0	0	0	0	25	0	114.625	120.35625	2025-04-14 13:22:09.279769+02	39	\N	\N	pending	\N	114625	\N	0	0	\N	\N	\N	\N	pending	0.00
25	#ORD-20250414-004	Zara	PH	WHB-12	1st Degree	8000	0	0	0	0	0	0	0	20	0	160	168	2025-04-14 14:25:23.243791+02	37	\N	\N	pending	\N	160000	\N	0	0	\N	\N	\N	\N	pending	0.00
5	#ORD-20250409-005	Nike	PH	WB-14	1st Degree	5000	0	0	0	0	0	0	0	0.02	0	100	105	2025-04-09 17:28:03.302566+02	\N	\N	\N	pending	\N	100000	\N	0	0	\N	\N	\N	1	pending	0.00
7	#ORD-20250409-007	Adidas	AB	gusset poly bags	1st Degree	23000	50	30	25	0.92	0	0	0	0	0	158700	166635	2025-04-09 18:21:18.988812+02	\N	\N	\N	pending	\N	158700000	\N	0	0	\N	\N	\N	\N	pending	0.00
19	#ORD-20250413-008	Apple	PH	WT-19	1st Degree	12520	0	0	0	0	0	0	0	0.23	0	2.8796	3.02358	2025-04-13 20:06:33.823043+02	\N	\N	\N	pending	\N	2879	\N	0	0	\N	\N	\N	10	pending	0.02
26	#ORD-20250414-005	PUMA	PH	WHB-14	1st Degree	10000	0	0	0	0	0	0	0	10	0	100	105	2025-04-14 14:28:12.960503+02	40	\N	\N	in_progress	2025-04-16 16:27:54.10192+02	10000	\N	0	0	\N	\N	\N	\N	pending	90.00
56	#ORD-20250618-002	TEST	AB	regular poly bags	1st Degree	10	10	10	10	10	0	0	0	0	0	0.02	0.021	2025-06-18 18:40:53.760325+03	35	\N	\N	pending	\N	20	\N	0	0	10.00	100.00		3	pending	0.00
44	#ORD-20250527-004	xyz	PH	WT-19	2nd Degree	12222	0	0	0	0	0	0	0	12	0	146.664	153.9972	2025-05-27 17:10:39.681762+03	39	\N	\N	pending	\N	146664	\N	0	0	2.00	24444.00	need by friday!	4	pending	0.00
\.


--
-- Data for Name: machine_production_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.machine_production_history (id, machine_id, order_id, roll_index, stage, production_weight_g, waste_weight_g, recorded_at) FROM stdin;
1	BF-002	37	6	BLOWING	50	100	2025-06-02 17:10:20.139329+03
2	P-002	37	6	PRINTING	6350	50	2025-06-02 17:14:21.353773+03
3	C-003	37	6	CUTTING	6350	50	2025-06-02 17:14:55.719308+03
4	BF-004	53	1	BLOWING	6350	500	2025-06-03 16:50:26.566721+03
5	BF-004	53	2	BLOWING	6350	100	2025-06-03 16:50:52.03721+03
6	BF-004	53	3	BLOWING	6350	\N	2025-06-03 16:51:02.383005+03
7	BF-004	53	4	BLOWING	6350	800	2025-06-03 16:51:23.115556+03
8	BF-002	37	7	BLOWING	6350	1000	2025-06-04 17:57:12.56312+03
9	BF-002	37	8	BLOWING	6350	4000	2025-06-04 18:14:16.686548+03
10	P-002	37	8	PRINTING	6350	6000	2025-06-04 18:14:34.109741+03
11	BF-006	54	1	BLOWING	6350	1000	2025-06-21 18:17:35.222822+03
\.


--
-- Data for Name: machine_production_history_ph; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.machine_production_history_ph (id, machine_id, order_id, batch_index, stage, production_weight_g, waste_weight_g, recorded_at) FROM stdin;
1	IM-003	52	1	INJECTION	1	1	2025-06-02 15:38:43.574264
2	IM-003	52	2	INJECTION	6350	100	2025-06-02 15:46:02.318683
\.


--
-- Data for Name: machine_waste; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.machine_waste (id, machine_id, job_order_id, waste_amount_g, waste_type, waste_date, waste_timestamp, recorded_by, index_number) FROM stdin;
5	IM-001	26	5000.00	injection_molding	2025-05-14	2025-05-20 18:37:17.135676	\N	2
6	IM-001	26	2000.00	injection_molding	2025-05-14	2025-05-20 18:37:17.660327	\N	3
7	IM-001	26	6000.00	injection_molding	2025-05-14	2025-05-20 18:37:17.661251	\N	4
8	IM-001	27	2000.00	injection_molding	2025-05-13	2025-05-20 18:37:17.726287	\N	3
9	IM-001	27	3000.00	injection_molding	2025-05-13	2025-05-20 18:37:17.726659	\N	4
1	BF-002	37	1000.00	blowing	2025-05-15	2025-05-20 18:37:17.749789	\N	1
23	BF-002	37	1000.00	blowing	2025-05-15	2025-05-20 18:37:17.750132	\N	2
24	BF-002	37	1000.00	blowing	2025-05-16	2025-05-20 18:37:17.750487	\N	4
25	P-002	37	1000.00	printing	2025-05-16	2025-05-20 18:37:17.750982	\N	4
26	C-003	37	1000.00	cutting	2025-05-15	2025-05-20 18:37:17.7515	\N	2
3	IM-001	38	50.00	injection_molding	2025-05-17	2025-05-20 18:37:17.75283	\N	1
33	IM-001	38	100.00	injection_molding	2025-05-17	2025-05-20 18:37:17.753182	\N	2
\.


--
-- Data for Name: machine_waste_backup; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.machine_waste_backup (id, machine_id, job_order_id, waste_amount_g, waste_type, waste_date, waste_timestamp, recorded_by) FROM stdin;
1	BF-002	37	1000.00	blowing	2025-05-15	2025-05-20 13:39:51.93905	\N
3	IM-001	38	50.00	injection_molding	2025-05-17	2025-05-20 13:39:51.960156	\N
\.


--
-- Data for Name: machines; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.machines (id, production_line, machine_type, machine_id, status, current_job_order, updated_at) FROM stdin;
12	Line 2	Blowing Film	BF-003	in_use	31	2025-05-13 18:30:18.931581+03
7	Line 1	Blowing Film	BF-001	in_use	31	2025-05-13 18:30:18.931581+03
10	Line 1	Printing	P-001	in_use	31	2025-05-13 18:30:18.931581+03
11	Line 1	Cutting	C-001	in_use	31	2025-05-13 18:30:18.931581+03
14	Line 1	Cutting	C-002	in_use	31	2025-05-13 18:30:18.931581+03
9	Line 1	Blowing Film	BF-002	in_use	37	2025-05-13 18:30:18.931581+03
17	Line 1	Printing	P-002	in_use	37	2025-05-13 18:30:18.931581+03
15	Line 1	Cutting	C-003	in_use	37	2025-05-13 18:30:18.931581+03
8	Line 2	Injection Molding	IM-001	in_use	38	2025-05-13 18:30:18.931581+03
20	Line 2	Injection Molding	IM-002	in_use	39	2025-05-22 13:02:32.805311+03
21	Line 2	Injection Molding	IM-003	in_use	52	2025-05-22 13:02:32.929999+03
13	Line 1	Blowing Film	BF-004	in_use	53	2025-05-13 18:30:18.931581+03
22	Line 1	Blowing Film	BF-005	in_use	53	2025-05-22 13:08:49.669563+03
18	Line 1	Printing	P-003	in_use	53	2025-05-22 13:02:04.399988+03
16	Line 1	Cutting	C-004	in_use	53	2025-05-13 18:30:18.931581+03
25	Line 1	Cutting	C-006	available	\N	2025-06-03 20:36:47.916123+03
26	Line 1	Cutting	C-007	available	\N	2025-06-03 20:36:48.068694+03
27	Line 1	Cutting	C-008	available	\N	2025-06-03 20:36:48.215316+03
28	Line 1	Blowing Film	BF-007	available	\N	2025-06-03 20:36:54.372521+03
29	Line 1	Blowing Film	BF-008	available	\N	2025-06-03 20:36:54.484106+03
30	Line 1	Blowing Film	BF-009	available	\N	2025-06-03 20:36:54.628766+03
31	Line 1	Printing	P-005	available	\N	2025-06-03 20:36:58.928397+03
32	Line 1	Printing	P-006	available	\N	2025-06-03 20:36:59.037604+03
33	Line 1	Printing	P-007	available	\N	2025-06-03 20:36:59.183194+03
23	Line 1	Blowing Film	BF-006	in_use	54	2025-05-24 21:34:11.671247+03
19	Line 1	Printing	P-004	in_use	54	2025-05-22 13:02:05.29814+03
24	Line 1	Cutting	C-005	in_use	54	2025-06-03 20:36:47.222498+03
34	Line 2	Injection Molding	IM-004	available	\N	2025-06-18 18:43:22.650989+03
35	Line 2	Injection Molding	IM-005	available	\N	2025-06-18 18:43:23.448334+03
36	Line 2	Injection Molding	IM-006	available	\N	2025-06-18 18:43:23.60024+03
37	Line 2	Injection Molding	IM-007	available	\N	2025-06-18 18:43:23.757705+03
\.


--
-- Data for Name: material_types; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.material_types (id, category, material_type) FROM stdin;
5	1st Degree	ZYE
6	2nd Degree	EE
7	1st Degree	MASTERBATCH
8	2nd Degree	LLDPE (recycled)
9	1st Degree	HDPE
10	1st Degree	PP
11	string	string
12	2nd Degree	HDPP
13	1st Degree	PS
15	1st Degree	PLASTIC ROLL
16	1st Degree	FRESKA
17	1st Degree	40X11
\.


--
-- Data for Name: operational_costs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.operational_costs (id, title, cost, quantity, currency, type, dynamic_fields, submission_date, created_at, updated_at) FROM stdin;
975bc10a-76b9-4075-962c-caab2f6ce81d	machine	500.00	1	USD	oper	\N	2025-06-24	2025-06-24 16:47:27.80496+03	2025-06-24 16:47:27.80496+03
\.


--
-- Data for Name: order_accounting; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.order_accounting (id, customer_account_id, job_order_id, client_name, order_amount, amount_invoiced, amount_paid, outstanding_balance, payment_status, invoice_status, order_date, first_invoice_date, last_payment_date, due_date, created_at, updated_at) FROM stdin;
7	5	48	Budget Bags Ltd	3600.00	3960.00	0.00	3600.00	unpaid	invoiced	2025-05-27 14:19:13.517742	2025-06-19 00:00:00	\N	\N	2025-06-19 15:16:59.959889	2025-06-19 15:16:59.959889
8	5	45	Budget Bags Ltd	3600.00	3960.00	0.00	3600.00	unpaid	invoiced	2025-05-27 14:12:45.214678	2025-06-19 00:00:00	\N	\N	2025-06-19 15:17:00.001025	2025-06-19 15:17:00.001025
2	3	57	test	40.00	176.00	0.00	40.00	unpaid	invoiced	2025-06-18 18:44:22.567963	2025-06-19 00:00:00	\N	\N	2025-06-18 18:44:22.567963	2025-06-18 18:44:22.567963
3	4	51	xyz	2000.00	2220.00	0.00	2000.00	unpaid	invoiced	2025-05-27 15:34:09.754214	2025-06-19 00:00:00	\N	\N	2025-06-18 18:47:03.612461	2025-06-18 18:47:03.612461
4	4	46	xyz	12200.00	13420.00	0.00	12200.00	unpaid	invoiced	2025-05-27 14:17:31.290241	2025-06-19 00:00:00	\N	\N	2025-06-18 18:47:03.61427	2025-06-18 18:47:03.61427
6	4	43	xyz	24444.00	26888.40	0.00	24444.00	unpaid	invoiced	2025-05-27 14:10:19.535169	2025-06-19 00:00:00	\N	\N	2025-06-18 18:47:03.615261	2025-06-18 18:47:03.615261
10	7	52	Zebra	10000.00	11400.00	0.00	10000.00	unpaid	invoiced	2025-06-02 12:33:31.414393	2025-06-19 00:00:00	\N	\N	2025-06-19 18:17:20.841994	2025-06-19 18:17:20.841994
12	8	49	Fashion House Co	2500.00	2750.00	0.00	2500.00	unpaid	invoiced	2025-05-27 14:23:10.662884	2025-06-19 00:00:00	\N	\N	2025-06-19 18:27:21.660121	2025-06-19 18:27:21.660121
15	12	53	ytdd	100000.00	114000.00	0.00	100000.00	unpaid	invoiced	2025-06-03 13:46:57.42484	2025-06-19 00:00:00	\N	\N	2025-06-19 19:12:24.161806	2025-06-19 19:12:24.161806
1	1	55	nike	1464.00	1668.96	1317.00	147.00	partial	invoiced	2025-06-18 16:20:15.963734	2025-06-18 00:00:00	2025-06-20 00:00:00	\N	2025-06-18 16:20:15.963734	2025-06-18 16:20:15.963734
5	4	44	xyz	24444.00	24932.88	4444.00	20000.00	partial	invoiced	2025-05-27 14:10:39.681762	2025-06-19 00:00:00	2025-06-20 00:00:00	\N	2025-06-18 18:47:03.614767	2025-06-18 18:47:03.614767
11	8	50	Fashion House Co	2500.00	2775.00	500.00	2000.00	partial	invoiced	2025-05-27 14:29:16.478118	2025-06-19 00:00:00	2025-06-20 00:00:00	\N	2025-06-19 18:27:21.657986	2025-06-19 18:27:21.657986
9	6	54	www	1000000.00	1140000.00	10881.00	989119.00	partial	invoiced	2025-06-03 17:38:00.380638	2025-06-19 00:00:00	2025-06-20 00:00:00	\N	2025-06-19 18:07:31.19436	2025-06-19 18:07:31.19436
13	10	41	APPLE	1000.00	1140.00	400.00	600.00	partial	invoiced	2025-05-27 10:22:08.506246	2025-06-19 00:00:00	2025-06-22 00:00:00	\N	2025-06-19 18:47:50.599038	2025-06-19 18:47:50.599038
16	11	58	adam	100000.00	0.00	0.00	100000.00	unpaid	not_invoiced	2025-06-23 12:13:18.052705	\N	\N	\N	2025-06-23 12:13:18.052705	2025-06-23 12:13:18.052705
17	1	59	Nike	100000.00	114000.00	500.00	99500.00	partial	invoiced	2025-06-25 18:54:02.802431	2025-06-25 00:00:00	2025-06-25 00:00:00	\N	2025-06-25 18:54:02.802431	2025-06-25 18:54:02.802431
14	11	42	adam	20000.00	22000.00	1689.00	18311.00	partial	invoiced	2025-05-27 10:54:48.434748	2025-06-19 00:00:00	2025-06-29 00:00:00	\N	2025-06-19 19:07:52.373978	2025-06-19 19:07:52.373978
\.


--
-- Data for Name: payment_allocations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.payment_allocations (id, receipt_id, customer_account_id, job_order_id, invoice_id, allocated_amount, allocation_date, notes) FROM stdin;
\.


--
-- Data for Name: payments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.payments (id, supplier_id, group_id, invoice_id, payment_method, reference_number, amount_paid, currency, payment_date, additional_fields, created_at, updated_at, supplier_name) FROM stdin;
1	4	929	1	bank	45841	50.00	USD	2025-06-12	{}	2025-06-12 15:32:28.058169	2025-06-12 15:32:28.058169	\N
5	6	11	7	bank	1254	25.00	USD	2025-06-23	{}	2025-06-23 19:23:11.23629	2025-06-23 19:23:11.23629	eemw
10	6	0	7	bank	123	20.00	USD	2025-06-23	{}	2025-06-23 19:35:17.276326	2025-06-23 19:35:17.276326	eemw
14	6	0	6	bank	369	75.00	USD	2025-06-23	{}	2025-06-23 19:38:03.332467	2025-06-23 19:38:03.332467	eemw
17	6	0	6	check	789	20.00	USD	2025-06-23	{}	2025-06-23 19:45:23.75751	2025-06-23 19:45:23.75751	eemw
18	6	0	7	bank	12	10.00	USD	2025-06-24	{}	2025-06-24 12:00:59.816158	2025-06-24 12:00:59.816158	eemw
\.


--
-- Data for Name: production_hangers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.production_hangers (id, order_id, batch_index, stage, model, injection_weight_g, packaged_weight_g, injection_weight_ts, packaged_weight_ts, metal_detect_ts, sizing_ts, plastic_clips_ts, metal_clips_ts, created_at, updated_at, waste_of_im_g, waste_of_im_ts, waste_of_metaldetect_g, waste_of_metaldetect_ts, injection_machine_id, metal_detect_machine_id) FROM stdin;
1	30	1	INJECTION	1st Degree	500	\N	2025-05-06 15:24:00.475073+03	\N	\N	\N	\N	\N	2025-05-06 15:24:00.475073+03	2025-05-06 15:24:00.475073+03	\N	\N	\N	\N	\N	\N
12	27	5	PACKAGING	WHB-14	6350	6350	2025-05-16 20:52:42.42579+03	2025-05-16 20:53:16.401359+03	\N	2025-05-16 20:52:57.909782+03	2025-05-16 20:53:02.812468+03	2025-05-16 20:53:07.583748+03	2025-05-16 20:52:42.42579+03	2025-05-16 20:53:16.401359+03	0	2025-05-16 20:52:42.42579	0	2025-05-16 20:53:16.401359	\N	\N
2	29	1	PACKAGING	WT-19	1	40723	2025-05-06 15:33:20.397038+03	2025-05-06 15:49:01.925814+03	\N	2025-05-06 15:36:42.547543+03	\N	\N	2025-05-06 15:33:20.397038+03	2025-05-06 15:49:01.925814+03	\N	\N	\N	\N	\N	\N
3	29	2	PACKAGING	WT-19	5040	40723	2025-05-06 15:50:05.504749+03	2025-05-06 15:51:10.871837+03	\N	2025-05-06 15:50:56.910995+03	\N	\N	2025-05-06 15:50:05.504749+03	2025-05-06 15:51:10.871837+03	\N	\N	\N	\N	\N	\N
13	38	1	PACKAGING	WHB-12	6400	6400	2025-05-17 17:05:01.354242+03	2025-05-17 17:07:04.463582+03	2025-05-17 17:06:05.770181+03	2025-05-17 17:06:37.130407+03	2025-05-17 17:06:42.86766+03	2025-05-17 17:06:46.110094+03	2025-05-17 17:05:01.354242+03	2025-05-17 17:07:04.463582+03	50	2025-05-17 17:05:01.354242	200	2025-05-17 17:07:04.463582	\N	\N
4	27	1	PACKAGING	WHB-14	50000	50000	2025-05-06 17:01:12.416099+03	2025-05-06 17:03:58.469385+03	\N	2025-05-06 17:03:00.307898+03	2025-05-06 17:03:23.118626+03	2025-05-06 17:03:46.441251+03	2025-05-06 17:01:12.416099+03	2025-05-06 17:03:58.469385+03	\N	\N	\N	\N	\N	\N
5	26	1	PACKAGING	WHB-14	22000	50000	2025-05-06 19:19:41.276718+03	2025-05-06 19:21:32.081123+03	\N	2025-05-06 19:20:41.117464+03	2025-05-06 19:20:49.966193+03	2025-05-06 19:20:54.598422+03	2025-05-06 19:19:41.276718+03	2025-05-06 19:21:32.081123+03	\N	\N	\N	\N	\N	\N
15	38	3	PACKAGING	WHB-12	6350	6350	2025-05-24 23:08:26.517907+03	2025-05-24 23:09:22.198523+03	2025-05-24 23:08:46.73759+03	2025-05-24 23:08:53.991016+03	2025-05-24 23:09:00.740707+03	2025-05-24 23:09:04.533327+03	2025-05-24 23:08:26.517907+03	2025-05-24 23:09:22.198523+03	50	2025-05-24 23:08:26.517907	100	2025-05-24 23:09:22.198523	\N	\N
16	26	5	INJECTION	WHB-14	6350	\N	2025-05-24 23:11:45.031606+03	\N	\N	\N	\N	\N	2025-05-24 23:11:45.031606+03	2025-05-24 23:11:45.031606+03	1000	2025-05-24 23:11:45.031606	\N	\N	\N	\N
7	27	3	PACKAGING	WHB-14	10000	15000	2025-05-13 17:42:40.081456+03	2025-05-13 17:45:47.127478+03	\N	2025-05-13 17:44:42.929589+03	2025-05-13 17:44:53.915814+03	2025-05-13 17:45:07.638325+03	2025-05-13 17:42:40.081456+03	2025-05-13 17:45:47.127478+03	2000	2025-05-13 17:42:40.081456	5000	2025-05-13 17:45:47.127478	\N	\N
14	38	2	WEIGHING	WHB-12	6400	\N	2025-05-17 17:25:41.337297+03	\N	\N	\N	\N	\N	2025-05-17 17:25:41.337297+03	2025-06-02 12:46:39.411948+03	100	2025-05-17 17:25:41.337297	\N	\N	\N	\N
17	52	1	INJECTION	WT-19	1	\N	2025-06-02 15:38:43.574264+03	\N	\N	\N	\N	\N	2025-06-02 15:38:43.574264+03	2025-06-02 15:38:43.574264+03	1	2025-06-02 15:38:43.574264	\N	\N	IM-003	\N
18	52	2	PACKAGING	WT-19	6350	6350	2025-06-02 15:46:02.318683+03	2025-06-02 15:46:32.362017+03	\N	2025-06-02 15:46:21.564717+03	\N	\N	2025-06-02 15:46:02.318683+03	2025-06-02 15:46:32.362017+03	100	2025-06-02 15:46:02.318683	1000	2025-06-02 15:46:32.362017	IM-003	\N
9	26	2	PACKAGING	WHB-14	25000	30000	2025-05-14 14:12:19.231661+03	2025-05-14 14:53:54.210043+03	\N	2025-05-14 14:19:53.788816+03	2025-05-14 14:21:20.712054+03	2025-05-14 14:21:27.704007+03	2025-05-14 14:12:19.231661+03	2025-05-14 14:53:54.210043+03	5000	2025-05-14 14:12:19.231661	\N	\N	\N	\N
6	27	2	PACKAGING	WHB-14	20000	15000	2025-05-13 17:26:26.159109+03	2025-05-14 15:15:30.305182+03	\N	2025-05-14 15:14:55.92364+03	2025-05-14 15:15:02.466784+03	2025-05-14 15:15:08.950874+03	2025-05-13 17:26:26.159109+03	2025-05-14 15:15:30.305182+03	\N	\N	\N	\N	\N	\N
8	27	4	PACKAGING	WHB-14	15000	10000	2025-05-13 17:47:13.405837+03	2025-05-14 15:16:50.480386+03	\N	2025-05-14 15:16:27.634932+03	2025-05-14 15:16:32.277594+03	2025-05-14 15:16:35.998165+03	2025-05-13 17:47:13.405837+03	2025-05-14 15:16:50.480386+03	3000	2025-05-13 17:47:13.405837	\N	\N	\N	\N
10	26	3	PACKAGING	WHB-14	10000	5000	2025-05-14 14:59:26.478231+03	2025-05-14 15:26:04.971332+03	\N	2025-05-14 15:25:32.546986+03	2025-05-14 15:25:36.943935+03	2025-05-14 15:25:43.257485+03	2025-05-14 14:59:26.478231+03	2025-05-14 15:26:04.971332+03	2000	2025-05-14 14:59:26.478231	\N	\N	\N	\N
11	26	4	PACKAGING	WHB-14	5000	5000	2025-05-14 15:43:38.175032+03	2025-05-14 15:44:27.048457+03	\N	2025-05-14 15:43:57.574035+03	2025-05-14 15:44:05.098082+03	2025-05-14 15:44:09.230478+03	2025-05-14 15:43:38.175032+03	2025-05-14 15:44:27.048457+03	6000	2025-05-14 15:43:38.175032	6000	2025-05-14 15:44:27.048457	\N	\N
\.


--
-- Data for Name: production_rolls; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.production_rolls (id, order_id, tmp_index, stage, roll_weight_g, printed_weight_g, cut_weight_g, packaged_weight_g, created_at, updated_at, roll_weight_ts, printed_weight_ts, cut_weight_ts, packaged_weight_ts, metal_detect_ts, waste_of_blowing_g, waste_of_blowing_ts, waste_of_printing_g, waste_of_printing_ts, waste_of_cutting_g, waste_of_cutting_ts, waste_of_metal_detect_g, waste_of_metal_detect_ts, blowing_machine_id, printing_machine_id, cutting_machine_id, metal_detect_machine_id) FROM stdin;
22	37	6	PACKAGING	50	6350	6350	6350	2025-06-02 14:10:20.139329+03	2025-06-02 14:15:50.116178+03	2025-06-02 14:10:20.139329+03	2025-06-02 14:14:21.353773+03	2025-06-02 14:14:55.719308+03	2025-06-02 14:15:50.116178+03	2025-06-02 14:15:26.646047+03	100	2025-06-02 14:10:20.139329	50	2025-06-02 14:14:21.353773	50	2025-06-02 14:14:55.719308	10	2025-06-02 14:15:50.116178	BF-002	P-002	C-003	\N
23	53	1	BLOWING	6350	\N	\N	\N	2025-06-03 16:50:26.566721+03	2025-06-03 16:50:26.566721+03	2025-06-03 16:50:26.566721+03	\N	\N	\N	\N	500	2025-06-03 16:50:26.566721	\N	\N	\N	\N	\N	\N	BF-004	\N	\N	\N
24	53	2	BLOWING	6350	\N	\N	\N	2025-06-03 16:50:52.03721+03	2025-06-03 16:50:52.03721+03	2025-06-03 16:50:52.03721+03	\N	\N	\N	\N	100	2025-06-03 16:50:52.03721	\N	\N	\N	\N	\N	\N	BF-004	\N	\N	\N
25	53	3	BLOWING	6350	\N	\N	\N	2025-06-03 16:51:02.383005+03	2025-06-03 16:51:02.383005+03	2025-06-03 16:51:02.383005+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	BF-004	\N	\N	\N
26	53	4	BLOWING	6350	\N	\N	\N	2025-06-03 16:51:23.115556+03	2025-06-03 16:51:23.115556+03	2025-06-03 16:51:23.115556+03	\N	\N	\N	\N	800	2025-06-03 16:51:23.115556	\N	\N	\N	\N	\N	\N	BF-004	\N	\N	\N
28	37	8	PRINTING	6350	6350	\N	\N	2025-06-04 18:14:16.686548+03	2025-06-04 18:14:34.109741+03	2025-06-04 18:14:16.686548+03	2025-06-04 18:14:34.109741+03	\N	\N	\N	4000	2025-06-04 18:14:16.686548	6000	2025-06-04 18:14:34.109741	\N	\N	\N	\N	BF-002	P-002	\N	\N
5	28	1	PACKAGING	10000	10000	10000	66000	2025-04-30 19:06:25.71001+03	2025-04-30 19:22:53.298057+03	2025-04-30 19:18:50.444531+03	2025-04-30 19:22:02.416853+03	2025-04-30 19:22:25.032794+03	2025-04-30 19:22:53.298057+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
27	37	7	PRINTING	6350	6000	\N	\N	2025-06-04 17:57:12.56312+03	2025-06-16 17:50:07.880429+03	2025-06-04 17:57:12.56312+03	2025-06-16 17:50:07.880429+03	\N	\N	\N	1000	2025-06-04 17:57:12.56312	1000	2025-06-16 17:50:07.880429	\N	\N	\N	\N	BF-002	\N	\N	\N
6	28	2	PACKAGING	80000	75000	70000	68000	2025-04-30 19:07:12.094111+03	2025-05-01 17:54:02.582235+03	2025-04-30 19:09:00.087178+03	2025-05-01 17:53:26.923193+03	2025-05-01 17:53:39.717652+03	2025-05-01 17:54:02.582235+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
29	54	1	PRINTING	6350	20000	\N	\N	2025-06-21 18:17:35.222822+03	2025-06-26 19:21:30.047318+03	2025-06-21 18:17:35.222822+03	2025-06-26 19:21:30.047318+03	\N	\N	\N	1000	2025-06-21 18:17:35.222822	1000	2025-06-26 19:21:30.047318	\N	\N	\N	\N	BF-006	\N	\N	\N
7	28	3	PACKAGING	40000	35000	34000	32920	2025-05-01 19:10:12.115165+03	2025-05-01 19:10:51.806223+03	2025-05-01 19:10:12.115165+03	2025-05-01 19:10:21.214334+03	2025-05-01 19:10:35.259753+03	2025-05-01 19:10:51.806223+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
8	28	4	BLOWING	15000	\N	\N	\N	2025-05-04 12:38:54.709395+03	2025-05-04 12:38:54.709395+03	2025-05-04 12:38:54.709395+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
9	28	5	BLOWING	10000	\N	\N	\N	2025-05-04 13:39:10.935001+03	2025-05-04 13:39:10.935001+03	2025-05-04 13:39:10.935001+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
10	34	1	PACKAGING	20000	25000	25000	26100	2025-05-04 14:47:29.130271+03	2025-05-04 11:48:34.440808+03	2025-05-04 14:47:29.130271+03	2025-05-04 11:47:54.494666+03	2025-05-04 11:48:04.635417+03	2025-05-04 11:48:34.440808+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
11	35	1	PACKAGING	20000	\N	\N	25000	2025-05-04 19:48:31.973999+03	2025-05-04 16:55:11.986917+03	2025-05-04 16:48:31.973999+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
12	35	2	PACKAGING	25000	\N	\N	25000	2025-05-04 20:38:14.814416+03	2025-05-04 17:38:24.789034+03	2025-05-04 17:38:14.814416+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
13	36	1	PACKAGING	25000	35000	25000	10000	2025-05-04 21:32:05.54061+03	2025-05-05 10:33:38.182708+03	2025-05-04 18:32:05.54061+03	\N	\N	\N	2025-05-05 10:28:17.700204+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
14	36	2	PACKAGING	25000	25000	25000	10	2025-05-04 21:50:09.022058+03	2025-05-05 10:34:49.281098+03	2025-05-04 18:50:09.022058+03	\N	\N	\N	2025-05-05 10:31:42.095635+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
15	36	3	PACKAGING	10000	10	10000	45200	2025-05-05 13:33:47.261348+03	2025-05-05 14:22:54.904963+03	2025-05-05 10:33:47.261348+03	\N	2025-05-05 13:44:13.752197+03	2025-05-05 14:22:54.904963+03	2025-05-05 14:22:28.624865+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
16	32	1	PACKAGING	10000	\N	\N	50000	2025-05-05 14:25:31.899467+03	2025-05-05 14:25:40.47544+03	2025-05-05 14:25:31.899467+03	\N	\N	2025-05-05 14:25:40.47544+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
17	37	1	PACKAGING	2000	2000	2000	2000	2025-05-15 12:59:06.918437+03	2025-05-15 13:36:44.047995+03	2025-05-15 12:59:06.918437+03	2025-05-15 13:21:34.52889+03	2025-05-15 13:35:54.682564+03	2025-05-15 13:36:44.047995+03	2025-05-15 13:36:12.224053+03	1000	2025-05-15 12:59:06.918437	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
18	37	2	CUTTING	2000	2000	2000	\N	2025-05-15 13:51:41.877122+03	2025-05-15 14:21:45.54267+03	2025-05-15 13:51:41.877122+03	2025-05-15 13:52:04.882696+03	2025-05-15 14:21:45.54267+03	\N	\N	1000	2025-05-15 13:51:41.877122	\N	\N	1000	2025-05-15 14:21:45.54267	\N	\N	\N	\N	\N	\N
19	37	3	PRINTING	50	6350	\N	\N	2025-05-16 20:00:07.662475+03	2025-05-16 20:48:13.464011+03	2025-05-16 20:00:07.662475+03	2025-05-16 20:48:13.464011+03	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
20	37	4	PACKAGING	6350	6350	6350	6350	2025-05-16 20:42:18.63663+03	2025-05-17 14:22:29.965786+03	2025-05-16 20:42:18.63663+03	2025-05-16 20:42:47.510186+03	2025-05-16 20:43:13.569772+03	2025-05-17 14:22:29.965786+03	2025-05-16 20:47:54.519663+03	1000	2025-05-16 20:42:18.63663	1000	2025-05-16 20:42:47.510186	\N	\N	50	2025-05-17 14:22:29.965786	\N	\N	\N	\N
21	37	5	CUTTING	6350	6350	6350	\N	2025-06-01 14:35:15.194406+03	2025-06-01 14:36:59.166398+03	2025-06-01 14:35:15.194406+03	2025-06-01 14:36:44.262852+03	2025-06-01 14:36:59.166398+03	\N	\N	50	2025-06-01 14:35:15.194406	50	2025-06-01 14:36:44.262852	\N	\N	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: purchase_orders; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.purchase_orders (id, group_id, supplier_id, po_number, delivery_date, quantity_ordered, unit_price, vat_percentage, additional_fields, created_at, updated_at, material_type, supplier_name) FROM stdin;
1	290	1	125548	2025-06-12	0	0.00	0.00	{}	2025-06-12 15:19:32.170019	2025-06-12 15:19:32.170019	\N	\N
2	929	4	120548	2025-06-02	10	10.00	15.00	{}	2025-06-12 15:29:44.072252	2025-06-12 15:29:44.072252	\N	\N
3	209	5	PO-209-2025-06	2025-06-12	10	10.00	0.00	{}	2025-06-12 15:44:13.594468	2025-06-12 15:44:13.594468	\N	\N
4	241	6	1234	2025-06-29	10	10.00	10.00	{}	2025-06-23 13:48:22.940728	2025-06-23 13:48:22.940728	LDPE	EEMW
5	0	6	string	2025-06-23	100	1.00	14.00	{}	2025-06-23 15:57:22.694312	2025-06-23 15:57:22.694312	LDPE	eemw
6	0	6	PO-20250623-6-001	2025-06-23	40	1.00	14.00	{}	2025-06-23 16:08:20.194121	2025-06-23 16:08:20.194121	PP	eemw
7	0	6	PO-20250623-6-002	2025-06-23	100	1.00	14.00	{}	2025-06-23 16:08:52.390045	2025-06-23 16:08:52.390045	LDPE	eemw
8	0	6	PO-20250624-6-001	2025-06-24	100	10.00	14.00	{}	2025-06-24 11:47:31.618226	2025-06-24 11:47:31.618226	PP	eemw
9	0	6	PO-20250625-6-001	2025-06-25	100	10.00	14.00	{}	2025-06-25 19:38:23.986543	2025-06-25 19:38:23.986543	pp	eemw
\.


--
-- Data for Name: raw_invoices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.raw_invoices (id, supplier_id, group_id, invoice_number, total_amount, status, invoice_date, due_date, additional_fields, created_at, updated_at, supplier_name) FROM stdin;
1	4	929	54698	100.00	partial	2025-06-12	2025-06-12	{}	2025-06-12 15:31:03.464367	2025-06-12 15:32:28.058169	\N
2	5	209	INV-209-2025-06	100.00	unpaid	2025-06-12	\N	{}	2025-06-12 15:44:13.594468	2025-06-12 15:44:13.594468	\N
6	6	0	879	100.00	partial	2025-06-23	2025-06-23	{}	2025-06-23 15:08:43.958627	2025-06-23 19:45:23.75751	eemw
7	6	0	789	100.00	partial	2025-06-23	2025-07-23	{}	2025-06-23 15:36:02.648617	2025-06-24 12:00:59.816158	eemw
\.


--
-- Data for Name: raw_materials_costs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.raw_materials_costs (id, title, cost, quantity, currency, type, dynamic_fields, submission_date, created_at, updated_at) FROM stdin;
1	pp	100.00	10	USD	raw	\N	2025-06-24	2025-06-24 14:27:23.258017+03	2025-06-24 14:27:23.258017+03
\.


--
-- Data for Name: receipts; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.receipts (id, receipt_number, customer_account_id, job_order_id, invoice_id, client_name, amount_received, payment_date, payment_method, bank_or_cash, transaction_reference, bank_name, check_number, allocated_to_order, allocated_to_invoice, notes, custom_fields, created_at, updated_at) FROM stdin;
6	RCP-2025-000001	1	55	6	Nike	500.00	2025-06-18	bank_transfer	bank	ww	qq	11	f	f	string	\N	2025-06-18 17:05:34.452984	2025-06-18 17:05:34.452984
7	RCP-2025-000002	11	42	22	adam	500.00	2025-06-20	bank_transfer	bank	string	AAIB	89135	f	f	string	\N	2025-06-20 20:18:39.958396	2025-06-20 20:18:39.958396
8	RCP-2025-000003	10	41	21	APPLE	250.00	2025-06-20	bank_transfer	bank	59421	AAIB	789456	f	f		\N	2025-06-20 21:16:11.275887	2025-06-20 21:16:11.275887
9	RCP-2025-000004	1	55	6	Nike	364.00	2025-06-20	cash	bank	8926323	huf	486	f	f		\N	2025-06-20 21:39:21.839373	2025-06-20 21:39:21.839373
10	RCP-2025-000005	1	55	6	Nike	364.00	2025-06-20	cash	bank	8926323	huf	486	f	f		\N	2025-06-20 21:39:43.19638	2025-06-20 21:39:43.19638
11	RCP-2025-000006	6	54	17	www	7853.00	2025-06-20	bank_transfer	bank	754	hh	54	f	f		\N	2025-06-20 21:47:19.062695	2025-06-20 21:47:19.062695
12	RCP-2025-000007	1	55	6	Nike	89.00	2025-06-20	bank_transfer	bank	7893	asd	154	f	f		\N	2025-06-20 22:17:31.660975	2025-06-20 22:17:31.660975
13	RCP-2025-000008	4	44	15	xyz	4444.00	2025-06-20	cash	bank	26	momes	rere	f	f		\N	2025-06-20 22:22:20.623745	2025-06-20 22:22:20.623745
14	RCP-2025-000009	8	50	19	Fashion House Co	500.00	2025-06-20	bank_transfer	bank	23123	ttt		f	f		\N	2025-06-20 22:28:49.50434	2025-06-20 22:28:49.50434
15	RCP-2025-000010	6	54	17	www	3028.00	2025-06-20	bank_transfer	bank	7893	lol		f	f		\N	2025-06-20 22:30:13.116317	2025-06-20 22:30:13.116317
16	RCP-2025-000011	10	41	21	APPLE	100.00	2025-06-20	bank_transfer	bank	789	pop	789	f	f		\N	2025-06-20 22:50:35.187541	2025-06-20 22:50:35.187541
17	RCP-2025-000012	10	41	21	APPLE	50.00	2025-06-22	bank_transfer	bank	100	HSBC	1293	f	f		\N	2025-06-22 18:35:07.657169	2025-06-22 18:35:07.657169
18	RCP-2025-000013	11	42	22	adam	1000.00	2025-06-23	bank_transfer	bank	78745	cib	78	f	f		\N	2025-06-23 12:15:13.64903	2025-06-23 12:15:13.64903
19	RCP-2025-000014	11	42	22	adam	89.00	2025-06-24	bank_transfer	bank	12	aa	12	f	f		\N	2025-06-24 11:34:35.288949	2025-06-24 11:34:35.288949
20	RCP-2025-000015	1	59	24	Nike	500.00	2025-06-25	bank_transfer	bank	123	CIB	12344	f	f		\N	2025-06-25 19:37:11.403114	2025-06-25 19:37:11.403114
21	RCP-2025-000016	11	42	22	adam	100.00	2025-06-29	bank_transfer	bank	142	cib	12	f	f		\N	2025-06-29 12:41:16.417311	2025-06-29 12:41:16.417311
\.


--
-- Data for Name: recycling_line; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.recycling_line (id, recycling_material_type, input_weight, timestamp_start, final_weight_recycled, packaging_process_timestamp, calculated_recycling_time, count_packaged_bags, status, created_at, updated_at) FROM stdin;
2	Plastic Rolls	100.000	2025-06-28 22:31:23.677955+03	10.000	2025-06-28 22:30:53.367+03	-00:00:30.310955	2	COMPLETED	2025-06-28 22:31:23.677955+03	2025-06-28 22:32:16.279559+03
3	Plastic Hangers	100.000	2025-06-28 22:35:52.701746+03	90.000	2025-06-28 22:36:10.820713+03	00:00:18.118967	5	COMPLETED	2025-06-28 22:35:52.701746+03	2025-06-28 22:36:10.820713+03
6	Poly Bags	200.000	2025-06-29 13:10:44.645699+03	100.000	2025-06-29 13:31:10.254186+03	00:20:25.608487	2	COMPLETED	2025-06-29 13:10:44.645699+03	2025-06-29 13:31:10.254186+03
1	Plastic Rolls	100.000	2025-06-28 22:30:19.733163+03	10.000	2025-06-29 14:07:50.811991+03	\N	2	COMPLETED	2025-06-28 22:30:19.733163+03	2025-06-29 14:07:50.811991+03
8	Poly Bags	50.000	2025-06-29 13:14:39.058517+03	10.000	2025-06-29 14:08:43.642927+03	00:54:04.58441	2	COMPLETED	2025-06-29 13:14:39.058517+03	2025-06-29 14:08:43.642927+03
9	Plastic Rolls	60.000	2025-06-29 13:25:40.823959+03	50.000	2025-06-29 14:20:51.752413+03	00:55:10.928454	10	COMPLETED	2025-06-29 13:25:40.823959+03	2025-06-29 14:20:51.752413+03
7	Poly Bags	50.000	2025-06-29 13:13:27.401699+03	40.000	2025-06-29 14:22:02.51984+03	01:08:35.118141	5	COMPLETED	2025-06-29 13:13:27.401699+03	2025-06-29 14:22:02.51984+03
5	Plastic Hangers	200.000	2025-06-29 13:07:49.649409+03	150.000	2025-06-29 14:29:38.678278+03	01:21:49.028869	10	COMPLETED	2025-06-29 13:07:49.649409+03	2025-06-29 14:29:38.678278+03
4	Plastic Rolls	100.000	2025-06-29 13:00:57.394089+03	90.000	2025-06-29 14:32:18.385163+03	01:31:20.991074	10	COMPLETED	2025-06-29 13:00:57.394089+03	2025-06-29 14:32:18.385163+03
\.


--
-- Data for Name: revenue_details; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.revenue_details (id, revenue_id, invoice_id, client_name, job_order_id, invoice_date, invoice_number, subtotal, total_amount, amount_paid, outstanding_balance, product, model, unit_price, order_quantity, created_at) FROM stdin;
1	1	24	Nike	59	2025-06-25	INV-2025-000019	100000.00	114000.00	500.00	113500.00	PH	WT-19	10.00	10000	2025-06-28 16:52:06.979108
2	1	22	adam	42	2025-06-19	INV-2025-000017	20000.00	22000.00	1589.00	20411.00	AB	gusset poly bags	2.00	10000	2025-06-28 16:52:06.979108
3	1	23	ytdd	53	2025-06-19	INV-2025-000018	100000.00	114000.00	0.00	114000.00	AB	regular poly bags	1.00	100000	2025-06-28 16:52:06.979108
4	1	18	Zebra	52	2025-06-19	INV-2025-000013	10000.00	11400.00	0.00	11400.00	PH	WT-19	10.00	1000	2025-06-28 16:52:06.979108
5	1	20	Fashion House Co	49	2025-06-19	INV-2025-000015	2500.00	2750.00	0.00	2750.00	PH	WT-19	0.50	5000	2025-06-28 16:52:06.979108
6	1	19	Fashion House Co	50	2025-06-19	INV-2025-000014	2500.00	2775.00	500.00	2275.00	PH	WT-19	0.50	5000	2025-06-28 16:52:06.979108
7	1	21	APPLE	41	2025-06-19	INV-2025-000016	1000.00	1140.00	400.00	740.00	PH	WT-19	1.00	1000	2025-06-28 16:52:06.979108
8	1	16	xyz	43	2025-06-19	INV-2025-000011	24444.00	26888.40	0.00	26888.40	PH	WT-19	2.00	12222	2025-06-28 16:52:06.979108
9	1	17	www	54	2025-06-19	INV-2025-000012	1000000.00	1140000.00	10881.00	1129119.00	AB	regular poly bags	10.00	100000	2025-06-28 16:52:06.979108
10	1	8	Budget Bags Ltd	45	2025-06-19	INV-2025-000003	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 16:52:06.979108
11	1	15	xyz	44	2025-06-19	INV-2025-000010	24444.00	24932.88	4444.00	20488.88	PH	WT-19	2.00	12222	2025-06-28 16:52:06.979108
12	1	14	xyz	46	2025-06-19	INV-2025-000009	12200.00	13420.00	0.00	13420.00	PH	WT-19	1.00	12200	2025-06-28 16:52:06.979108
13	1	13	xyz	51	2025-06-19	INV-2025-000008	2000.00	2220.00	0.00	2220.00	PH	WT-19	2.00	1000	2025-06-28 16:52:06.979108
14	1	12	test	57	2025-06-19	INV-2025-000007	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 16:52:06.979108
15	1	11	test	57	2025-06-19	INV-2025-000006	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 16:52:06.979108
16	1	10	test	57	2025-06-19	INV-2025-000005	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 16:52:06.979108
17	1	9	test	57	2025-06-19	INV-2025-000004	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 16:52:06.979108
18	1	7	Budget Bags Ltd	48	2025-06-19	INV-2025-000002	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 16:52:06.979108
19	1	6	Nike	55	2025-06-18	INV-2025-000001	1464.00	1668.96	1317.00	351.96	AB	regular poly bags	12.00	122	2025-06-28 16:52:06.979108
20	2	24	Nike	59	2025-06-25	INV-2025-000019	100000.00	114000.00	500.00	113500.00	PH	WT-19	10.00	10000	2025-06-28 18:37:27.655073
21	2	22	adam	42	2025-06-19	INV-2025-000017	20000.00	22000.00	1589.00	20411.00	AB	gusset poly bags	2.00	10000	2025-06-28 18:37:27.655073
22	2	23	ytdd	53	2025-06-19	INV-2025-000018	100000.00	114000.00	0.00	114000.00	AB	regular poly bags	1.00	100000	2025-06-28 18:37:27.655073
23	2	18	Zebra	52	2025-06-19	INV-2025-000013	10000.00	11400.00	0.00	11400.00	PH	WT-19	10.00	1000	2025-06-28 18:37:27.655073
24	2	20	Fashion House Co	49	2025-06-19	INV-2025-000015	2500.00	2750.00	0.00	2750.00	PH	WT-19	0.50	5000	2025-06-28 18:37:27.655073
25	2	19	Fashion House Co	50	2025-06-19	INV-2025-000014	2500.00	2775.00	500.00	2275.00	PH	WT-19	0.50	5000	2025-06-28 18:37:27.655073
26	2	21	APPLE	41	2025-06-19	INV-2025-000016	1000.00	1140.00	400.00	740.00	PH	WT-19	1.00	1000	2025-06-28 18:37:27.655073
27	2	16	xyz	43	2025-06-19	INV-2025-000011	24444.00	26888.40	0.00	26888.40	PH	WT-19	2.00	12222	2025-06-28 18:37:27.655073
28	2	17	www	54	2025-06-19	INV-2025-000012	1000000.00	1140000.00	10881.00	1129119.00	AB	regular poly bags	10.00	100000	2025-06-28 18:37:27.655073
29	2	8	Budget Bags Ltd	45	2025-06-19	INV-2025-000003	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:37:27.655073
30	2	15	xyz	44	2025-06-19	INV-2025-000010	24444.00	24932.88	4444.00	20488.88	PH	WT-19	2.00	12222	2025-06-28 18:37:27.655073
31	2	14	xyz	46	2025-06-19	INV-2025-000009	12200.00	13420.00	0.00	13420.00	PH	WT-19	1.00	12200	2025-06-28 18:37:27.655073
32	2	13	xyz	51	2025-06-19	INV-2025-000008	2000.00	2220.00	0.00	2220.00	PH	WT-19	2.00	1000	2025-06-28 18:37:27.655073
33	2	12	test	57	2025-06-19	INV-2025-000007	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:27.655073
34	2	11	test	57	2025-06-19	INV-2025-000006	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:27.655073
35	2	10	test	57	2025-06-19	INV-2025-000005	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:27.655073
36	2	9	test	57	2025-06-19	INV-2025-000004	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:27.655073
37	2	7	Budget Bags Ltd	48	2025-06-19	INV-2025-000002	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:37:27.655073
38	2	6	Nike	55	2025-06-18	INV-2025-000001	1464.00	1668.96	1317.00	351.96	AB	regular poly bags	12.00	122	2025-06-28 18:37:27.655073
39	3	24	Nike	59	2025-06-25	INV-2025-000019	100000.00	114000.00	500.00	113500.00	PH	WT-19	10.00	10000	2025-06-28 18:37:31.537236
40	3	22	adam	42	2025-06-19	INV-2025-000017	20000.00	22000.00	1589.00	20411.00	AB	gusset poly bags	2.00	10000	2025-06-28 18:37:31.537236
41	3	23	ytdd	53	2025-06-19	INV-2025-000018	100000.00	114000.00	0.00	114000.00	AB	regular poly bags	1.00	100000	2025-06-28 18:37:31.537236
42	3	18	Zebra	52	2025-06-19	INV-2025-000013	10000.00	11400.00	0.00	11400.00	PH	WT-19	10.00	1000	2025-06-28 18:37:31.537236
43	3	20	Fashion House Co	49	2025-06-19	INV-2025-000015	2500.00	2750.00	0.00	2750.00	PH	WT-19	0.50	5000	2025-06-28 18:37:31.537236
44	3	19	Fashion House Co	50	2025-06-19	INV-2025-000014	2500.00	2775.00	500.00	2275.00	PH	WT-19	0.50	5000	2025-06-28 18:37:31.537236
45	3	21	APPLE	41	2025-06-19	INV-2025-000016	1000.00	1140.00	400.00	740.00	PH	WT-19	1.00	1000	2025-06-28 18:37:31.537236
46	3	16	xyz	43	2025-06-19	INV-2025-000011	24444.00	26888.40	0.00	26888.40	PH	WT-19	2.00	12222	2025-06-28 18:37:31.537236
47	3	17	www	54	2025-06-19	INV-2025-000012	1000000.00	1140000.00	10881.00	1129119.00	AB	regular poly bags	10.00	100000	2025-06-28 18:37:31.537236
48	3	8	Budget Bags Ltd	45	2025-06-19	INV-2025-000003	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:37:31.537236
49	3	15	xyz	44	2025-06-19	INV-2025-000010	24444.00	24932.88	4444.00	20488.88	PH	WT-19	2.00	12222	2025-06-28 18:37:31.537236
50	3	14	xyz	46	2025-06-19	INV-2025-000009	12200.00	13420.00	0.00	13420.00	PH	WT-19	1.00	12200	2025-06-28 18:37:31.537236
51	3	13	xyz	51	2025-06-19	INV-2025-000008	2000.00	2220.00	0.00	2220.00	PH	WT-19	2.00	1000	2025-06-28 18:37:31.537236
52	3	12	test	57	2025-06-19	INV-2025-000007	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:31.537236
53	3	11	test	57	2025-06-19	INV-2025-000006	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:31.537236
54	3	10	test	57	2025-06-19	INV-2025-000005	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:31.537236
55	3	9	test	57	2025-06-19	INV-2025-000004	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:31.537236
56	3	7	Budget Bags Ltd	48	2025-06-19	INV-2025-000002	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:37:31.537236
57	3	6	Nike	55	2025-06-18	INV-2025-000001	1464.00	1668.96	1317.00	351.96	AB	regular poly bags	12.00	122	2025-06-28 18:37:31.537236
58	4	24	Nike	59	2025-06-25	INV-2025-000019	100000.00	114000.00	500.00	113500.00	PH	WT-19	10.00	10000	2025-06-28 18:37:53.291279
59	4	22	adam	42	2025-06-19	INV-2025-000017	20000.00	22000.00	1589.00	20411.00	AB	gusset poly bags	2.00	10000	2025-06-28 18:37:53.291279
60	4	23	ytdd	53	2025-06-19	INV-2025-000018	100000.00	114000.00	0.00	114000.00	AB	regular poly bags	1.00	100000	2025-06-28 18:37:53.291279
61	4	18	Zebra	52	2025-06-19	INV-2025-000013	10000.00	11400.00	0.00	11400.00	PH	WT-19	10.00	1000	2025-06-28 18:37:53.291279
62	4	20	Fashion House Co	49	2025-06-19	INV-2025-000015	2500.00	2750.00	0.00	2750.00	PH	WT-19	0.50	5000	2025-06-28 18:37:53.291279
63	4	19	Fashion House Co	50	2025-06-19	INV-2025-000014	2500.00	2775.00	500.00	2275.00	PH	WT-19	0.50	5000	2025-06-28 18:37:53.291279
64	4	21	APPLE	41	2025-06-19	INV-2025-000016	1000.00	1140.00	400.00	740.00	PH	WT-19	1.00	1000	2025-06-28 18:37:53.291279
65	4	16	xyz	43	2025-06-19	INV-2025-000011	24444.00	26888.40	0.00	26888.40	PH	WT-19	2.00	12222	2025-06-28 18:37:53.291279
66	4	17	www	54	2025-06-19	INV-2025-000012	1000000.00	1140000.00	10881.00	1129119.00	AB	regular poly bags	10.00	100000	2025-06-28 18:37:53.291279
67	4	8	Budget Bags Ltd	45	2025-06-19	INV-2025-000003	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:37:53.291279
68	4	15	xyz	44	2025-06-19	INV-2025-000010	24444.00	24932.88	4444.00	20488.88	PH	WT-19	2.00	12222	2025-06-28 18:37:53.291279
69	4	14	xyz	46	2025-06-19	INV-2025-000009	12200.00	13420.00	0.00	13420.00	PH	WT-19	1.00	12200	2025-06-28 18:37:53.291279
70	4	13	xyz	51	2025-06-19	INV-2025-000008	2000.00	2220.00	0.00	2220.00	PH	WT-19	2.00	1000	2025-06-28 18:37:53.291279
71	4	12	test	57	2025-06-19	INV-2025-000007	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:53.291279
72	4	11	test	57	2025-06-19	INV-2025-000006	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:53.291279
73	4	10	test	57	2025-06-19	INV-2025-000005	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:53.291279
74	4	9	test	57	2025-06-19	INV-2025-000004	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:37:53.291279
75	4	7	Budget Bags Ltd	48	2025-06-19	INV-2025-000002	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:37:53.291279
76	4	6	Nike	55	2025-06-18	INV-2025-000001	1464.00	1668.96	1317.00	351.96	AB	regular poly bags	12.00	122	2025-06-28 18:37:53.291279
77	5	24	Nike	59	2025-06-25	INV-2025-000019	100000.00	114000.00	500.00	113500.00	PH	WT-19	10.00	10000	2025-06-28 18:38:02.410674
78	5	22	adam	42	2025-06-19	INV-2025-000017	20000.00	22000.00	1589.00	20411.00	AB	gusset poly bags	2.00	10000	2025-06-28 18:38:02.410674
79	5	23	ytdd	53	2025-06-19	INV-2025-000018	100000.00	114000.00	0.00	114000.00	AB	regular poly bags	1.00	100000	2025-06-28 18:38:02.410674
80	5	18	Zebra	52	2025-06-19	INV-2025-000013	10000.00	11400.00	0.00	11400.00	PH	WT-19	10.00	1000	2025-06-28 18:38:02.410674
81	5	20	Fashion House Co	49	2025-06-19	INV-2025-000015	2500.00	2750.00	0.00	2750.00	PH	WT-19	0.50	5000	2025-06-28 18:38:02.410674
82	5	19	Fashion House Co	50	2025-06-19	INV-2025-000014	2500.00	2775.00	500.00	2275.00	PH	WT-19	0.50	5000	2025-06-28 18:38:02.410674
83	5	21	APPLE	41	2025-06-19	INV-2025-000016	1000.00	1140.00	400.00	740.00	PH	WT-19	1.00	1000	2025-06-28 18:38:02.410674
84	5	16	xyz	43	2025-06-19	INV-2025-000011	24444.00	26888.40	0.00	26888.40	PH	WT-19	2.00	12222	2025-06-28 18:38:02.410674
85	5	17	www	54	2025-06-19	INV-2025-000012	1000000.00	1140000.00	10881.00	1129119.00	AB	regular poly bags	10.00	100000	2025-06-28 18:38:02.410674
86	5	8	Budget Bags Ltd	45	2025-06-19	INV-2025-000003	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:38:02.410674
87	5	15	xyz	44	2025-06-19	INV-2025-000010	24444.00	24932.88	4444.00	20488.88	PH	WT-19	2.00	12222	2025-06-28 18:38:02.410674
88	5	14	xyz	46	2025-06-19	INV-2025-000009	12200.00	13420.00	0.00	13420.00	PH	WT-19	1.00	12200	2025-06-28 18:38:02.410674
89	5	13	xyz	51	2025-06-19	INV-2025-000008	2000.00	2220.00	0.00	2220.00	PH	WT-19	2.00	1000	2025-06-28 18:38:02.410674
90	5	12	test	57	2025-06-19	INV-2025-000007	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:02.410674
91	5	11	test	57	2025-06-19	INV-2025-000006	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:02.410674
92	5	10	test	57	2025-06-19	INV-2025-000005	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:02.410674
93	5	9	test	57	2025-06-19	INV-2025-000004	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:02.410674
94	5	7	Budget Bags Ltd	48	2025-06-19	INV-2025-000002	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:38:02.410674
95	5	6	Nike	55	2025-06-18	INV-2025-000001	1464.00	1668.96	1317.00	351.96	AB	regular poly bags	12.00	122	2025-06-28 18:38:02.410674
96	6	24	Nike	59	2025-06-25	INV-2025-000019	100000.00	114000.00	500.00	113500.00	PH	WT-19	10.00	10000	2025-06-28 18:38:04.109459
97	6	22	adam	42	2025-06-19	INV-2025-000017	20000.00	22000.00	1589.00	20411.00	AB	gusset poly bags	2.00	10000	2025-06-28 18:38:04.109459
98	6	23	ytdd	53	2025-06-19	INV-2025-000018	100000.00	114000.00	0.00	114000.00	AB	regular poly bags	1.00	100000	2025-06-28 18:38:04.109459
99	6	18	Zebra	52	2025-06-19	INV-2025-000013	10000.00	11400.00	0.00	11400.00	PH	WT-19	10.00	1000	2025-06-28 18:38:04.109459
100	6	20	Fashion House Co	49	2025-06-19	INV-2025-000015	2500.00	2750.00	0.00	2750.00	PH	WT-19	0.50	5000	2025-06-28 18:38:04.109459
101	6	19	Fashion House Co	50	2025-06-19	INV-2025-000014	2500.00	2775.00	500.00	2275.00	PH	WT-19	0.50	5000	2025-06-28 18:38:04.109459
102	6	21	APPLE	41	2025-06-19	INV-2025-000016	1000.00	1140.00	400.00	740.00	PH	WT-19	1.00	1000	2025-06-28 18:38:04.109459
103	6	16	xyz	43	2025-06-19	INV-2025-000011	24444.00	26888.40	0.00	26888.40	PH	WT-19	2.00	12222	2025-06-28 18:38:04.109459
104	6	17	www	54	2025-06-19	INV-2025-000012	1000000.00	1140000.00	10881.00	1129119.00	AB	regular poly bags	10.00	100000	2025-06-28 18:38:04.109459
105	6	8	Budget Bags Ltd	45	2025-06-19	INV-2025-000003	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:38:04.109459
106	6	15	xyz	44	2025-06-19	INV-2025-000010	24444.00	24932.88	4444.00	20488.88	PH	WT-19	2.00	12222	2025-06-28 18:38:04.109459
107	6	14	xyz	46	2025-06-19	INV-2025-000009	12200.00	13420.00	0.00	13420.00	PH	WT-19	1.00	12200	2025-06-28 18:38:04.109459
108	6	13	xyz	51	2025-06-19	INV-2025-000008	2000.00	2220.00	0.00	2220.00	PH	WT-19	2.00	1000	2025-06-28 18:38:04.109459
109	6	12	test	57	2025-06-19	INV-2025-000007	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:04.109459
110	6	11	test	57	2025-06-19	INV-2025-000006	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:04.109459
111	6	10	test	57	2025-06-19	INV-2025-000005	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:04.109459
112	6	9	test	57	2025-06-19	INV-2025-000004	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:38:04.109459
113	6	7	Budget Bags Ltd	48	2025-06-19	INV-2025-000002	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:38:04.109459
114	6	6	Nike	55	2025-06-18	INV-2025-000001	1464.00	1668.96	1317.00	351.96	AB	regular poly bags	12.00	122	2025-06-28 18:38:04.109459
115	7	24	Nike	59	2025-06-25	INV-2025-000019	100000.00	114000.00	500.00	113500.00	PH	WT-19	10.00	10000	2025-06-28 18:50:01.676932
116	7	22	adam	42	2025-06-19	INV-2025-000017	20000.00	22000.00	1589.00	20411.00	AB	gusset poly bags	2.00	10000	2025-06-28 18:50:01.676932
117	7	23	ytdd	53	2025-06-19	INV-2025-000018	100000.00	114000.00	0.00	114000.00	AB	regular poly bags	1.00	100000	2025-06-28 18:50:01.676932
118	7	18	Zebra	52	2025-06-19	INV-2025-000013	10000.00	11400.00	0.00	11400.00	PH	WT-19	10.00	1000	2025-06-28 18:50:01.676932
119	7	20	Fashion House Co	49	2025-06-19	INV-2025-000015	2500.00	2750.00	0.00	2750.00	PH	WT-19	0.50	5000	2025-06-28 18:50:01.676932
120	7	19	Fashion House Co	50	2025-06-19	INV-2025-000014	2500.00	2775.00	500.00	2275.00	PH	WT-19	0.50	5000	2025-06-28 18:50:01.676932
121	7	21	APPLE	41	2025-06-19	INV-2025-000016	1000.00	1140.00	400.00	740.00	PH	WT-19	1.00	1000	2025-06-28 18:50:01.676932
122	7	16	xyz	43	2025-06-19	INV-2025-000011	24444.00	26888.40	0.00	26888.40	PH	WT-19	2.00	12222	2025-06-28 18:50:01.676932
123	7	17	www	54	2025-06-19	INV-2025-000012	1000000.00	1140000.00	10881.00	1129119.00	AB	regular poly bags	10.00	100000	2025-06-28 18:50:01.676932
124	7	8	Budget Bags Ltd	45	2025-06-19	INV-2025-000003	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:50:01.676932
125	7	15	xyz	44	2025-06-19	INV-2025-000010	24444.00	24932.88	4444.00	20488.88	PH	WT-19	2.00	12222	2025-06-28 18:50:01.676932
126	7	14	xyz	46	2025-06-19	INV-2025-000009	12200.00	13420.00	0.00	13420.00	PH	WT-19	1.00	12200	2025-06-28 18:50:01.676932
127	7	13	xyz	51	2025-06-19	INV-2025-000008	2000.00	2220.00	0.00	2220.00	PH	WT-19	2.00	1000	2025-06-28 18:50:01.676932
128	7	12	test	57	2025-06-19	INV-2025-000007	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:50:01.676932
129	7	11	test	57	2025-06-19	INV-2025-000006	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:50:01.676932
130	7	10	test	57	2025-06-19	INV-2025-000005	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:50:01.676932
131	7	9	test	57	2025-06-19	INV-2025-000004	40.00	44.00	0.00	44.00	PH	WT-19	4.00	10	2025-06-28 18:50:01.676932
132	7	7	Budget Bags Ltd	48	2025-06-19	INV-2025-000002	3600.00	3960.00	0.00	3960.00	AB	flap poly bags	1.80	2000	2025-06-28 18:50:01.676932
133	7	6	Nike	55	2025-06-18	INV-2025-000001	1464.00	1668.96	1317.00	351.96	AB	regular poly bags	12.00	122	2025-06-28 18:50:01.676932
\.


--
-- Data for Name: revenues; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.revenues (id, report_name, period_type, period_start_date, period_end_date, year, month, quarter, total_revenue, total_invoices, raw_materials_costs, operational_costs, general_costs, depreciation_costs, unexpected_costs, total_costs, profit, net_profit, profit_margin, net_profit_margin, generated_at, updated_at, status, notes) FROM stdin;
1	test	monthly	2025-06-01	2025-06-30	\N	\N	\N	19631.00	19	100.00	500.00	1000.00	250.00	500.00	2350.00	19031.00	17281.00	96.94	88.03	2025-06-28 16:52:06.974785	2025-06-28 16:52:06.974785	active	\N
2	Monthly_Report_1751125047674	monthly	2025-06-01	2025-06-30	2025	6	\N	19631.00	19	100.00	500.00	1000.00	250.00	500.00	2350.00	19031.00	17281.00	96.94	88.03	2025-06-28 18:37:27.653299	2025-06-28 18:37:27.653299	active	\N
3	Monthly_Report_1751125051600	monthly	2025-06-01	2025-06-30	2025	6	\N	19631.00	19	100.00	500.00	1000.00	250.00	500.00	2350.00	19031.00	17281.00	96.94	88.03	2025-06-28 18:37:31.535144	2025-06-28 18:37:31.535144	active	\N
4	Monthly_Report_1751125073373	monthly	2025-06-01	2025-06-30	2025	6	\N	19631.00	19	100.00	500.00	1000.00	250.00	500.00	2350.00	19031.00	17281.00	96.94	88.03	2025-06-28 18:37:53.289019	2025-06-28 18:37:53.289019	active	\N
5	Quarterly_Report_1751125082491	quarterly	2025-04-01	2025-06-30	2025	\N	2	19631.00	19	100.00	500.00	1000.00	250.00	500.00	2350.00	19031.00	17281.00	96.94	88.03	2025-06-28 18:38:02.408351	2025-06-28 18:38:02.408351	active	\N
6	Yearly_Report_1751125084190	yearly	2025-01-01	2025-12-31	2025	\N	\N	19631.00	19	100.00	500.00	1000.00	250.00	500.00	2350.00	19031.00	17281.00	96.94	88.03	2025-06-28 18:38:04.106684	2025-06-28 18:38:04.106684	active	\N
7	Custom_Report_1751125801232	custom	2025-06-01	2025-06-28	\N	\N	\N	19631.00	19	100.00	500.00	1000.00	250.00	500.00	2350.00	19031.00	17281.00	96.94	88.03	2025-06-28 18:50:01.141448	2025-06-28 18:50:01.141448	active	\N
8	Monthly_Report_1751806412918	monthly	2025-07-01	2025-07-31	2025	7	\N	0.00	0	0.00	0.00	0.00	0.00	0.00	0.00	0.00	0.00	0.00	0.00	2025-07-06 15:53:32.537432	2025-07-06 15:53:32.537432	active	\N
\.


--
-- Data for Name: storage_management; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.storage_management (id, order_id, client_name, product, model, order_quantity, size_specs, status, storage_date, shipping_date, stored_by, shipped_by, notes) FROM stdin;
2	35	TEST1	PR	\N	100	0.0*0.0*0.0	stored	2025-05-19 16:54:09.740253	\N	eemw	\N	string
1	34	WOW	AB	regular poly bags	71000	10.0*20.0*10.0	shipped	2025-05-19 15:55:16.57411	2025-05-19 17:28:05.433522	eemw	eemw	string | Shipping note: string
3	36	Under Armor	AB	flap poly bags	100000	10.0*10.0*20.0	shipped	2025-05-19 18:55:01.524501	2025-05-19 19:01:50.88636	eemw	eemw	 | Shipping note: 
4	32	TEST	PR	\N	1500	0.0*0.0*0.0	shipped	2025-05-19 19:03:47.362643	2025-05-19 19:04:17.729343	eemw	eemw	 | Shipping note: 
\.


--
-- Data for Name: supplier_accounts; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.supplier_accounts (id, group_id, supplier_name, supplier_code, contact_email, contact_phone, contact_name, currency, payment_terms, outstanding_balance, additional_fields, created_at, updated_at) FROM stdin;
1	0	string	string	string	string	string	USD	string	0.00	{}	2025-06-23 12:06:12.391418	2025-06-23 12:06:12.391418
2	0	tesst	test	test	test	tess	USD	string	0.00	{}	2025-06-23 12:06:26.959436	2025-06-23 12:06:26.959436
4	0	tesst	12354	test@gmail.com	01000000	tess	USD	string	0.00	{}	2025-06-23 12:07:12.867675	2025-06-23 12:07:12.867675
5	0	Nike	4561	nike@gmail.com	01000245601	mohamed	USD	30	0.00	{}	2025-06-23 12:27:33.326723	2025-06-23 12:27:33.326723
7	0	SIDEVC	1548	test1@gmail.com	12345	HUS	USD	30	0.00	{}	2025-06-23 14:26:30.852096	2025-06-23 14:26:30.852096
6	0	eemw	123	eemw@gmail.com	0111212	eemwtst1	USD	30	50.00	{}	2025-06-23 13:34:23.476734	2025-06-24 12:00:59.816158
\.


--
-- Data for Name: unexpected_costs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.unexpected_costs (id, title, cost, quantity, currency, type, dynamic_fields, submission_date, created_at, updated_at) FROM stdin;
1	machine	500.00	1	USD	oper	\N	2025-06-24	2025-06-24 16:48:10.954923+03	2025-06-24 16:48:10.954923+03
\.


--
-- Data for Name: used_materials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.used_materials (id, barcode, job_order_id, activation_time) FROM stdin;
\.


--
-- Data for Name: withdrawals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.withdrawals (id, material_type, withdrawn_weight, withdrawn_at, job_order_id, operator_id) FROM stdin;
\.


--
-- Name: attendance_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.attendance_id_seq', 1, false);


--
-- Name: comp_inventory_attributes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.comp_inventory_attributes_id_seq', 35, true);


--
-- Name: comp_inventory_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.comp_inventory_id_seq', 24, true);


--
-- Name: custom_field_definitions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.custom_field_definitions_id_seq', 1, false);


--
-- Name: customer_accounts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.customer_accounts_id_seq', 12, true);


--
-- Name: daily_waste_summary_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.daily_waste_summary_id_seq', 12, true);


--
-- Name: depreciation_costs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.depreciation_costs_id_seq', 1, true);


--
-- Name: employees_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.employees_id_seq', 44, true);


--
-- Name: general_costs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.general_costs_id_seq', 1, true);


--
-- Name: inventory_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.inventory_id_seq', 868, true);


--
-- Name: inventory_orders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.inventory_orders_id_seq', 12, true);


--
-- Name: invoices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.invoices_id_seq', 24, true);


--
-- Name: job_order_bags_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_bags_id_seq', 2, true);


--
-- Name: job_order_cardboards_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_cardboards_id_seq', 1, false);


--
-- Name: job_order_clips_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_clips_id_seq', 6, true);


--
-- Name: job_order_component_attributes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_component_attributes_id_seq', 45, true);


--
-- Name: job_order_components_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_components_id_seq', 39, true);


--
-- Name: job_order_inks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_inks_id_seq', 2, true);


--
-- Name: job_order_machines_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_machines_id_seq', 144, true);


--
-- Name: job_order_materials_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_materials_id_seq', 92, true);


--
-- Name: job_order_sizers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_sizers_id_seq', 3, true);


--
-- Name: job_order_solvents_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_solvents_id_seq', 2, true);


--
-- Name: job_order_tapes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_order_tapes_id_seq', 2, true);


--
-- Name: job_orders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.job_orders_id_seq', 60, true);


--
-- Name: machine_production_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.machine_production_history_id_seq', 11, true);


--
-- Name: machine_production_history_ph_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.machine_production_history_ph_id_seq', 2, true);


--
-- Name: machine_waste_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.machine_waste_id_seq', 66, true);


--
-- Name: machines_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.machines_id_seq', 37, true);


--
-- Name: material_types_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.material_types_id_seq', 17, true);


--
-- Name: order_accounting_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.order_accounting_id_seq', 17, true);


--
-- Name: payment_allocations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.payment_allocations_id_seq', 1, false);


--
-- Name: payments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.payments_id_seq', 18, true);


--
-- Name: production_hangers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.production_hangers_id_seq', 18, true);


--
-- Name: production_rolls_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.production_rolls_id_seq', 29, true);


--
-- Name: purchase_orders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.purchase_orders_id_seq', 9, true);


--
-- Name: raw_invoices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.raw_invoices_id_seq', 7, true);


--
-- Name: raw_materials_costs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.raw_materials_costs_id_seq', 1, true);


--
-- Name: receipts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.receipts_id_seq', 21, true);


--
-- Name: recycling_line_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.recycling_line_id_seq', 9, true);


--
-- Name: revenue_details_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.revenue_details_id_seq', 133, true);


--
-- Name: revenues_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.revenues_id_seq', 8, true);


--
-- Name: storage_management_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.storage_management_id_seq', 4, true);


--
-- Name: supplier_accounts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.supplier_accounts_id_seq', 7, true);


--
-- Name: unexpected_costs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.unexpected_costs_id_seq', 1, true);


--
-- Name: used_materials_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.used_materials_id_seq', 34, true);


--
-- Name: withdrawals_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.withdrawals_id_seq', 1, false);


--
-- Name: inv_kpi_history inv_kpi_history_pkey; Type: CONSTRAINT; Schema: analytics; Owner: postgres
--

ALTER TABLE ONLY analytics.inv_kpi_history
    ADD CONSTRAINT inv_kpi_history_pkey PRIMARY KEY (snapshot_date, material_type);


--
-- Name: inv_risk_assessment inv_risk_assessment_pkey; Type: CONSTRAINT; Schema: analytics; Owner: postgres
--

ALTER TABLE ONLY analytics.inv_risk_assessment
    ADD CONSTRAINT inv_risk_assessment_pkey PRIMARY KEY (material_type, assessment_date);


--
-- Name: inv_seasonality inv_seasonality_pkey; Type: CONSTRAINT; Schema: analytics; Owner: postgres
--

ALTER TABLE ONLY analytics.inv_seasonality
    ADD CONSTRAINT inv_seasonality_pkey PRIMARY KEY (material_type, month);


--
-- Name: attendance attendance_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.attendance
    ADD CONSTRAINT attendance_pkey PRIMARY KEY (id);


--
-- Name: comp_inventory_attributes comp_inventory_attributes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comp_inventory_attributes
    ADD CONSTRAINT comp_inventory_attributes_pkey PRIMARY KEY (id);


--
-- Name: comp_inventory comp_inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comp_inventory
    ADD CONSTRAINT comp_inventory_pkey PRIMARY KEY (id);


--
-- Name: comp_inventory comp_inventory_serial_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comp_inventory
    ADD CONSTRAINT comp_inventory_serial_number_key UNIQUE (serial_number);


--
-- Name: custom_field_definitions custom_field_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_field_definitions
    ADD CONSTRAINT custom_field_definitions_pkey PRIMARY KEY (id);


--
-- Name: customer_accounts customer_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer_accounts
    ADD CONSTRAINT customer_accounts_pkey PRIMARY KEY (id);


--
-- Name: daily_waste_summary daily_waste_summary_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.daily_waste_summary
    ADD CONSTRAINT daily_waste_summary_pkey PRIMARY KEY (id);


--
-- Name: depreciation_costs depreciation_costs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.depreciation_costs
    ADD CONSTRAINT depreciation_costs_pkey PRIMARY KEY (id);


--
-- Name: employees employees_barcode_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_barcode_key UNIQUE (barcode);


--
-- Name: employees employees_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_email_key UNIQUE (email);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: general_costs general_costs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.general_costs
    ADD CONSTRAINT general_costs_pkey PRIMARY KEY (id);


--
-- Name: inventory_orders inventory_orders_group_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_orders
    ADD CONSTRAINT inventory_orders_group_id_key UNIQUE (group_id);


--
-- Name: inventory_orders inventory_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_orders
    ADD CONSTRAINT inventory_orders_pkey PRIMARY KEY (id);


--
-- Name: inventory inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_pkey PRIMARY KEY (id);


--
-- Name: invoices invoices_invoice_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_invoice_number_key UNIQUE (invoice_number);


--
-- Name: invoices invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);


--
-- Name: job_order_bags job_order_bags_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_bags
    ADD CONSTRAINT job_order_bags_pkey PRIMARY KEY (id);


--
-- Name: job_order_cardboards job_order_cardboards_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_cardboards
    ADD CONSTRAINT job_order_cardboards_pkey PRIMARY KEY (id);


--
-- Name: job_order_clips job_order_clips_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_clips
    ADD CONSTRAINT job_order_clips_pkey PRIMARY KEY (id);


--
-- Name: job_order_component_attributes job_order_component_attributes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_component_attributes
    ADD CONSTRAINT job_order_component_attributes_pkey PRIMARY KEY (id);


--
-- Name: job_order_components job_order_components_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_components
    ADD CONSTRAINT job_order_components_pkey PRIMARY KEY (id);


--
-- Name: job_order_inks job_order_inks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_inks
    ADD CONSTRAINT job_order_inks_pkey PRIMARY KEY (id);


--
-- Name: job_order_machines job_order_machines_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_machines
    ADD CONSTRAINT job_order_machines_pkey PRIMARY KEY (id);


--
-- Name: job_order_materials job_order_materials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_materials
    ADD CONSTRAINT job_order_materials_pkey PRIMARY KEY (id);


--
-- Name: job_order_sizers job_order_sizers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_sizers
    ADD CONSTRAINT job_order_sizers_pkey PRIMARY KEY (id);


--
-- Name: job_order_solvents job_order_solvents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_solvents
    ADD CONSTRAINT job_order_solvents_pkey PRIMARY KEY (id);


--
-- Name: job_order_tapes job_order_tapes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_tapes
    ADD CONSTRAINT job_order_tapes_pkey PRIMARY KEY (id);


--
-- Name: job_orders job_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_orders
    ADD CONSTRAINT job_orders_pkey PRIMARY KEY (id);


--
-- Name: machine_production_history machine_production_history_machine_id_order_id_roll_index_s_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history
    ADD CONSTRAINT machine_production_history_machine_id_order_id_roll_index_s_key UNIQUE (machine_id, order_id, roll_index, stage);


--
-- Name: machine_production_history_ph machine_production_history_ph_machine_id_order_id_batch_ind_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history_ph
    ADD CONSTRAINT machine_production_history_ph_machine_id_order_id_batch_ind_key UNIQUE (machine_id, order_id, batch_index, stage);


--
-- Name: machine_production_history_ph machine_production_history_ph_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history_ph
    ADD CONSTRAINT machine_production_history_ph_pkey PRIMARY KEY (id);


--
-- Name: machine_production_history machine_production_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history
    ADD CONSTRAINT machine_production_history_pkey PRIMARY KEY (id);


--
-- Name: machine_waste machine_waste_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_waste
    ADD CONSTRAINT machine_waste_pkey PRIMARY KEY (id);


--
-- Name: machines machines_machine_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machines
    ADD CONSTRAINT machines_machine_id_key UNIQUE (machine_id);


--
-- Name: machines machines_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machines
    ADD CONSTRAINT machines_pkey PRIMARY KEY (id);


--
-- Name: material_types material_types_material_type_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_types
    ADD CONSTRAINT material_types_material_type_key UNIQUE (material_type);


--
-- Name: material_types material_types_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_types
    ADD CONSTRAINT material_types_pkey PRIMARY KEY (id);


--
-- Name: operational_costs operational_costs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operational_costs
    ADD CONSTRAINT operational_costs_pkey PRIMARY KEY (id);


--
-- Name: order_accounting order_accounting_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_accounting
    ADD CONSTRAINT order_accounting_pkey PRIMARY KEY (id);


--
-- Name: payment_allocations payment_allocations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_pkey PRIMARY KEY (id);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: production_hangers production_hangers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_hangers
    ADD CONSTRAINT production_hangers_pkey PRIMARY KEY (id);


--
-- Name: production_rolls production_rolls_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_rolls
    ADD CONSTRAINT production_rolls_pkey PRIMARY KEY (id);


--
-- Name: purchase_orders purchase_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_pkey PRIMARY KEY (id);


--
-- Name: purchase_orders purchase_orders_po_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_po_number_key UNIQUE (po_number);


--
-- Name: raw_invoices raw_invoices_invoice_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.raw_invoices
    ADD CONSTRAINT raw_invoices_invoice_number_key UNIQUE (invoice_number);


--
-- Name: raw_invoices raw_invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.raw_invoices
    ADD CONSTRAINT raw_invoices_pkey PRIMARY KEY (id);


--
-- Name: raw_materials_costs raw_materials_costs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.raw_materials_costs
    ADD CONSTRAINT raw_materials_costs_pkey PRIMARY KEY (id);


--
-- Name: receipts receipts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_pkey PRIMARY KEY (id);


--
-- Name: receipts receipts_receipt_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_receipt_number_key UNIQUE (receipt_number);


--
-- Name: recycling_line recycling_line_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recycling_line
    ADD CONSTRAINT recycling_line_pkey PRIMARY KEY (id);


--
-- Name: revenue_details revenue_details_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.revenue_details
    ADD CONSTRAINT revenue_details_pkey PRIMARY KEY (id);


--
-- Name: revenues revenues_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.revenues
    ADD CONSTRAINT revenues_pkey PRIMARY KEY (id);


--
-- Name: storage_management storage_management_order_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.storage_management
    ADD CONSTRAINT storage_management_order_id_key UNIQUE (order_id);


--
-- Name: storage_management storage_management_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.storage_management
    ADD CONSTRAINT storage_management_pkey PRIMARY KEY (id);


--
-- Name: supplier_accounts supplier_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_accounts
    ADD CONSTRAINT supplier_accounts_pkey PRIMARY KEY (id);


--
-- Name: supplier_accounts supplier_accounts_supplier_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_accounts
    ADD CONSTRAINT supplier_accounts_supplier_code_key UNIQUE (supplier_code);


--
-- Name: unexpected_costs unexpected_costs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unexpected_costs
    ADD CONSTRAINT unexpected_costs_pkey PRIMARY KEY (id);


--
-- Name: daily_waste_summary unique_machine_date; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.daily_waste_summary
    ADD CONSTRAINT unique_machine_date UNIQUE (machine_id, waste_date);


--
-- Name: machine_waste unique_machine_order_index_type_date; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_waste
    ADD CONSTRAINT unique_machine_order_index_type_date UNIQUE (machine_id, job_order_id, index_number, waste_type, waste_date);


--
-- Name: order_accounting unique_order_accounting; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_accounting
    ADD CONSTRAINT unique_order_accounting UNIQUE (job_order_id);


--
-- Name: custom_field_definitions unique_table_field; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.custom_field_definitions
    ADD CONSTRAINT unique_table_field UNIQUE (table_name, field_name);


--
-- Name: used_materials used_materials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.used_materials
    ADD CONSTRAINT used_materials_pkey PRIMARY KEY (id);


--
-- Name: withdrawals withdrawals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.withdrawals
    ADD CONSTRAINT withdrawals_pkey PRIMARY KEY (id);


--
-- Name: idx_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_created_at ON public.recycling_line USING btree (created_at);


--
-- Name: idx_custom_field_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_custom_field_is_active ON public.custom_field_definitions USING btree (is_active);


--
-- Name: idx_custom_field_table_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_custom_field_table_name ON public.custom_field_definitions USING btree (table_name);


--
-- Name: idx_customer_accounts_client_name_ci; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_customer_accounts_client_name_ci ON public.customer_accounts USING btree (lower(TRIM(BOTH FROM client_name)));


--
-- Name: idx_customer_accounts_client_name_ci_unique; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX idx_customer_accounts_client_name_ci_unique ON public.customer_accounts USING btree (lower(TRIM(BOTH FROM client_name)));


--
-- Name: idx_customer_accounts_outstanding; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_customer_accounts_outstanding ON public.customer_accounts USING btree (outstanding_balance);


--
-- Name: idx_customer_accounts_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_customer_accounts_status ON public.customer_accounts USING btree (account_status);


--
-- Name: idx_depreciation_costs_cost; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_depreciation_costs_cost ON public.depreciation_costs USING btree (cost);


--
-- Name: idx_depreciation_costs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_depreciation_costs_created_at ON public.depreciation_costs USING btree (created_at);


--
-- Name: idx_depreciation_costs_currency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_depreciation_costs_currency ON public.depreciation_costs USING btree (currency);


--
-- Name: idx_depreciation_costs_dynamic_fields; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_depreciation_costs_dynamic_fields ON public.depreciation_costs USING gin (dynamic_fields);


--
-- Name: idx_depreciation_costs_submission_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_depreciation_costs_submission_date ON public.depreciation_costs USING btree (submission_date);


--
-- Name: idx_depreciation_costs_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_depreciation_costs_type ON public.depreciation_costs USING btree (type);


--
-- Name: idx_employees_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_employees_status ON public.employees USING btree (status);


--
-- Name: idx_general_costs_cost; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_general_costs_cost ON public.general_costs USING btree (cost);


--
-- Name: idx_general_costs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_general_costs_created_at ON public.general_costs USING btree (created_at);


--
-- Name: idx_general_costs_currency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_general_costs_currency ON public.general_costs USING btree (currency);


--
-- Name: idx_general_costs_dynamic_fields; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_general_costs_dynamic_fields ON public.general_costs USING gin (dynamic_fields);


--
-- Name: idx_general_costs_submission_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_general_costs_submission_date ON public.general_costs USING btree (submission_date);


--
-- Name: idx_general_costs_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_general_costs_type ON public.general_costs USING btree (type);


--
-- Name: idx_inventory_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_inventory_status ON public.inventory USING btree (status);


--
-- Name: idx_invoices_client_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_invoices_client_name ON public.invoices USING btree (client_name);


--
-- Name: idx_invoices_customer_account; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_invoices_customer_account ON public.invoices USING btree (customer_account_id);


--
-- Name: idx_invoices_due_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_invoices_due_date ON public.invoices USING btree (due_date);


--
-- Name: idx_invoices_payment_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_invoices_payment_status ON public.invoices USING btree (payment_status);


--
-- Name: idx_job_orders_client_name_ci; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_job_orders_client_name_ci ON public.job_orders USING btree (lower(TRIM(BOTH FROM client_name)));


--
-- Name: idx_job_orders_customer_account; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_job_orders_customer_account ON public.job_orders USING btree (customer_account_id);


--
-- Name: idx_machine_production_machine_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_production_machine_id ON public.machine_production_history USING btree (machine_id);


--
-- Name: idx_machine_production_ph_machine_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_production_ph_machine_id ON public.machine_production_history_ph USING btree (machine_id);


--
-- Name: idx_machine_production_ph_recorded_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_production_ph_recorded_at ON public.machine_production_history_ph USING btree (recorded_at);


--
-- Name: idx_machine_production_recorded_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_production_recorded_at ON public.machine_production_history USING btree (recorded_at);


--
-- Name: idx_machine_waste_index_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_waste_index_number ON public.machine_waste USING btree (index_number);


--
-- Name: idx_machine_waste_job_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_waste_job_order_id ON public.machine_waste USING btree (job_order_id);


--
-- Name: idx_machine_waste_machine_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_waste_machine_id ON public.machine_waste USING btree (machine_id);


--
-- Name: idx_machine_waste_waste_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machine_waste_waste_date ON public.machine_waste USING btree (waste_date);


--
-- Name: idx_machines_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_machines_status ON public.machines USING btree (status);


--
-- Name: idx_operational_costs_cost; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operational_costs_cost ON public.operational_costs USING btree (cost);


--
-- Name: idx_operational_costs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operational_costs_created_at ON public.operational_costs USING btree (created_at);


--
-- Name: idx_operational_costs_currency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operational_costs_currency ON public.operational_costs USING btree (currency);


--
-- Name: idx_operational_costs_dynamic_fields; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operational_costs_dynamic_fields ON public.operational_costs USING gin (dynamic_fields);


--
-- Name: idx_operational_costs_submission_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operational_costs_submission_date ON public.operational_costs USING btree (submission_date);


--
-- Name: idx_operational_costs_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operational_costs_type ON public.operational_costs USING btree (type);


--
-- Name: idx_order_accounting_client_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_accounting_client_name ON public.order_accounting USING btree (client_name);


--
-- Name: idx_order_accounting_customer; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_accounting_customer ON public.order_accounting USING btree (customer_account_id);


--
-- Name: idx_order_accounting_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_accounting_status ON public.order_accounting USING btree (payment_status);


--
-- Name: idx_payments_group_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_payments_group_id ON public.payments USING btree (group_id);


--
-- Name: idx_payments_payment_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_payments_payment_date ON public.payments USING btree (payment_date);


--
-- Name: idx_payments_supplier_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_payments_supplier_id ON public.payments USING btree (supplier_id);


--
-- Name: idx_purchase_orders_group_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_purchase_orders_group_id ON public.purchase_orders USING btree (group_id);


--
-- Name: idx_purchase_orders_po_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_purchase_orders_po_number ON public.purchase_orders USING btree (po_number);


--
-- Name: idx_purchase_orders_supplier_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_purchase_orders_supplier_id ON public.purchase_orders USING btree (supplier_id);


--
-- Name: idx_raw_invoices_group_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_invoices_group_id ON public.raw_invoices USING btree (group_id);


--
-- Name: idx_raw_invoices_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_invoices_status ON public.raw_invoices USING btree (status);


--
-- Name: idx_raw_invoices_supplier_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_invoices_supplier_id ON public.raw_invoices USING btree (supplier_id);


--
-- Name: idx_raw_materials_costs_cost; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_materials_costs_cost ON public.raw_materials_costs USING btree (cost);


--
-- Name: idx_raw_materials_costs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_materials_costs_created_at ON public.raw_materials_costs USING btree (created_at);


--
-- Name: idx_raw_materials_costs_currency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_materials_costs_currency ON public.raw_materials_costs USING btree (currency);


--
-- Name: idx_raw_materials_costs_dynamic_fields; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_materials_costs_dynamic_fields ON public.raw_materials_costs USING gin (dynamic_fields);


--
-- Name: idx_raw_materials_costs_submission_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_materials_costs_submission_date ON public.raw_materials_costs USING btree (submission_date);


--
-- Name: idx_raw_materials_costs_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_raw_materials_costs_type ON public.raw_materials_costs USING btree (type);


--
-- Name: idx_receipts_client_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_receipts_client_name ON public.receipts USING btree (client_name);


--
-- Name: idx_receipts_customer_account; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_receipts_customer_account ON public.receipts USING btree (customer_account_id);


--
-- Name: idx_receipts_payment_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_receipts_payment_date ON public.receipts USING btree (payment_date);


--
-- Name: idx_recycling_material_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_recycling_material_type ON public.recycling_line USING btree (recycling_material_type);


--
-- Name: idx_revenue_details_invoice_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_revenue_details_invoice_date ON public.revenue_details USING btree (invoice_date);


--
-- Name: idx_revenue_details_revenue_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_revenue_details_revenue_id ON public.revenue_details USING btree (revenue_id);


--
-- Name: idx_revenues_period_dates; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_revenues_period_dates ON public.revenues USING btree (period_start_date, period_end_date);


--
-- Name: idx_revenues_period_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_revenues_period_type ON public.revenues USING btree (period_type);


--
-- Name: idx_revenues_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_revenues_status ON public.revenues USING btree (status);


--
-- Name: idx_revenues_year_month; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_revenues_year_month ON public.revenues USING btree (year, month);


--
-- Name: idx_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_status ON public.recycling_line USING btree (status);


--
-- Name: idx_storage_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_storage_order_id ON public.storage_management USING btree (order_id);


--
-- Name: idx_storage_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_storage_status ON public.storage_management USING btree (status);


--
-- Name: idx_supplier_accounts_contact_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_supplier_accounts_contact_email ON public.supplier_accounts USING btree (contact_email);


--
-- Name: idx_supplier_accounts_group_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_supplier_accounts_group_id ON public.supplier_accounts USING btree (group_id);


--
-- Name: idx_supplier_accounts_name_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_supplier_accounts_name_code ON public.supplier_accounts USING btree (supplier_name, supplier_code);


--
-- Name: idx_supplier_accounts_supplier_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_supplier_accounts_supplier_code ON public.supplier_accounts USING btree (supplier_code);


--
-- Name: idx_supplier_accounts_supplier_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_supplier_accounts_supplier_name ON public.supplier_accounts USING btree (supplier_name);


--
-- Name: idx_timestamp_start; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_timestamp_start ON public.recycling_line USING btree (timestamp_start);


--
-- Name: idx_unexpected_costs_cost; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_unexpected_costs_cost ON public.unexpected_costs USING btree (cost);


--
-- Name: idx_unexpected_costs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_unexpected_costs_created_at ON public.unexpected_costs USING btree (created_at);


--
-- Name: idx_unexpected_costs_currency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_unexpected_costs_currency ON public.unexpected_costs USING btree (currency);


--
-- Name: idx_unexpected_costs_dynamic_fields; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_unexpected_costs_dynamic_fields ON public.unexpected_costs USING gin (dynamic_fields);


--
-- Name: idx_unexpected_costs_submission_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_unexpected_costs_submission_date ON public.unexpected_costs USING btree (submission_date);


--
-- Name: idx_unexpected_costs_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_unexpected_costs_type ON public.unexpected_costs USING btree (type);


--
-- Name: order_details_view _RETURN; Type: RULE; Schema: public; Owner: postgres
--

CREATE OR REPLACE VIEW public.order_details_view AS
 SELECT oa.id,
    oa.customer_account_id,
    oa.job_order_id,
    oa.client_name,
    oa.order_amount,
    oa.amount_invoiced,
    oa.amount_paid,
    oa.outstanding_balance,
    oa.payment_status,
    oa.invoice_status,
    oa.order_date,
    oa.first_invoice_date,
    oa.last_payment_date,
    oa.due_date,
    oa.created_at,
    oa.updated_at,
    jo.order_id,
    jo.product,
    jo.model,
    jo.order_quantity,
    jo.assigned_date,
    jo.status AS order_status,
    count(DISTINCT i.id) AS invoice_count,
    count(DISTINCT r.id) AS payment_count
   FROM (((public.order_accounting oa
     JOIN public.job_orders jo ON ((oa.job_order_id = jo.id)))
     LEFT JOIN public.invoices i ON ((oa.job_order_id = i.job_order_id)))
     LEFT JOIN public.receipts r ON ((oa.job_order_id = r.job_order_id)))
  GROUP BY oa.id, jo.order_id, jo.product, jo.model, jo.order_quantity, jo.assigned_date, jo.status;


--
-- Name: job_orders auto_release_machines_trigger; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER auto_release_machines_trigger AFTER UPDATE OF status ON public.job_orders FOR EACH ROW EXECUTE FUNCTION public.release_machines_on_order_completion();


--
-- Name: job_orders trg_job_orders_completed; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_job_orders_completed BEFORE UPDATE ON public.job_orders FOR EACH ROW EXECUTE FUNCTION public.trg_job_orders_completed();


--
-- Name: custom_field_definitions trigger_custom_field_definitions_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_custom_field_definitions_updated_at BEFORE UPDATE ON public.custom_field_definitions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: payments trigger_payments_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_payments_updated_at BEFORE UPDATE ON public.payments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: purchase_orders trigger_purchase_orders_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_purchase_orders_updated_at BEFORE UPDATE ON public.purchase_orders FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: raw_invoices trigger_raw_invoices_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_raw_invoices_updated_at BEFORE UPDATE ON public.raw_invoices FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: supplier_accounts trigger_supplier_accounts_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_supplier_accounts_updated_at BEFORE UPDATE ON public.supplier_accounts FOR EACH ROW EXECUTE FUNCTION public.update_supplier_accounts_updated_at();


--
-- Name: raw_invoices trigger_update_balance_on_invoice; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_update_balance_on_invoice AFTER INSERT OR UPDATE ON public.raw_invoices FOR EACH ROW EXECUTE FUNCTION public.update_outstanding_balance();


--
-- Name: payments trigger_update_balance_on_payment; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_update_balance_on_payment AFTER INSERT OR UPDATE ON public.payments FOR EACH ROW EXECUTE FUNCTION public.update_outstanding_balance();


--
-- Name: machine_waste trigger_update_daily_waste; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_update_daily_waste AFTER INSERT ON public.machine_waste FOR EACH ROW EXECUTE FUNCTION public.update_daily_waste_summary();


--
-- Name: recycling_line trigger_update_recycling_line_timestamp; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_update_recycling_line_timestamp BEFORE UPDATE ON public.recycling_line FOR EACH ROW EXECUTE FUNCTION public.update_recycling_line_timestamp();


--
-- Name: depreciation_costs update_depreciation_costs_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_depreciation_costs_updated_at BEFORE UPDATE ON public.depreciation_costs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: general_costs update_general_costs_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_general_costs_updated_at BEFORE UPDATE ON public.general_costs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: operational_costs update_operational_costs_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_operational_costs_updated_at BEFORE UPDATE ON public.operational_costs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: raw_materials_costs update_raw_materials_costs_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_raw_materials_costs_updated_at BEFORE UPDATE ON public.raw_materials_costs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: unexpected_costs update_unexpected_costs_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_unexpected_costs_updated_at BEFORE UPDATE ON public.unexpected_costs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: attendance attendance_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.attendance
    ADD CONSTRAINT attendance_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id);


--
-- Name: comp_inventory_attributes comp_inventory_attributes_comp_inventory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comp_inventory_attributes
    ADD CONSTRAINT comp_inventory_attributes_comp_inventory_id_fkey FOREIGN KEY (comp_inventory_id) REFERENCES public.comp_inventory(id) ON DELETE CASCADE;


--
-- Name: employees employees_current_job_order_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_current_job_order_fkey FOREIGN KEY (current_job_order) REFERENCES public.job_orders(id);


--
-- Name: production_rolls fk_blowing_machine; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_rolls
    ADD CONSTRAINT fk_blowing_machine FOREIGN KEY (blowing_machine_id) REFERENCES public.machines(machine_id);


--
-- Name: production_rolls fk_cutting_machine; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_rolls
    ADD CONSTRAINT fk_cutting_machine FOREIGN KEY (cutting_machine_id) REFERENCES public.machines(machine_id);


--
-- Name: production_rolls fk_metal_detect_machine; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_rolls
    ADD CONSTRAINT fk_metal_detect_machine FOREIGN KEY (metal_detect_machine_id) REFERENCES public.machines(machine_id);


--
-- Name: production_hangers fk_ph_injection_machine; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_hangers
    ADD CONSTRAINT fk_ph_injection_machine FOREIGN KEY (injection_machine_id) REFERENCES public.machines(machine_id);


--
-- Name: production_hangers fk_ph_metal_detect_machine; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_hangers
    ADD CONSTRAINT fk_ph_metal_detect_machine FOREIGN KEY (metal_detect_machine_id) REFERENCES public.machines(machine_id);


--
-- Name: production_rolls fk_printing_machine; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_rolls
    ADD CONSTRAINT fk_printing_machine FOREIGN KEY (printing_machine_id) REFERENCES public.machines(machine_id);


--
-- Name: revenue_details fk_revenue_details_revenue; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.revenue_details
    ADD CONSTRAINT fk_revenue_details_revenue FOREIGN KEY (revenue_id) REFERENCES public.revenues(id) ON DELETE CASCADE;


--
-- Name: inventory inventory_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id);


--
-- Name: invoices invoices_customer_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_customer_account_id_fkey FOREIGN KEY (customer_account_id) REFERENCES public.customer_accounts(id);


--
-- Name: invoices invoices_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id);


--
-- Name: job_order_bags job_order_bags_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_bags
    ADD CONSTRAINT job_order_bags_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_cardboards job_order_cardboards_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_cardboards
    ADD CONSTRAINT job_order_cardboards_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_clips job_order_clips_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_clips
    ADD CONSTRAINT job_order_clips_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_component_attributes job_order_component_attributes_job_order_component_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_component_attributes
    ADD CONSTRAINT job_order_component_attributes_job_order_component_id_fkey FOREIGN KEY (job_order_component_id) REFERENCES public.job_order_components(id) ON DELETE CASCADE;


--
-- Name: job_order_component_attributes job_order_component_attributes_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_component_attributes
    ADD CONSTRAINT job_order_component_attributes_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_components job_order_components_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_components
    ADD CONSTRAINT job_order_components_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_inks job_order_inks_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_inks
    ADD CONSTRAINT job_order_inks_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_machines job_order_machines_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_machines
    ADD CONSTRAINT job_order_machines_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_materials job_order_materials_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_materials
    ADD CONSTRAINT job_order_materials_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_sizers job_order_sizers_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_sizers
    ADD CONSTRAINT job_order_sizers_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_solvents job_order_solvents_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_solvents
    ADD CONSTRAINT job_order_solvents_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_order_tapes job_order_tapes_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_order_tapes
    ADD CONSTRAINT job_order_tapes_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: job_orders job_orders_customer_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_orders
    ADD CONSTRAINT job_orders_customer_account_id_fkey FOREIGN KEY (customer_account_id) REFERENCES public.customer_accounts(id);


--
-- Name: job_orders job_orders_operator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_orders
    ADD CONSTRAINT job_orders_operator_id_fkey FOREIGN KEY (operator_id) REFERENCES public.employees(id);


--
-- Name: machine_production_history machine_production_history_machine_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history
    ADD CONSTRAINT machine_production_history_machine_id_fkey FOREIGN KEY (machine_id) REFERENCES public.machines(machine_id);


--
-- Name: machine_production_history machine_production_history_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history
    ADD CONSTRAINT machine_production_history_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.job_orders(id);


--
-- Name: machine_production_history_ph machine_production_history_ph_machine_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history_ph
    ADD CONSTRAINT machine_production_history_ph_machine_id_fkey FOREIGN KEY (machine_id) REFERENCES public.machines(machine_id);


--
-- Name: machine_production_history_ph machine_production_history_ph_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_production_history_ph
    ADD CONSTRAINT machine_production_history_ph_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.job_orders(id);


--
-- Name: machine_waste machine_waste_recorded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machine_waste
    ADD CONSTRAINT machine_waste_recorded_by_fkey FOREIGN KEY (recorded_by) REFERENCES public.employees(id);


--
-- Name: machines machines_current_job_order_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.machines
    ADD CONSTRAINT machines_current_job_order_fkey FOREIGN KEY (current_job_order) REFERENCES public.job_orders(id);


--
-- Name: order_accounting order_accounting_customer_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_accounting
    ADD CONSTRAINT order_accounting_customer_account_id_fkey FOREIGN KEY (customer_account_id) REFERENCES public.customer_accounts(id);


--
-- Name: order_accounting order_accounting_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_accounting
    ADD CONSTRAINT order_accounting_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id);


--
-- Name: payment_allocations payment_allocations_customer_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_customer_account_id_fkey FOREIGN KEY (customer_account_id) REFERENCES public.customer_accounts(id);


--
-- Name: payment_allocations payment_allocations_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id);


--
-- Name: payment_allocations payment_allocations_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id);


--
-- Name: payment_allocations payment_allocations_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment_allocations
    ADD CONSTRAINT payment_allocations_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.receipts(id);


--
-- Name: payments payments_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.raw_invoices(id) ON DELETE SET NULL;


--
-- Name: production_hangers production_hangers_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_hangers
    ADD CONSTRAINT production_hangers_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: production_rolls production_rolls_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_rolls
    ADD CONSTRAINT production_rolls_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.job_orders(id) ON DELETE CASCADE;


--
-- Name: receipts receipts_customer_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_customer_account_id_fkey FOREIGN KEY (customer_account_id) REFERENCES public.customer_accounts(id);


--
-- Name: receipts receipts_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id);


--
-- Name: receipts receipts_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id);


--
-- Name: storage_management storage_management_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.storage_management
    ADD CONSTRAINT storage_management_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.job_orders(id);


--
-- Name: used_materials used_materials_job_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.used_materials
    ADD CONSTRAINT used_materials_job_order_id_fkey FOREIGN KEY (job_order_id) REFERENCES public.job_orders(id);


--
-- Name: mv_inv_flow_daily; Type: MATERIALIZED VIEW DATA; Schema: public; Owner: postgres
--

REFRESH MATERIALIZED VIEW public.mv_inv_flow_daily;


--
-- Name: mv_inv_live; Type: MATERIALIZED VIEW DATA; Schema: public; Owner: postgres
--

REFRESH MATERIALIZED VIEW public.mv_inv_live;


--
-- PostgreSQL database dump complete
--

