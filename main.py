import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import random
import json
from models import PaymentRequest, TransactionStatusRequest

#Configurations
APP_ENVIRONMENT = "live"

# Pesapal API credentials
if APP_ENVIRONMENT == 'sandbox':
    API_URL = "https://cybqa.pesapal.com/pesapalv3/api/Auth/RequestToken"
    CONSUMER_KEY = "TDpigBOOhs+zAl8cwH2Fl82jJGyD8xev"
    CONSUMER_SECRET = "1KpqkfsMaihIcOlhnBo/gBZ5smw="
    
elif APP_ENVIRONMENT == 'live':
    API_URL = "https://pay.pesapal.com/v3/api/Auth/RequestToken"
    CONSUMER_KEY = "BopfGlE7GfenAqGvS5SGdke4M67WLFxh"
    CONSUMER_SECRET = "nnYh5QSFZUXRsQu6PQI4llLB5iU="
else:
    raise Exception("Invalid APP_ENVIRONMENT")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,         
    allow_methods=["*"],             
    allow_headers=["*"],
)


class IPNRegistrationRequest(BaseModel):
    url: str
    ipn_notification_type: str = "POST"

# Function to get access token
def get_access_token():
    data = {
        "consumer_key": CONSUMER_KEY,
        "consumer_secret": CONSUMER_SECRET
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    response = requests.post(API_URL, json=data, headers=headers)
    
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to fetch token. Response: {response.text}")
    
    token_data = response.json()
    return token_data.get("token")

# Endpoint to get access token
@app.get("/access-token")
async def fetch_access_token():
    try:
        token = get_access_token()
        return {"token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint to register IPN
@app.post("/register-ipn")
async def register_ipn(request: IPNRegistrationRequest):
    token = get_access_token()
    ipn_url = "https://93c7-102-86-10-172.ngrok-free.app"  #Actual IPN URL
    ipn_registration_url = "https://cybqa.pesapal.com/pesapalv3/api/URLSetup/RegisterIPN" if APP_ENVIRONMENT == 'sandbox' else "https://pay.pesapal.com/v3/api/URLSetup/RegisterIPN"
    
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
    
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"IPN Registration failed. Response: {response.text}")
    
    ipn_data = response.json()
    return {"ipn_id": ipn_data.get("ipn_id"), "ipn_url": ipn_data.get("url")}



# Endpoint to submit order and handle transaction status
@app.post("/submit-order")
async def submit_order(request: PaymentRequest):
    token = get_access_token()
    ipn_id_req = await register_ipn(request=IPNRegistrationRequest(url="https://93c7-102-86-10-172.ngrok-free.app"))
    ipn_id = ipn_id_req.get("ipn_id")
    merchant_reference = f"Al-{random.randint(1, 10000)}"
    
    submit_order_url = (
        "https://cybqa.pesapal.com/pesapalv3/api/Transactions/SubmitOrderRequest"
        if APP_ENVIRONMENT == 'sandbox'
        else "https://pay.pesapal.com/v3/api/Transactions/SubmitOrderRequest"
    )
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    data = {
        "id": merchant_reference,
        "currency": "UGX",
        "amount": request.amount,
        "description": "Thanks For Using Al-Transfer",
        "callback_url": request.callback_url,
        "notification_id": ipn_id,
        "branch": request.branch,
        "billing_address": {
            "email_address": request.email_address,
            "phone_number": request.phone,
            "country_code": "UG",
            "first_name": request.first_name,
            "middle_name": request.middle_name,
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
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to submit order. Response: {response.text}")
    
    order_response = response.json()
    order_tracking_id = order_response.get("order_tracking_id")
    
    if not order_tracking_id:
        raise HTTPException(status_code=400, detail="No order tracking ID received.")
    
    # Poll transaction status
    transaction_status_url = (
        "https://cybqa.pesapal.com/pesapalv3/api/Transactions/GetTransactionStatus"
        if APP_ENVIRONMENT == 'sandbox'
        else "https://pay.pesapal.com/v3/api/Transactions/GetTransactionStatus"
    )
    
    transaction_status = None
    for _ in range(10):  # Poll 10 times with delays
        status_response = requests.get(
            f"{transaction_status_url}?orderTrackingId={order_tracking_id}", headers=headers
        )
        if status_response.status_code == 200:
            status_data = status_response.json()
            transaction_status = status_data.get("status")
            if transaction_status in ["COMPLETED", "FAILED"]:
                break
        time.sleep(5)  # Wait 5 seconds between polls
    
    if not transaction_status:
        transaction_status = "PENDING"
    
    return {
        "order_tracking_id": order_tracking_id,
        "status": transaction_status,
        "details": order_response
    }
# # Endpoint to submit order
# @app.post("/submit-order")
# async def submit_order(request: PaymentRequest):
    
#     token = get_access_token()
#     ipn_id_req = await register_ipn(request=IPNRegistrationRequest(url="https://93c7-102-86-10-172.ngrok-free.app"))
    
#     ipn_id = ipn_id_req.get("ipn_id")
    
#     merchant_reference = f"Al-{random.randint(1, 10000)}"
    
#     submit_order_url = "https://cybqa.pesapal.com/pesapalv3/api/Transactions/SubmitOrderRequest" if APP_ENVIRONMENT == 'sandbox' else "https://pay.pesapal.com/v3/api/Transactions/SubmitOrderRequest"
    
#     headers = {
#         "Accept": "application/json",
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {token}"
#     }
    
#     data = {
#         "id": merchant_reference,
#         "currency": "UGX",
#         "amount": request.amount,
#         "description": "Thanks For Using Al-Transfer",
#         "callback_url": request.callback_url,
#         "notification_id": ipn_id,
#         "branch": request.branch,
#         "billing_address": {
#             "email_address": request.email_address,
#             "phone_number": request.phone,
#             "country_code": "UG",
#             "first_name": request.first_name,
#             "middle_name": request.middle_name,
#             "last_name": request.last_name,
#             "line_1": "Pesapal Limited",
#             "line_2": "",
#             "city": "",
#             "state": "",
#             "postal_code": "",
#             "zip_code": ""
#         }
#     }
    
#     response = requests.post(submit_order_url, json=data, headers=headers)
    
#     if response.status_code != 200:
#         raise HTTPException(status_code=400, detail=f"Failed to submit order. Response: {response.text}")
    
#     return {"order_status": response.json()}


# Endpoint to get transaction status
@app.get("/transaction-status")
async def transaction_status(request: TransactionStatusRequest):
    token = get_access_token()
    transaction_status_url = f"https://cybqa.pesapal.com/pesapalv3/api/Transactions/GetTransactionStatus?orderTrackingId={request.order_tracking_id}" if APP_ENVIRONMENT == 'sandbox' else f"https://pay.pesapal.com/v3/api/Transactions/GetTransactionStatus?orderTrackingId={request.order_tracking_id}"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    response = requests.get(transaction_status_url, headers=headers)
    
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to fetch transaction status. Response: {response.text}")
    
    return {"transaction_status": response.json()}
