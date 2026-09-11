"""Focused live audit. No order creation, OTP delivery, payments or account changes."""
import json
import smtplib
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import settings

out=Path(__file__).resolve().parents[2]/'docs'/'live-audit-followup.json'
creds=json.load(sys.stdin)
c=httpx.Client(base_url='http://127.0.0.1:8000',timeout=55,limits=httpx.Limits(max_keepalive_connections=0))
evidence=[]
def save(row):
    evidence.append(row)
    out.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(row),flush=True)
def req(label,path,token=None,method='GET',payload=None):
    start=time.monotonic()
    try:
        r=c.request(method,path,headers={'Authorization':f'Bearer {token}'} if token else {},json=payload)
        try:b=r.json()
        except ValueError:b={}
        row={'test':label,'method':method,'path':path,'status':r.status_code,'ms':round((time.monotonic()-start)*1000)}
        if r.status_code>=400:row['error']=b.get('detail','non-JSON response')
        save(row)
        return b.get('data'),r
    except Exception as exc:
        save({'test':label,'path':path,'error':type(exc).__name__})
        return None,None

tokens={}
for role,cred in creds.items():
    p='/api/v1/customer/auth/login' if role=='customer' else '/api/v1/auth/login'
    d,r=req(role+' login',p,method='POST',payload=cred)
    tokens[role]=d['accessToken']
bt,ct=tokens['business'],tokens['customer']
tenants,_=req('Owner tenants','/api/v1/tenants/my',bt)
t=tenants[0]; tid=t['id']; slug=t['slug']
market,_=req('Marketplace','/api/v1/customer/marketplace',ct)
other=next((b for b in market if b['id']!=tid),None)
if other:
    req('Cross-tenant owner access',f"/api/v1/tenants/{other['id']}/items",bt)
req('Invalid item ID',f'/api/v1/public/businesses/{slug}/items/invalid')
req('Literal bracket search',f'/api/v1/public/businesses/{slug}/items?search=%5B')
req('Normal search',f'/api/v1/public/businesses/{slug}/items?search=shirt')
req('Overlong login password','/api/v1/auth/login',method='POST',payload={'email':creds['business']['email'],'password':'Aa9!'*20})

data,r=req('Public business fields',f'/api/v1/public/businesses/{slug}')
save({'test':'Public internal metadata','internalKeys':[k for k in data if k.startswith('websiteApproval') or k=='ownerUserId'],'packageAccessVisible':'packageAccess' in data.get('settings',{}),'planCode':data.get('settings',{}).get('planCode')})
orders,_=req('Customer orders','/api/v1/customer/orders',ct)
for order in orders[:2]:
    detail,_=req('Order privacy',f"/api/v1/customer/orders/{order['id']}",ct)
    save({'test':'Order internal fields','orderId':order['id'],'internalNotesPresent':'internalNotes' in detail,'internalNotesNonempty':bool(detail.get('internalNotes')),'inventoryMovementCount':len(detail.get('inventoryMovements',[])),'movementFieldNames':sorted(detail['inventoryMovements'][0]) if detail.get('inventoryMovements') else []})

items,_=req('Public catalog',f'/api/v1/public/businesses/{slug}/items')
for item in items[:4]:
    save({'test':'Public catalog data','name':item.get('name'),'price':item.get('price'),'costPriceExposed':'costPrice' in item,'stockKeys':sorted((item.get('stock') or {}).keys()),'imageCount':len(item.get('images') or [])})
    for image in (item.get('images') or [])[:1]:
        url=image.get('url','')
        if url.startswith('/uploads/'):
            response=c.get(url)
            save({'test':'Local product image','status':response.status_code,'contentType':response.headers.get('content-type'),'bytes':len(response.content)})

for path in ('/','/login','/customer/login','/dashboard','/admin','/businesses/'+slug,'/src/assets/bizxus-logo.png'):
    try:
        r=httpx.get('http://localhost:5173'+path,timeout=15)
        save({'test':'Frontend HTTP delivery (not rendered)','path':path,'status':r.status_code,'contentType':r.headers.get('content-type'),'bytes':len(r.content)})
    except Exception as exc:save({'test':'Frontend HTTP delivery','path':path,'error':type(exc).__name__})
r=c.options('/api/v1/auth/me',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization'})
save({'test':'CORS preflight','status':r.status_code,'allowedOrigin':r.headers.get('access-control-allow-origin')})

wa,_=req('WhatsApp settings',f'/api/v1/tenants/{tid}/whatsapp/settings',bt)
w=wa.get('settings',{})
save({'test':'WhatsApp state','state':{k:v for k,v in w.items() if k in ('provider','isConnected','connectionStatus','bridgeStatus','lastBridgeSeenAt','lastConnectedAt','lastError','pairingUrl')}})
bridge_url=settings.whatsapp_bridge_public_url
try:
    r=httpx.get(bridge_url.rstrip('/')+'/health',timeout=5)
    save({'test':'Configured bridge health','url':bridge_url,'status':r.status_code})
except Exception as exc:save({'test':'Configured bridge health','url':bridge_url,'error':type(exc).__name__})

save({'test':'Integration modes','smsProvider':settings.sms_provider,'emailProvider':settings.email_provider,'smtpHost':settings.smtp_host,'smtpPort':settings.smtp_port,'smtpUsernamePresent':bool(settings.smtp_username),'smtpPasswordPresent':bool(settings.smtp_password),'otpDemoMode':settings.otp_demo_mode,'jazzcashMode':settings.jazzcash_mode,'easypaisaMode':settings.easypaisa_mode,'stripeKeyPresent':bool(settings.stripe_secret_key),'stripeUsesTestKey':settings.stripe_secret_key.startswith('sk_test_'),'groqModel':settings.groq_model})
try:
    with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=12) as smtp:
        smtp.ehlo(); smtp.starttls(); smtp.ehlo()
        code,_=smtp.login(settings.smtp_username,''.join(settings.smtp_password.split()))
        save({'test':'SMTP connection/TLS/authentication; no message sent','statusCode':code})
except Exception as exc:
    save({'test':'SMTP connection/TLS/authentication; no message sent','error':type(exc).__name__,'smtpCode':getattr(exc,'smtp_code',None)})

# Preview calls do not persist chats or create orders; hosted AI may be invoked.
name=items[0]['name'] if items else 'shirt'
for message in ('Assalam o Alaikum',f'{name} ki price kya hai?',f'I want 1 {name}'):
    d,r=req('AI preview',f'/api/v1/tenants/{tid}/agent/preview',bt,method='POST',payload={'messageText':message,'channel':'customer_portal','includeRecentMessages':False})
    if d:
        save({'test':'AI preview result','message':message,'reply':d.get('reply'),'meta':d.get('meta'),'ragSourceCount':len(d.get('ragSources',[])),'draftItemCount':len((d.get('draftOrder') or {}).get('items',[]))})
c.close()
