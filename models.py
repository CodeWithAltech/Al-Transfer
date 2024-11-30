from pydantic import BaseModel


# Models
class PaymentRequest(BaseModel):
    phone: str
    amount: int
    callback_url: str
    branch: str
    first_name: str
    middle_name: str
    last_name: str
    email_address: str

class TransactionStatusRequest(BaseModel):
    order_tracking_id: str
    order_merchant_reference: str
