import jwt
from datetime import datetime,timedelta,timezone
from fastapi import Depends, HTTPException,APIRouter
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.security import (verify_password,create_access_token)
from app.db.database import get_connection_db

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Find the user in clerk and then approvers and then auditors."""
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT c_id,c_name,c_email,c_password,is_active
            From clerks
            where c_email=%s
            """,(form_data.username,))

            user = cursor.fetchone()
            role="clerk"
            if not user:
                cursor.execute("""
                SELECT app_id,app_name,app_email,app_password,is_active
                From approvers
                where app_email=%s
                """,(form_data.username,))

                user = cursor.fetchone()
                role="approver"
            if not user:
                cursor.execute("""
                SELECT aud_id,aud_name,aud_email,aud_password,is_active
                From auditors
                where aud_email=%s
                """, (form_data.username,))

                user = cursor.fetchone()
                role = "auditor"

            if not user:
                raise HTTPException(
                    status_code=401,
                    detail = "Invalid email or password"
                )

            # Assuming the user table has all the following columns
            user_id = user[0]
            name = user[1]
            email = user[2]
            stored_password = user[3]
            is_active = user[4]

            if not (verify_password(form_data.password,stored_password)):
                raise HTTPException(
                    status_code=401,
                    detail="Incorrect email or password"
                )

            if not is_active:
                raise HTTPException(
                    status_code=403,
                    detail="Inactive user"
                )
            token = create_access_token(user_id,role)

            return {
                "access_token": token,
                "token_type": "bearer",
            }

    finally:
        conn.close()

# ------------------------------------------------
# Get current logged-in user
# ------------------------------------------------

def get_current_user(
        token: str = Depends(oauth2_scheme),
):
    credentials_exception = HTTPException(
        status_code = 401,
        detail = "Invalid or expired token",
        headers = {"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms = [settings.JWT_ALGORITHM],
        )
        user_id = int(payload.get("sub"))
        role = payload.get("role")
        if role not in ["clerk", "approver","auditor"]:
            raise credentials_exception

    except (jwt.InvalidTokenError,TypeError,ValueError):
        raise credentials_exception

    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            if role == "clerk":
                cursor.execute("""
                           SELECT c_id,c_name,c_email
                           from clerks 
                           where c_id=%s    
                               """, (user_id,))

            elif role == "approver":
                cursor.execute("""
                               SELECT app_id,app_name,app_email
                               from approvers 
                               where app_id=%s    
                               """, (user_id,))
            # user = cursor.fetchone()
            elif role == "auditor":
                cursor.execute("""
                               SELECT aud_id,aud_name,aud_email
                               from auditors 
                               where aud_id=%s    
                               """, (user_id,))
            user = cursor.fetchone()
            if not user:
                raise credentials_exception

            return {
                "id": user[0],
                "name": user[1],
                "email": user[2],
                "role": role,
            }
    finally:
        conn.close()

# ------------------------------------------------
# GET LOGGED-IN USER DETAILS
# ------------------------------------------------
@router.get("/me")
def get_my_profile(
        current_user: dict = Depends(get_current_user),
):
    return current_user

# ------------------------------------------------
# ROLE-BASED ACCESS CONTROL
# ------------------------------------------------
def require_role(required_role:str):
    def role_checker(
            current_user:dict = Depends(get_current_user)
    ):
        if current_user["role"] != required_role:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to access this resource",
            )
        return current_user
    return role_checker