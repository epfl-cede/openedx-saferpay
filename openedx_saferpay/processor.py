import base64
import json
import logging
import simplejson.errors
from urllib.parse import urljoin
from uuid import uuid4

from django.urls import reverse
from oscar.apps.payment.exceptions import GatewayError
import requests

from ecommerce.core.url_utils import get_ecommerce_url
from ecommerce.extensions.payment.processors import (
    BasePaymentProcessor,
    HandledProcessorResponse,
)

logger = logging.getLogger(__name__)


class Saferpay(BasePaymentProcessor):
    """
    Implement the Saferpay payment processor. Documentation can be found at the following urls:

    High-lever overview: https://saferpay.github.io/sndbx/Integration_PP.html
    API documentation: https://saferpay.github.io/jsonapi/index.html#ChapterPaymentPage

    The payment process is as follows:

    1. Initiate a payment with get_transaction_parameters
    2. Redirect the user to the payment page
    3. After payment, the user is redirected to one of the success or failure callback pages
    4. In the success callback page, we check whether the payment was successfully made with handle_processor_response

    The payment processor is supposed to be configured as follows:

        saferpay:
            api_username: API_ABC_DEF
            api_password: JsonApiPwdX_XXXX
            customer_id: 'ABC'
            terminal_id: 'GHI'
            # api_url is optional: in testing set to https://test.saferpay.com/api/
            # api_url: https://www.saferpay.com/api/
    """

    NAME = "saferpay"
    TITLE = "Saferpay"
    API_REQUEST_TIMEOUT_SECONDS = 10
    API_URL = "https://www.saferpay.com/api/"

    def __init__(self, site):
        super().__init__(site)
        self.api_url = self.configuration.get("api_url", self.API_URL)
        self.api_username = self.configuration["api_username"]
        self.api_password = self.configuration["api_password"]
        self.customer_id = self.configuration["customer_id"]
        self.terminal_id = self.configuration["terminal_id"]

        self.error_url = reverse("checkout:error")
        self.cancel_url = reverse("checkout:cancel-checkout")

    def get_transaction_parameters(
        self, basket, request=None, use_client_side_checkout=False, **kwargs
    ):
        """
        Fetch a payment page url from the Saferpay API and redirect the user to this url.

        Documentation:
        https://saferpay.github.io/sndbx/Integration_PP.html#pp-initialize
        https://saferpay.github.io/jsonapi/index.html#Payment_v1_PaymentPage_Initialize
        """
        # Create PPR early to obtain an ID that can be passed to the return urls
        success_payment_processor_response = self.record_processor_response(
            {}, transaction_id=None, basket=basket
        )
        description = "\n".join([line.product.title for line in basket.lines.all()])
        data = {
            "TerminalId": self.terminal_id,
            "Payment": {
                "Amount": {
                    # Amount in cents
                    "Value": str(int(100 * basket.total_incl_tax)),
                    "CurrencyCode": basket.currency,
                },
                "OrderId": str(basket.order_number),
                "Description": description,
            },
            "ReturnUrls": {
                "Success": get_ecommerce_url(
                    reverse(
                        "saferpay:callback_success",
                        kwargs={"ppr_id": success_payment_processor_response.id},
                    )
                ),
                "Fail": get_ecommerce_url(self.cancel_url),
            },
        }
        response_data = self.make_api_json_request(
            "Payment/v1/PaymentPage/Initialize", method="POST", data=data, basket=basket
        )

        try:
            payment_page_url = response_data["RedirectUrl"]
            transaction_id = response_data["Token"]
        except KeyError:
            message = "Could not parse RedirectUrl field from response: content={}".format(
                json.dumps(response_data)
            )
            self.raise_api_error(basket, message)

        # Save payment processor response
        success_payment_processor_response.transaction_id = transaction_id
        success_payment_processor_response.response = response_data
        success_payment_processor_response.save()

        logger.info(
            "Saferpay payment: obtained token=%s for basket=%d",
            transaction_id,
            basket.id,
        )
        return {"payment_page_url": payment_page_url}

    def handle_processor_response(self, response, basket=None):
        """
        Verify that the payment was successfully processed -- because Trust but Verify.
        https://saferpay.github.io/jsonapi/index.html#Payment_v1_PaymentPage_Assert
        If payment did not succeed, raise GatewayError and log error.

        Once payment has been verified, call Capture to finalize the payment
        https://saferpay.github.io/jsonapi/index.html#Payment_v1_Transaction_Capture
        The generated CaptureId will be used to generate refunds.

        Args:
            response (str): this is actually the request token.
        """
        token = response
        assert_request_data = {"Token": token}

        # Check payment was successful (this will raise in case of invalid payment)
        assert_data = self.make_api_json_request(
            "Payment/v1/PaymentPage/Assert",
            method="POST",
            data=assert_request_data,
            basket=basket,
        )
        total = int(assert_data["Transaction"]["Amount"]["Value"]) / 100.0
        currency = assert_data["Transaction"]["Amount"]["CurrencyCode"]
        card_number = assert_data["PaymentMeans"]["Card"]["MaskedNumber"]
        card_type = assert_data["PaymentMeans"]["Brand"]["PaymentMethod"]
        transaction_id = assert_data["Transaction"]["Id"]

        # Finalize payment
        capture_request_data = {
            "TransactionReference": {"TransactionId": transaction_id}
        }
        capture_data = self.make_api_json_request(
            "Payment/v1/Transaction/Capture",
            method="POST",
            data=capture_request_data,
            basket=basket,
        )
        capture_id = capture_data["CaptureId"]

        return HandledProcessorResponse(
            transaction_id=capture_id,
            total=total,
            currency=currency,
            card_number=card_number,
            card_type=card_type,
        )

    def issue_credit(self, order_number, basket, reference_number, amount, currency):
        """
        Refund transaction: https://saferpay.github.io/jsonapi/index.html#Payment_v1_Transaction_Refund
        Assert refund: https://saferpay.github.io/jsonapi/index.html#Payment_v1_Transaction_AssertRefund
        Note that this is only available to business license owners.
        """
        # Issue refund
        capture_id = reference_number
        refund_request_data = {
            "Refund": {
                "Amount": {"Value": str(int(amount * 100)), "CurrencyCode": currency}
            },
            "CaptureReference": {"CaptureId": capture_id},
        }
        refund_data = self.make_api_json_request(
            "Payment/v1/Transaction/Refund",
            method="POST",
            data=refund_request_data,
            basket=basket,
        )
        transaction_id = refund_data["Transaction"]["Id"]

        # Check refund has gone through: note this is only necessary for paydirekt transactions, so we just ignore this
        # for now
        # assert_request_data = {
        #     "TransactionReference": {"TransactionId": transaction_id}
        # }
        # assert_data = self.make_api_json_request(
        #     "Payment/v1/Transaction/AssertRefund",
        #     method="POST",
        #     data=assert_request_data,
        #     basket=basket,
        # )

        self.record_processor_response(
            refund_data, transaction_id=transaction_id, basket=basket
        )
        return transaction_id

    def get_base_request_data(self, retry_indicator=0):
        request_id = str(uuid4())  # TODO log request ID
        return {
            "RequestHeader": {
                "SpecVersion": "1.19",
                "CustomerId": self.customer_id,
                "RequestId": request_id,
                "RetryIndicator": retry_indicator,  # TODO implement retry
            }
        }

    def make_api_json_request(self, endpoint, method="GET", data=None, basket=None):
        requests_func = getattr(requests, method.lower())
        url = urljoin(self.api_url, endpoint)

        # Basic auth: https://saferpay.github.io/jsonapi/index.html#authentication
        encoded_auth = base64.b64encode(
            "{}:{}".format(self.api_username, self.api_password).encode()
        ).decode()
        headers = {"Authorization": "Basic {}".format(encoded_auth)}

        # Add standard request data
        request_data = self.get_base_request_data()
        request_data.update(data)

        try:
            # pylint: disable=not-callable
            response = requests_func(
                url,
                json=request_data,
                headers=headers,
                timeout=self.API_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout:
            self.raise_api_error("API timeout", None, {}, basket)

        try:
            response_data = response.json()
        except (json.JSONDecodeError, simplejson.errors.JSONDecodeError):
            self.raise_api_error(
                "Could not parse JSON content from response", response, {}, basket
            )
        if response.status_code != 200:
            self.raise_api_error(
                "Invalid API response", response, response_data, basket
            )
        return response_data

    def raise_api_error(self, message, response=None, response_data=None, basket=None):
        error_response = None
        if response is not None:
            error_response = {
                "status_code": response.status_code,
                "content": response.content.decode(),
                "data": response_data,
            }
        error = {"message": message, "response": error_response}
        entry = self.record_processor_response(
            error, transaction_id=basket.order_number if basket else None, basket=basket
        )
        logger.error(
            u"Failed request to Saferpay API for basket [%d], response stored in entry [%d].",
            basket.id if basket else None,
            entry.id,
            exc_info=True,
        )
        raise GatewayError(error)
