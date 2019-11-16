"""
mqttlogger - Log MQTT messages
Usage:
    mqttlogger [-h | --help]
    mqttlogger [options]

Options:
    -h --help           Show this screen.
    --uri=<mqttclient>  MQTT broker URI [default: mqtt://localhost]
    --output=FILE       Logfile [default: /var/log/house/mqtt.log]
    --log=FILE          Logfile [default: /var/log/house/mqttlogger.log]
    -v                  log level DEBUG
"""
import csv
import asyncio
import logging
import docopt

from hbmqtt.client import MQTTClient, ClientException
from hbmqtt.mqtt.constants import QOS_2


BASE_TOPIC = "/house/heating"


CLIENT_CONFIG = {
    "default_qos": QOS_2,
    "broker": {
        "cleansession": False  # don't miss data
    }
}

SUBSCRIPTIONS = [
    (BASE_TOPIC + '/#', QOS_2),
]


@asyncio.coroutine
def run(arguments):
    with open(arguments['--output'], 'a') as outfile:
        retry = True
        writer = csv.writer(outfile)
        while retry:
            C = MQTTClient(
                BASE_TOPIC + "/mqttlogger",
                config=CLIENT_CONFIG,
            )
            yield from C.connect(arguments['--uri'])
            yield from C.subscribe(SUBSCRIPTIONS)
            try:
                while True:
                    message = yield from C.deliver_message()
                    packet = message.publish_packet
                    row = packet.payload.data.decode('utf-8').split(',', 1)
                    row.append(packet.variable_header.topic_name)
                    writer.writerow(row)
                    outfile.flush()
            except KeyboardInterrupt:
                retry = False
            except ClientException as ce:
                logging.error("Client exception: %s" % ce)
                yield from C.unsubscribe([s[0] for s in SUBSCRIPTIONS])
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
