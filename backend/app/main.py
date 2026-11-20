from fastapi import FastAPI
from app.routers.auth import router as auth_router
from app.routers.vendors import router as vendor_router
from app.routers.invoices import router as invoice_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(vendor_router)
app.include_router(invoice_router)
