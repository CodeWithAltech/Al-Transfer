import time
import random
import json
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.timeout import TimeoutMiddleware



# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred",
            "error": str(exc)
        }
    )


# Configurations
APP_ENVIRONMENT = "live"

# Pesapal API credentials
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
    raise Exception("Invalid APP_ENVIRONMENT")

# Pydantic Models
class PaymentRequest(BaseModel):
    amount: float
    email_address: str
    phone: str
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    callback_url: str
    branch: Optional[str] = "Default Branch"

class TransactionStatusRequest(BaseModel):
    order_tracking_id: str

class IPNRegistrationRequest(BaseModel):
    url: str
    ipn_notification_type: str = "POST"

# FastAPI App Configuration
app = FastAPI(
    title="AlTransfer Payment API",
    description="Payment processing API for AlTransfer using Pesapal",
    version="1.0.0"
)

# CORS Middleware with Extensive Configuration
app.add_middleware(TimeoutMiddleware, seconds=30)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500", 
        "https://altransfer.vercel.app", 
        # Add other specific domains
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Utility Functions
def get_access_token():
    """Retrieve access token from Pesapal API"""
    data = {
        "consumer_key": CONSUMER_KEY,
        "consumer_secret": CONSUMER_SECRET
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(API_URL, json=data, headers=headers)
        response.raise_for_status()
        token_data = response.json()
        return token_data.get("token")
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Token retrieval failed: {str(e)}"
        )

# API Endpoints
@app.options("/submit-order")
@app.options("/register-ipn")
@app.options("/transaction-status")
@app.options("/access-token")
async def options_handler():
    """Handle CORS preflight requests"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

@app.get("/access-token")
async def fetch_access_token():
    """Endpoint to retrieve Pesapal access token"""
    try:
        token = get_access_token()
        return {"token": token}
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": str(e.detail)},
            headers={"Access-Control-Allow-Origin": "*"}
        )

@app.post("/register-ipn")
async def register_ipn(request: IPNRegistrationRequest):
    """Register Instant Payment Notification (IPN) URL"""
    try:
        token = get_access_token()
        ipn_registration_url = f"{BASE_API_URL}/api/URLSetup/RegisterIPN"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        data = {
            "url": request.url,
            "ipn_notification_type": request.ipn_notification_type
        }

        response = requests.post(ipn_registration_url, json=data, headers=headers)
        response.raise_for_status()
        
        ipn_data = response.json()
        return {
            "ipn_id": ipn_data.get("ipn_id"), 
            "ipn_url": ipn_data.get("url")
        }
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400, 
            detail=f"IPN Registration failed: {str(e)}"
        )

@app.post("/submit-order")
async def submit_order(request: PaymentRequest):
    """Submit payment order to Pesapal"""
    try:
        # Get access token
        token = get_access_token()
        
        # Register IPN (you might want to make this configurable)
        ipn_id_req = await register_ipn(
            request=IPNRegistrationRequest(url="https://your-ipn-callback-url.com")
        )
        ipn_id = ipn_id_req.get("ipn_id")
        
        # Generate merchant reference
        merchant_reference = f"Al-{random.randint(1, 10000)}"
        
        # Prepare submit order URL
        submit_order_url = f"{BASE_API_URL}/api/Transactions/SubmitOrderRequest"
        
        # Prepare headers
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        # Prepare order data
        data = {
            "id": merchant_reference,
            "currency": "UGX",
            "amount": request.amount,
            "description": "Thanks For Using Al-Transfer",
            "callback_url": request.callback_url,
            "notification_id": ipn_id,
            "branch": request.branch or "Default Branch",
            "billing_address": {
                "email_address": request.email_address,
                "phone_number": request.phone,
                "country_code": "UG",
                "first_name": request.first_name,
                "middle_name": request.middle_name or "",
                "last_name": request.last_name,
                "line_1": "Pesapal Limited",
                "line_2": "",
                "city": "",
                "state": "",
                "postal_code": "",
                "zip_code": ""
            }
        }
        
        # Submit order to Pesapal
        response = requests.post(submit_order_url, json=data, headers=headers)
        response.raise_for_status()
        
        order_response = response.json()
        order_tracking_id = order_response.get("order_tracking_id")
        
        if not order_tracking_id:
            raise HTTPException(status_code=400, detail="No order tracking ID received")
        
        # Poll transaction status
        transaction_status_url = f"{BASE_API_URL}/api/Transactions/GetTransactionStatus"
        transaction_status = None
        
        for _ in range(10):  # Poll 10 times with delays
            status_response = requests.get(
                f"{transaction_status_url}?orderTrackingId={order_tracking_id}", 
                headers=headers
            )
            if status_response.status_code == 200:
                status_data = status_response.json()
                transaction_status = status_data.get("status")
                if transaction_status in ["COMPLETED", "FAILED"]:
                    break
            time.sleep(5)  # Wait 5 seconds between polls
        
        transaction_status = transaction_status or "PENDING"
        
        return {
            "order_tracking_id": order_tracking_id,
            "status": transaction_status,
            "details": order_response
        }
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Order submission failed: {str(e)}",
            headers={"Access-Control-Allow-Origin": "*"}
        )

@app.get("/transaction-status")
async def transaction_status(orderTrackingId: str):
    """Get transaction status from Pesapal"""
    try:
        token = get_access_token()
        transaction_status_url = f"{BASE_API_URL}/api/Transactions/GetTransactionStatus"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.get(
            f"{transaction_status_url}?orderTrackingId={orderTrackingId}", 
            headers=headers
        )
        response.raise_for_status()
        
        return {"transaction_status": response.json()}
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Failed to fetch transaction status: {str(e)}",
            headers={"Access-Control-Allow-Origin": "*"}
        )

# Health check endpoint
@app.get("/")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "message": "AlTransfer Payment API is running"}
