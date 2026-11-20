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

@router.get("/vendors",response_model=list[VendorResponse])
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
                    "v_id": row[0],
                    "v_name": row[1],
                    "contact_ref": row[2],
                    "active": row[3]
                }
                for row in rows
            ]
            return vendors
    finally:
        conn.close()

@router.post("/vendors",response_model=VendorResponse)
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
                    v_name,
                    contact_ref,
                    active
                )
                VALUES (%s, %s, %s)
                RETURNING v_id, v_name, contact_ref, active
                """,
                (
                    vendor.v_name,
                    vendor.contact_ref,
                    vendor.active
                )
            )

            row = cursor.fetchone()

            conn.commit()

            return {
                "v_id": row[0],
                "v_name": row[1],
                "contact_ref": row[2],
                "active": row[3]
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

@router.put("/vendors/{id}",response_model=VendorResponse)
def update_vendor(
        id:int,
        vendor: VendorUpdate ,
        current_user :dict = Depends(require_role("clerk")),
):
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            UPDATE vendors set 
            v_name=%s, 
            contact_ref=%s, 
            active=%s where v_id=%s
            RETURNING v_id, v_name, contact_ref, active""",
            (vendor.v_name,vendor.contact_ref,vendor.active,id))

            row = cursor.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Vendor not found"
                )
            conn.commit()
            return {
                "v_id": row[0],
                "v_name": row[1],
                "contact_ref": row[2],
                "active": row[3]
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

