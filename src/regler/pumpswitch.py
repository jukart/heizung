"""
pumpswitch - Switch the pump on /off based on mqtt message
Usage:
    pumpswitch [-h | --help]
    pumpswitch [options]

Options:
    -h --help           Show this screen.
    --log=<logfile>     Logfile [default: /var/log/house/pumpswitch.log]
    --uri=<mqttclient>  MQTT broker URI [default: mqtt://localhost]
    -v                  log level DEBUG
"""
import asyncio
import logging
import docopt

from hbmqtt.client import MQTTClient, ClientException
from hbmqtt.mqtt.constants import QOS_2

import RPi.GPIO as GPIO


heatPumpPin = 19
waterPumpPin = 20

HEAT_PUMP_ON = GPIO.LOW
HEAT_PUMP_OFF = GPIO.HIGH
WATER_PUMP_ON = GPIO.HIGH
WATER_PUMP_OFF = GPIO.LOW

ON = True
OFF = False
UNKNOWN = None


BASE_TOPIC = "/house/heating"
ACTOR_BASE_TOPIC = BASE_TOPIC + '/actors'


CLIENT_CONFIG = {
    "default_qos": QOS_2,
    "broker": {
        "cleansession": False
    }
}

SUBSCRIPTIONS = [
    (ACTOR_BASE_TOPIC + "/heat_pump", QOS_2),
    (ACTOR_BASE_TOPIC + "/water_pump", QOS_2),
]


def pinStateFromMQTTState(state):
    if state == '0':
        return OFF
    if state == '1':
        return ON
    return UNKNOWN


@asyncio.coroutine
def run(arguments):
    retry = True
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(heatPumpPin, GPIO.OUT)
    GPIO.setup(waterPumpPin, GPIO.OUT)
    GPIO.output(heatPumpPin, HEAT_PUMP_OFF)
    GPIO.output(waterPumpPin, WATER_PUMP_ON)
    while retry:
        C = MQTTClient(
            BASE_TOPIC + "/pumpswitch",
            config=CLIENT_CONFIG,
        )
        yield from C.connect(arguments['--uri'])
        yield from C.subscribe(SUBSCRIPTIONS)
        try:
            while True:
                message = yield from C.deliver_message()
                packet = message.publish_packet
                topic = packet.variable_header.topic_name
                state = packet.payload.data.decode('utf-8').split(',')[-1]
                state = pinStateFromMQTTState(state)
                if state == UNKNOWN:
                    continue
                if topic.endswith('heat_pump'):
                    if state == ON:
                        GPIO.output(heatPumpPin, HEAT_PUMP_ON)
                    else:
                        GPIO.output(heatPumpPin, HEAT_PUMP_OFF)
                    if state == ON:
                        GPIO.output(waterPumpPin, WATER_PUMP_ON)
                elif topic.endswith('water_pump'):
                    if state == ON:
                        GPIO.output(heatPumpPin, WATER_PUMP_ON)
                    else:
                        GPIO.output(heatPumpPin, WATER_PUMP_OFF)
        except KeyboardInterrupt:
            retry = False
        except ClientException as e:
            logging.error("Client exception: %s" % e)
        except:
            yield from C.unsubscribe(SUBSCRIPTIONS)
        finally:
            yield from C.disconnect()

if __name__ == '__main__':
    arguments = docopt.docopt(__doc__)
    level = logging.INFO
    if arguments['-v']:
        level = logging.DEBUG
    logging.basicConfig(
        filename=arguments['--log'],
        format='%(asctime)s:%(message)s',
        level=level,
    )
    asyncio.get_event_loop().run_until_complete(run(arguments))
