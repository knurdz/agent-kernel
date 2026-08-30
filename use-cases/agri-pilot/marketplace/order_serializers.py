"""Serialize orders for API responses."""

from __future__ import annotations

from marketplace.models import Order
from marketplace.schemas import OrderResponse


def order_to_response(order: Order) -> OrderResponse:
    delivery = order.delivery
    return OrderResponse(
        id=order.id,
        connection_id=order.connection_id,
        listing_id=order.listing_id,
        buyer_id=order.buyer_id,
        farmer_id=order.farmer_id,
        crop=order.crop,
        quantity_kg=order.quantity_kg,
        price_per_kg=order.price_per_kg,
        fulfillment_mode=order.fulfillment_mode,
        status=order.status,
        pickup_address_label=order.pickup_address_label,
        pickup_latitude=order.pickup_latitude,
        pickup_longitude=order.pickup_longitude,
        delivery_address_label=order.delivery_address_label,
        delivery_latitude=order.delivery_latitude,
        delivery_longitude=order.delivery_longitude,
        cancellation_reason=order.cancellation_reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
        delivery_id=delivery.id if delivery else None,
        delivery_status=delivery.status if delivery else None,
    )
