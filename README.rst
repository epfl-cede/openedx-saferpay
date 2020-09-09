==================================================================================
`Saferpay <https://www.six-payment-services.com>`__ payment processor for Open edX
==================================================================================

This is a payment processor for the `Ecommerce <https://edx-ecommerce.readthedocs.io/en/latest/>`__ application from `Open edX <https://open.edx.org/>`__. It allows customers who subscribe to paying courses to pay using the Saferpay payment system from `Six Payment Services <https://www.six-payment-services.com>`__.

Installation
============

This plugin was created by `Overhang.io <https://overhang.io>`__ to work specifically with the `Tutor <https://docs.tutor.overhang.io/>`__ Open edX distribution. The following installation instructions should work wit the `tutor-ecommerce plugin <https://github.com/overhangio/tutor-ecommerce>`__, but there is no reason to believe that it shouldn't also work with the Open edX native installation.

Make sure that the ecommerce plugin is enabled::

    tutor plugins enable ecommerce

Add the Saferpay payment processor to the Docker image::

    tutor config save \
        --set 'ECOMMERCE_EXTRA_PIP_REQUIREMENTS=["git+https://github.com/epfl-cede/openedx-saferpay"]'
    tutor images build ecommerce

Then configure your Ecommerce instance to use the Saferpay payment processor::

    tutor config save --set 'ECOMMERCE_ENABLED_PAYMENT_PROCESSORS=["saferpay"]'
    tutor config save --set 'ECOMMERCE_EXTRA_PAYMENT_PROCESSOR_CLASSES=["openedx_saferpay.processor.Saferpay"]'
    tutor config save --set 'ECOMMERCE_EXTRA_PAYMENT_PROCESSOR_URLS={"saferpay": "openedx_saferpay.urls"}'

Save your Saferpay credentials to saferpay.yml::

    $ cat saferpay.yml
    saferpay:
        # api_url: https://test.saferpay.com/api/ # optional
        api_username: API_ABC_DEF
        api_password: JsonApiPwdX_XXXX
        customer_id: 'ABC'
        terminal_id: 'GHI'
    $ tutor config save --set "ECOMMERCE_PAYMENT_PROCESSORS=$(cat saferpay.yml.yml)"

Run initialization scripts::

    tutor local quickstart

Enable the Saferpay payment backend::

    tutor local run ecommerce ./manage.py waffle_switch --create payment_processor_active_saferpay on

All payments will then proceed through the Saferpay payment processor.

License
=======

This work is licensed under the terms of the `GNU Affero General Public License (AGPL) <https://github.com/epfl-cede/openedx-saferpay/blob/master/LICENSE.txt>`_.