"""Live audit: credentials from stdin; only login POSTs and selected read endpoints."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[2] / "docs" / "live-audit-evidence.json"
records = []
client = httpx.Client(base_url=BASE, timeout=25)


def call(role, method, path, token=None, payload=None):
    start = time.monotonic()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = client.request(method, path, headers=headers, json=payload)
        try:
            body = response.json()
        except ValueError:
            body = {}
        data = body.get("data") if isinstance(body, dict) else None
        row = {"role": role, "method": method, "path": path, "status": response.status_code,
               "ms": round((time.monotonic()-start)*1000)}
        if response.status_code >= 400:
            row["error"] = body.get("detail", body.get("message", "Non-JSON server error"))
        elif isinstance(data, dict):
            row["keys"] = sorted(data)
            row["listCounts"] = {k: len(v) for k,v in data.items() if isinstance(v,list)}
        elif isinstance(data, list):
            row["count"] = len(data)
        records.append(row)
        print(json.dumps(row), flush=True)
        return data, body
    except Exception as exc:
        row = {"role":role,"method":method,"path":path,"error":type(exc).__name__,"ms":round((time.monotonic()-start)*1000)}
        records.append(row)
        print(json.dumps(row),flush=True)
        return None, {}


credentials = json.load(sys.stdin)
credentials["admin"] = {"email":settings.default_admin_email,"password":settings.default_admin_password}
tokens = {}
identity = {}
for role, cred in credentials.items():
    if not cred.get("email") or not cred.get("password"):
        continue
    prefix = "/api/v1/customer/auth" if role == "customer" else "/api/v1/auth"
    data,_ = call(role,"POST",prefix+"/login",payload=cred)
    if data and data.get("accessToken"):
        tokens[role] = data["accessToken"]
        user=data.get("user",{})
        identity[role]={k:user.get(k) for k in ("accountType","globalRole","status","mustResetPassword","isEmailVerified")}
        call(role,"GET",prefix+"/me",tokens[role])

call("anonymous","GET","/api/v1/health")
readiness,_=call("anonymous","GET","/api/v1/health/readiness")
for path in ("/api/v1/auth/me","/api/v1/customer/auth/me","/api/v1/tenants/my","/api/v1/admin/overview","/api/v1/public/business-categories","/api/v1/modules","/api/v1/customer/marketplace","/api/v1/whatsapp/bridge/tenants"):
    call("anonymous","GET",path)

tenant_summaries=[]
public_summaries=[]
business_token=tokens.get("business")
tenants=[]
if business_token:
    tenants,_=call("business","GET","/api/v1/tenants/my",business_token)
    tenants=tenants if isinstance(tenants,list) else []
    call("business","GET","/api/v1/admin/overview",business_token)
    for tenant in tenants:
        tid=tenant["id"]
        tenant_summaries.append({k:tenant.get(k) for k in ("id","slug","status","websiteStatus","websiteApprovalStatus","enabledModuleCodes")})
        tenant_summaries[-1]["plan"]=(tenant.get("settings") or {}).get("planCode")
        suffixes=["","/modules","/launch/status","/items","/item-categories","/custom-fields","/customers","/customers/insights","/transactions","/notifications","/analytics/summary","/payments/settings","/payments/overview","/knowledge-base","/ai/conversations","/ai/rag/status","/agent/tools","/owner-agent/history","/reports/delivery/settings","/reports/delivery/logs","/whatsapp/settings","/whatsapp/conversations"]
        for suffix in suffixes:
            data,_=call("business","GET",f"/api/v1/tenants/{tid}"+suffix,business_token)
            if suffix in ("/items","/customers","/knowledge-base","/ai/conversations"):
                items=data if isinstance(data,list) else (data or {}).get("items",[])
                if items and isinstance(items[0],dict) and items[0].get("id"):
                    call("business","GET",f"/api/v1/tenants/{tid}{suffix}/{items[0]['id']}",business_token)
        slug=tenant.get("slug")
        for suffix in ("","/items"):
            data,_=call("anonymous","GET",f"/api/v1/public/businesses/{slug}"+suffix)
            if suffix=="" and isinstance(data,dict):
                public_summaries.append({"slug":slug,"internalFieldsPresent":[k for k in ("ownerUserId","websiteApprovalReviewedBy","websiteApprovalNote","websiteApprovalCriteria","rag") if k in data],"settingsKeys":sorted((data.get("settings") or {}).keys())})
        if tokens.get("customer"):
            call("customer","GET",f"/api/v1/tenants/{tid}/items",tokens["customer"])

if tokens.get("customer"):
    tok=tokens["customer"]
    for path in ("/api/v1/customer/marketplace","/api/v1/customer/cart","/api/v1/customer/favorites","/api/v1/customer/orders","/api/v1/customer/transactions","/api/v1/customer/notifications","/api/v1/tenants/my","/api/v1/admin/overview"):
        data,_=call("customer","GET",path,tok)
        if path.endswith("/marketplace"):
            businesses=data if isinstance(data,list) else (data or {}).get("items",[])
            for b in businesses[:3]:
                if not isinstance(b,dict) or not b.get("slug"): continue
                for suffix in ("","/items"):
                    call("customer","GET",f"/api/v1/customer/businesses/{b['slug']}"+suffix,tok)
        if path.endswith("/orders"):
            orders=data if isinstance(data,list) else (data or {}).get("items",[])
            for order in orders[:3]:
                oid=order.get("id")
                if oid:
                    call("customer","GET",f"/api/v1/customer/orders/{oid}",tok)
                    if business_token:call("business","GET",f"/api/v1/customer/orders/{oid}",business_token)

if tokens.get("admin"):
    for suffix in ("overview","reports","payments","users","tenants","modules","business-categories"):
        call("admin","GET","/api/v1/admin/"+suffix,tokens["admin"])

# Retain only structural/configuration diagnostics, never provider secrets.
def clean(value):
    if isinstance(value,dict):
        return {k:('[redacted]' if any(word in k.lower() for word in ('password','secret','token','apikey','uri','recipient','email','phone')) else clean(v)) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    return value

result={"timestamp":datetime.now(timezone.utc).isoformat(),"baseUrl":BASE,"identity":identity,"tenants":tenant_summaries,"publicExposure":public_summaries,"readiness":clean(readiness),"requests":records}
OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
print('Evidence saved:',OUT,flush=True)
client.close()
