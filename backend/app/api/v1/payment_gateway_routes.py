"""Redirect payment gateways: JazzCash and Easypaisa.

These are the endpoints the gateway itself talks to:

* the gateway returns the customer to ``/callback`` with a signed result,
* ``/simulator`` stands in for the gateway while merchant credentials are pending.

Both are public because a gateway, not a signed-in user, is what calls them. The callback
signature is the only thing that makes a result trustworthy, which is checked in
``complete_gateway_payment``. Starting a checkout is a customer action and lives in
``customer_portal_routes`` instead, under the ``/customer/`` prefix that the web client
uses to decide which access token to send.
"""

from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.payment_service import (
    apply_simulated_gateway_result,
    complete_gateway_payment,
    get_gateway_simulator_context,
)

router = APIRouter(prefix="/payments", tags=["payment-gateways"])


async def _read_callback_payload(request: Request) -> dict:
    """Gateways post form data, but some configurations return JSON or query args."""
    payload: dict = dict(request.query_params)
    try:
        form = await request.form()
        payload.update({key: str(value) for key, value in form.items()})
    except Exception:
        pass
    if not payload:
        try:
            body = await request.json()
            if isinstance(body, dict):
                payload.update({key: str(value) for key, value in body.items()})
        except Exception:
            pass
    return payload


@router.api_route("/{provider}/callback", methods=["GET", "POST"])
async def gateway_callback(provider: str, request: Request):
    payload = await _read_callback_payload(request)
    result = await complete_gateway_payment(provider.lower(), payload)
    # The customer's browser is what lands here, so send them back to the order page.
    return RedirectResponse(url=result["redirectUrl"], status_code=303)


@router.get("/{provider}/simulator/{txnRef}", response_class=HTMLResponse)
async def gateway_simulator(provider: str, txnRef: str):
    context = await get_gateway_simulator_context(provider.lower(), txnRef)
    return HTMLResponse(_render_simulator_page(context))


@router.post("/{provider}/simulator/{txnRef}", response_class=HTMLResponse)
async def gateway_simulator_submit(provider: str, txnRef: str, request: Request):
    form = await request.form()
    approve = str(form.get("outcome", "")).lower() == "approve"
    result = await apply_simulated_gateway_result(provider.lower(), txnRef, approve)
    return RedirectResponse(url=result["redirectUrl"], status_code=303)


def _render_simulator_page(context: dict) -> str:
    """A stand-in for the gateway's hosted page.

    It is deliberately labelled as a simulation on every surface: the one thing worse
    than not having the real gateway is someone believing a real payment was taken.
    """
    label = escape(context["label"])
    amount = f"{context['amount']:,.2f}"
    currency = escape(context["currency"])
    business = escape(context["businessName"] or "this business")
    reference = escape(context["transactionNumber"] or context["txnRef"])
    already = context.get("alreadyPaid")

    action = f"/api/v1/payments/{escape(context['provider'])}/simulator/{escape(context['txnRef'])}"
    buttons = (
        '<p class="done">This payment has already been completed.</p>'
        if already
        else (
            f'<form method="post" action="{action}">'
            '<button class="pay" name="outcome" value="approve" type="submit">Pay '
            f'{currency} {amount}</button>'
            '<button class="cancel" name="outcome" value="cancel" type="submit">Cancel payment</button>'
            "</form>"
        )
    )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{label} payment (simulated)</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f1f5f9;color:#0f172a}}
main{{max-width:460px;margin:48px auto;padding:0 16px}}
.card{{background:#fff;border-radius:20px;padding:28px;box-shadow:0 20px 50px #0f172a1a}}
.banner{{background:#fef3c7;border:1px solid #fcd34d;color:#78350f;border-radius:12px;
padding:12px 14px;font-size:13px;line-height:1.5;margin-bottom:20px}}
h1{{font-size:22px;margin:0 0 4px}}
.muted{{color:#64748b;font-size:14px;margin:0 0 18px}}
dl{{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:14px;margin:0 0 22px}}
dt{{color:#64748b}} dd{{margin:0;text-align:right;font-weight:600}}
.amount{{font-size:28px;font-weight:800;text-align:center;margin:6px 0 22px}}
button{{width:100%;font:inherit;font-weight:700;border-radius:12px;padding:13px;
cursor:pointer;border:1px solid transparent;margin-bottom:10px}}
.pay{{background:#047857;color:#fff}} .cancel{{background:#fff;border-color:#cbd5e1;color:#334155}}
.done{{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;border-radius:12px;
padding:12px;text-align:center;font-weight:700}}
</style></head><body><main><div class="card">
<div class="banner"><strong>Simulated payment page.</strong> No real money moves here.
This stands in for {label} until merchant credentials are configured.</div>
<h1>{label}</h1>
<p class="muted">Paying {business}</p>
<div class="amount">{currency} {amount}</div>
<dl><dt>Order</dt><dd>{reference}</dd><dt>Reference</dt><dd>{escape(context['txnRef'])}</dd></dl>
{buttons}
</div></main></body></html>"""
