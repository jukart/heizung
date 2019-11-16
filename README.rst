How to Read Settings
====================

Watch everything::

    $ mosquitto_sub -t /house/#

Watch settings::

    $ mosquitto_sub -t /house/heating/state/#


How to Change Settings
======================

Test::

    $ mosquitto_pub -t /house/heating/settings/test -m 2

a*x + b::

    $ mosquitto_pub -t /house/heating/settings/a -m ...
    $ mosquitto_pub -t /house/heating/settings/b -m ...

