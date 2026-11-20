from fastapi import Depends, HTTPException,APIRouter
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.db.database import get_connection_db
from app.routers.auth import get_current_user,require_role
from app.schemas.vendor import VendorResponse,VendorCreate,VendorUpdate
import psycopg2

router = APIRouter(
    prefix="/vendors",
    tags=['Vendors']
)

@router.get("/",response_model=list[VendorResponse])
def get_all_vendors(
        current_user  : dict = Depends(get_current_user),
):
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("select * from vendors")
            rows = cursor.fetchall()
            vendors = [
                {
                    "vendor_id": row[0],
                    "vendor_name": row[1],
                    "contact_reference": row[2],
                    "tax_id":row[3],
                    "active": row[4],
                    "created_at": row[5],
                    "updated_at": row[6]
                }
                for row in rows
            ]
            return vendors
    finally:
        conn.close()

@router.get("/{id}",response_model=VendorResponse)
def get_vendor(
        id : int,
        current_user : dict = Depends(get_current_user),
):
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            Select * from vendors where vendor_id=%s
            """,id)

        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Vendor not found"
            )
        vendor = {
            "vendor_id": row[0],
            "vendor_name": row[1],
            "contact_reference": row[2],
            "tax_id": row[3],
            "active": row[4],
            "created_at": row[5],
            "updated_at": row[6]
        }
        return vendor
    finally:
        conn.close()

@router.post("/",response_model=VendorResponse)
def create_vendor(
        vendor: VendorCreate ,
        current_user :dict = Depends(require_role("clerk")),
):
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO vendors (
                    vendor_name,
                    contact_reference,
                    tax_id,
                    active
                )
                VALUES (%s, %s, %s,%s)
                RETURNING vendor_id, vendor_name, contact_reference, tax_id, active, created_at, updated_at
                """,
                (
                    vendor.vendor_name,
                    vendor.contact_reference,
                    vendor.tax_id,
                    vendor.active
                )
            )

            row = cursor.fetchone()

            conn.commit()

            return {
                "vendor_id": row[0],
                "vendor_name": row[1],
                "contact_reference": row[2],
                "tax_id": row[3],
                "active": row[4],
                "created_at": row[5],
                "updated_at": row[6]
            }

    # In db the contact_ref is UNIQUE, so if the contact is duplicating
    # then vendor is already present
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="Vendor already exists"
        )
    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

@router.put("/{id}",response_model=VendorResponse)
def update_vendor(
        id:int,
        vendor: VendorUpdate ,
        current_user :dict = Depends(require_role("clerk")),
):
    conn = get_connection_db()
    try:
        update_data = vendor.model_dump(exclude_unset=True)
        # update_data will have the data sent from frontend e.g={"v_name" : "ABC", "active":false}
        allowed_fields = {
            "vendor_name",
            "contact_reference",
            "tax_id",
            "active"
        }
        if not set(update_data).issubset(allowed_fields):
            raise HTTPException(
                status_code=400,
                detail="Invalid Update Fields"
            )


        with conn.cursor() as cursor:
            # If no fields were provided, just fetch and return
            # the existing vendor without updating updated_at field.
            if not update_data:
                cursor.execute(
                    """
                    SELECT
                        vendor_id,vendor_name,contact_reference,
                        tax_id,active,
                        created_at,updated_at
                    FROM vendors
                    WHERE vendor_id = %s
                    """,
                    (id,)
                )
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Vendor not found"
                    )
                return {
                    "vendor_id": row[0],
                    "vendor_name": row[1],
                    "contact_reference": row[2],
                    "tax_id": row[3],
                    "active": row[4],
                    "created_at": row[5],
                    "updated_at": row[6]
                }
            # Update only the fields provided by Frontend
            set_clause = ", ".join(
                f"{field} = %s" for field in update_data
            )
            set_clause += ", updated_at = CURRENT_TIMESTAMP"
            values = list(update_data.values())
            values.append(id)
            cursor.execute(f"""
            UPDATE vendors set 
            {set_clause} where vendor_id=%s
            RETURNING vendor_id, vendor_name, contact_reference, tax_id,active, created_at, updated_at""",
            values)

            row = cursor.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Vendor not found"
                )
            conn.commit()
            return {
                "vendor_id": row[0],
                "vendor_name": row[1],
                "contact_reference": row[2],
                "tax_id": row[3],
                "active": row[4],
                "created_at": row[5],
                "updated_at": row[6]
            }
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="Vendor already exists"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

