from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from app.api.http_auth import get_current_user
from app.core.config import settings
from app.repositories.users_repo import UsersRepo

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key


@router.post("/create-checkout-session")
async def create_checkout_session(user: dict = Depends(get_current_user)):
    if not settings.stripe_secret_key or not settings.stripe_price_pro_monthly:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    # Reuse customer if we have one
    customer = user.get("stripe_customer_id")

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer,
        line_items=[{"price": settings.stripe_price_pro_monthly, "quantity": 1}],
        success_url=settings.stripe_success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=settings.stripe_cancel_url,
        metadata={"user_id": user["_id"]},
        allow_promotion_codes=True,
    )

    return {"url": session.url}


@router.post("/create-portal-session")
async def create_portal_session(user: dict = Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    customer = user.get("stripe_customer_id")
    if not customer:
        raise HTTPException(status_code=400, detail="No Stripe customer for this user")

    portal = stripe.billing_portal.Session.create(
        customer=customer,
        return_url=settings.stripe_portal_return_url,
    )
    return {"url": portal.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default="")):
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.stripe_webhook_secret,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {type(e).__name__}: {e}")

    etype = event["type"]
    obj = event["data"]["object"]

    # 1) Checkout completed -> we can store customer id and maybe subscription id
    if etype == "checkout.session.completed":
        user_id = (obj.get("metadata") or {}).get("user_id")
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")

        if user_id and customer_id:
            await UsersRepo.update_stripe_fields(
                user_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                plan="pro",
            )

    # 2) Subscription updated -> plan pro if active, free if not
    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        customer_id = obj.get("customer")
        subscription_id = obj.get("id")
        status = obj.get("status")  # active, trialing, past_due, canceled...
        is_active = status in ("active", "trialing")

        # find user by customer id
        db = __import__("app.core.db", fromlist=["get_db"]).get_db()
        user = await db.users.find_one({"stripe_customer_id": customer_id})
        if user:
            await UsersRepo.update_stripe_fields(
                user["_id"],
                stripe_subscription_id=subscription_id,
                plan="pro" if is_active else "free",
            )

    # 3) Subscription deleted -> free
    elif etype == "customer.subscription.deleted":
        customer_id = obj.get("customer")
        db = __import__("app.core.db", fromlist=["get_db"]).get_db()
        user = await db.users.find_one({"stripe_customer_id": customer_id})
        if user:
            await UsersRepo.update_stripe_fields(
                user["_id"],
                stripe_subscription_id=None,
                plan="free",
            )

    return {"received": True}