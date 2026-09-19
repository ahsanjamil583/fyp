"""Owner controls for order confirmation messages."""

from pydantic import BaseModel, Field


class OrderMessageSettingsRequest(BaseModel):
    """Which confirmations this business sends, and on which channels.

    Defaults are on: a business that has never opened this page still confirms orders,
    which is the behaviour a customer expects.
    """

    emailEnabled: bool = True
    whatsappEnabled: bool = True
    sendOnOrderPlaced: bool = True
    sendOnPaymentConfirmed: bool = True
    footerNote: str = Field(default="", max_length=300)
