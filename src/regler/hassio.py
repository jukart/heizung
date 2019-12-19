"""
hassio - Transform MQTT house messages for hassio
Usage:
    hassio [-h | --help]
    hassio [options]

Options:
    -h --help           Show this screen.
    --uri=<mqttclient>  MQTT broker URI [default: mqtt://localhost]
"""
import asyncio
import docopt
import json

from hbmqtt.client import MQTTClient, ClientException
from hbmqtt.mqtt.constants import QOS_2


HOUSE_BASE_TOPIC = "/house/heating"

CLIENT_CONFIG = {
    "default_qos": QOS_2,
    "broker": {
        "cleansession": False  # don't miss data
    }
}


@asyncio.coroutine
def binarySensorHandler(settings, client, packet):
    [ts, state] = packet.payload.data.decode('utf-8').split(',', 1)
    state = 'OFF' if state == '0' else 'ON'
    yield from client.publish(
        settings['topicBase'] + 'state',
        bytes(state, 'utf-8'),
        qos=QOS_2,
    )


@asyncio.coroutine
def tempSensorHandler(settings, client, packet):
    [ts, value] = packet.payload.data.decode('utf-8').split(',', 1)
    yield from client.publish(
        settings['topicBase'] + 'state',
        bytes(value, 'utf-8'),
        qos=QOS_2,
    )


HANDLERS = {
    HOUSE_BASE_TOPIC + '/actors/heat_pump': {
        "active": True,
        "handler": binarySensorHandler,
        "topicBase": "homeassistant/binary_sensor/house/heat_pump/",
        "config": {
            "name": "Heizung Wärmepumpe",
            "unique_id": "house_sensor_heat_pump",
            "state_topic": "homeassistant/binary_sensor/house/heat_pump/state",
            "payload_available": "true",
            "payload_not_available": "false",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": {
                "manufacturer": "selbst",
                "model": "heizung",
                "name": "Heizung",
                "identifiers": [
                    "heizung1"
                ]
            }
        },
    },
    HOUSE_BASE_TOPIC + '/sensors/temp/outside_air_temp': {
        "active": True,
        "handler": tempSensorHandler,
        "topicBase": "homeassistant/sensor/house/outside_air_temp/",
        "config": {
            "name": "Heizung Aussentemperatur",
            "unique_id": "house_sensor_outside_air",
            "state_topic": "homeassistant/sensor/house/outside_air_temp/state",
            "value_template": "{{ value | float | round(1) }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "device": {
                "manufacturer": "selbst",
                "model": "heizung",
                "name": "Heizung",
                "identifiers": [
                    "heizung1"
                ]
            }
        },
    },
    HOUSE_BASE_TOPIC + '/sensors/temp/flow': {
        "active": True,
        "handler": tempSensorHandler,
        "topicBase": "homeassistant/sensor/house/flow/",
        "config": {
            "name": "Heizung Wassertemperatur",
            "unique_id": "house_sensor_flow",
            "state_topic": "homeassistant/sensor/house/flow/state",
            "value_template": "{{ value | float | round(1) }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "device": {
                "manufacturer": "selbst",
                "model": "heizung",
                "name": "Heizung",
                "identifiers": [
                    "heizung1"
                ]
            }
        },
    }
}

SUBSCRIPTIONS = [
    (name, QOS_2)
    for name, settings in HANDLERS.items()
    if settings['active']
]


@asyncio.coroutine
def publishConfig(client, settings):
    yield from client.publish(
        settings['topicBase'] + 'config',
        bytes(json.dumps(settings['config']), 'utf-8'),
        qos=QOS_2,
        retain=True,
    )


@asyncio.coroutine
def run(arguments):
    alive = True
    while alive:
        C = MQTTClient(
            "hassio/test",
            config=CLIENT_CONFIG,
        )
        yield from C.connect(arguments['--uri'])
        yield from C.subscribe(SUBSCRIPTIONS)
        for settings in HANDLERS.values():
            if settings['active']:
                yield from publishConfig(C, settings)
        try:
            while True:
                message = yield from C.deliver_message()
                packet = message.publish_packet
                topic = packet.topic_name
                if topic in HANDLERS:
                    settings = HANDLERS[topic]
                    yield from settings['handler'](settings, C, packet)
                    row = packet.payload.data.decode('utf-8').split(',', 1)
                    print(packet.topic_name, row)
        except KeyboardInterrupt:
            alive = False
        except ClientException as ce:
            print("Client exception: %s" % ce)
            yield from C.unsubscribe([s[0] for s in SUBSCRIPTIONS])
        finally:
            yield from C.disconnect()


if __name__ == '__main__':
    arguments = docopt.docopt(__doc__)
    asyncio.get_event_loop().run_until_complete(run(arguments))
