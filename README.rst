pretix-googlepaypasses
======================

.. image:: https://img.shields.io/pypi/v/pretix-googlepaypasses.svg
   :target: https://pypi.python.org/pypi/pretix-googlepaypasses

This is a plugin for `pretix`_. It allows to provide tickets in the Walletobjects-format, that can be added to Google
Pay.

This is a work in progress and quite possibly not working yet.

Contributing
------------

If you like to contribute to this project, you are very welcome to do so. If you have any
questions in the process, please do not hesitate to ask us.

Development setup
^^^^^^^^^^^^^^^^^

1. Make sure that you have a working `pretix development setup`_.

2. Clone this repository, eg to ``local/pretix-googlepaypasses``.

3. Activate the virtual environment you use for pretix development.

4. Execute ``python setup.py develop`` within this directory to register this application with pretix's plugin registry.

5. Execute ``make`` within this directory to compile translations.

6. Restart your local pretix server. You can now use the plugin from this repository for your events by enabling it in
   the 'plugins' tab in the settings.


Issuer ID / Google Pay API for Passes Merchant ID
-------------------------------------------------

As of now, the access to the Google Pay Passes API is invite only. In order to receive an Issuer ID, you will need to 
request access. This can be done by filling the form provided on the `Google Pay API for passes developer page`_.


License
-------

Copyright 2018 Martin Gross

Based on the `pretix-passbook plugin`_ by Tobias 'rixx' Kunze and Raphael Michel

Released under the terms of the Apache License 2.0


.. _pretix: https://github.com/pretix/pretix
.. _pretix-passbook plugin: https://github.com/pretix/pretix-passbook
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html
.. _Google Pay API for passes developer page: https://developers.google.com/pay/passes/
