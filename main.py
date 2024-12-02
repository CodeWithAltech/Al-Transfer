import time
import random
import json
import logging
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.timeout import TimeoutMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from models import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment Configuration
class Settings:
    APP_ENVIRONMENT: str = "live"
    
    # Pesapal API Configuration
    if APP_ENVIRONMENT == 'sandbox':
        API_URL = "https://cybqa.pesapal.com/pesapalv3/api/Auth/RequestToken"
        CONSUMER_KEY = "TDpigBOOhs+zAl8cwH2Fl82jJGyD8xev"
        CONSUMER_SECRET = "1KpkfsMaihIcOlhnBo/gBZ5smw="
        BASE_API_URL = "https://cybqa.pesapal.com/pesapalv3"
    elif APP_ENVIRONMENT == 'live':
        API_URL = "https://pay.pesapal.com/v3/api/Auth/RequestToken"
        CONSUMER_KEY = "BopfGlE7GfenAqGvS5SGdke4M67WLFxh"
        CONSUMER_SECRET = "nnYh5QSFZUXRsQu6PQI4llLB5iU="
        BASE_API_URL = "https://pay.pesapal.com/v3"
    else:
        raise ValueError("Invalid APP_ENVIRONMENT")

# Pydantic Models with Enhanced Validation
class PaymentRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Payment amount must be positive")
    email_address: EmailStr
    phone: str = Field(..., min_length=10, max_length=15, description="Valid phone number")
    first_name: str = Field(..., min_length=2, max_length=50)
    middle_name: Optional[str] = Field(None, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    callback_url: str = Field(..., description="URL to receive payment callback")
    branch: Optional[str] = Field(default="Default Branch", max_length=100)

    class Config:
        schema_extra = {
            "example": {
                "amount": 50000,
                "email_address": "user@example.com",
                "phone": "+256712345678",
                "first_name": "John",
                "last_name": "Doe",
                "callback_url": "https://yourapp.com/payment-callback"
            }
        }

class TransactionStatusRequest(BaseModel):
    order_tracking_id: str = Field(..., description="Unique order tracking ID")

class IPNRegistrationRequest(BaseModel):
    url: str = Field(..., description="IPN callback URL")
    ipn_notification_type: str = Field(default="POST", description="IPN notification method")

# FastAPI App with Enhanced Configuration
app = FastAPI(
    title="AlTransfer Payment API",
    description="Secure payment processing API for AlTransfer using Pesapal",
    version="1.1.0",
    docs_url="/api-docs",
    redoc_url="/redoc"
)

# Middleware Configuration
app.add_middleware(TimeoutMiddleware, seconds=45)  # Increased timeout
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500", 
        "https://altransfer.vercel.app",
        "http://127.0.0.1:5500",
        "*"  # Be cautious in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility Functions with Enhanced Error Handling
def get_access_token(max_retries: int = 3):
    """Retrieve access token from Pesapal API with retry mechanism"""
    for attempt in range(max_retries):
        try:
            data = {
                "consumer_key": Settings.CONSUMER_KEY,
                "consumer_secret": Settings.CONSUMER_SECRET
            }
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            response = requests.post(Settings.API_URL, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            return token_data.get("token")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Token retrieval attempt {attempt + 1} failed: {e}")
            time.sleep(2)  # Wait before retrying
    
    raise HTTPException(status_code=500, detail="Failed to retrieve access token")

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred",
            "detail": str(exc),
            "request_method": request.method,
            "request_url": str(request.url)
        }
    )

# CORS Options Handler
@app.options("/submit-order")
@app.options("/register-ipn")
@app.options("/transaction-status")
async def options_handler():
    """Handle CORS preflight requests"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

# API Endpoints
@app.post("/submit-order")
async def submit_order(request: PaymentRequest):
    """Submit payment order to Pesapal with comprehensive error handling"""
    try:
        token = get_access_token()
        
        # Generate secure merchant reference
        merchant_reference = f"AL-{random.randint(10000, 99999)}"
        
        # Prepare submit order URL
        submit_order_url = f"{Settings.BASE_API_URL}/api/Transactions/SubmitOrderRequest"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        data = {
            "id": merchant_reference,
            "currency": "UGX",
            "amount": request.amount,
            "description": "AlTransfer Payment",
            "callback_url": request.callback_url,
            "branch": request.branch or "Default Branch",
            "billing_address": {
                "email_address": request.email_address,
                "phone_number": request.phone,
                "country_code": "UG",
                "first_name": request.first_name,
                "middle_name": request.middle_name or "",
                "last_name": request.last_name
            }
        }
        
        response = requests.post(submit_order_url, json=data, headers=headers, timeout=20)
        response.raise_for_status()
        
        order_response = response.json()
        order_tracking_id = order_response.get("order_tracking_id")
        
        if not order_tracking_id:
            raise HTTPException(status_code=400, detail="No order tracking ID received")
        
        return {
            "order_tracking_id": order_tracking_id,
            "status": "PENDING",
            "reference": merchant_reference
        }
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Payment submission error: {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Order submission failed: {str(e)}"
        )

@app.get("/transaction-status")
async def transaction_status(orderTrackingId: str):
    """Get transaction status from Pesapal"""
    try:
        token = get_access_token()
        transaction_status_url = f"{Settings.BASE_API_URL}/api/Transactions/GetTransactionStatus"
        
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.get(
            f"{transaction_status_url}?orderTrackingId={orderTrackingId}", 
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        return {"transaction_status": response.json()}
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Transaction status error: {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Failed to fetch transaction status: {str(e)}"
        )

@app.get("/")
async def health_check():
    """Comprehensive health check endpoint"""
    return {
        "status": "healthy", 
        "message": "AlTransfer Payment API is running",
        "version": "1.1.0",
        "environment": Settings.APP_ENVIRONMENT
    }

# Optional: Add startup and shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info("Application is starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application is shutting down...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
