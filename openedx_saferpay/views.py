import logging

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import View

from oscar.apps.partner import strategy
from oscar.apps.payment.exceptions import PaymentError
from oscar.core.loading import get_model

from ecommerce.extensions.checkout.mixins import EdxOrderPlacementMixin
from ecommerce.extensions.checkout.utils import get_receipt_page_url

from .processor import Saferpay

logger = logging.getLogger(__name__)
PaymentProcessorResponse = get_model("payment", "PaymentProcessorResponse")


class SaferpaySuccessCallbackView(EdxOrderPlacementMixin, View):
    """Execute an approved PayPal payment and place an order for paid products as appropriate."""

    @property
    def payment_processor(self):
        return Saferpay(self.request.site)

    @method_decorator(transaction.non_atomic_requests)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, ppr_id):
        ppr = get_object_or_404(PaymentProcessorResponse, id=ppr_id)
        basket = ppr.basket
        basket.strategy = strategy.Default()

        # What follows is basically a copy-paste from paypal's GET view handler
        receipt_url = get_receipt_page_url(
            request,
            order_number=basket.order_number,
            site_configuration=basket.site.siteconfiguration,
            disable_back_button=True,
        )

        try:
            with transaction.atomic():
                try:
                    self.handle_payment(ppr.transaction_id, basket)
                except PaymentError:
                    return redirect(self.payment_processor.error_url)
        except PaymentError:
            return redirect(self.payment_processor.error_url)
        except:  # pylint: disable=bare-except
            logger.exception(
                "Attempts to handle payment for basket [%d] failed.", basket.id
            )
            return redirect(receipt_url)

        try:
            order = self.create_order(request, basket)
        except Exception:  # pylint: disable=broad-except
            return redirect(receipt_url)

        try:
            self.handle_post_order(order)
        except Exception:  # pylint: disable=broad-except
            self.log_order_placement_exception(basket.order_number, basket.id)

        return redirect(receipt_url)
