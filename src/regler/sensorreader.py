"""
sensorreader - Read sensordata and push to mqtt
Usage:
    sensorreader [-h | --help]
    sensorreader [options]

Options:
    -h --help           Show this screen.
    --log=<logfile>     Logfile [default: /var/log/house/sensorreader.log]
    --uri=<mqttclient>  MQTT broker URI [default: mqtt://localhost]
    --interval=<sec>    poll interval [default: 10]
    -v                  log level DEBUG
"""
import os
import time
import asyncio
import logging
import docopt
from datetime import datetime

# Force W1ThermSensor package to not load kernel modules
os.environ["W1THERMSENSOR_NO_KERNEL_MODULE"] = "1"
from w1thermsensor import W1ThermSensor, NoSensorFoundError  # noqa

from hbmqtt.client import MQTTClient, ClientException  # noqa
from hbmqtt.mqtt.constants import QOS_2  # noqa


BASE_TOPIC = "/house/heating"
SENSOR_BASE_TOPIC = BASE_TOPIC + '/sensors'


CLIENT_CONFIG = {
    "default_qos": QOS_2,
    "broker": {
        "cleansession": False  # don't miss data
    }
}

SENSORS = {
    "flow_temp": {
        "id": '0416c19d01ff',
        "topic": SENSOR_BASE_TOPIC + "/temp/flow",
        "min": -10.0,
        "max": 50.0,
    },
    "outside_air_temp": {
        "id": '03168514c9ff',
        "topic": SENSOR_BASE_TOPIC + "/temp/outside_air_temp",
        "min": -30.0,
        "max": 50.0,
    },
}


@asyncio.coroutine
def run(arguments):
    poll_interval = int(arguments['--interval'])
    # connect to the MQTT brocker
    C = MQTTClient(
        BASE_TOPIC + "/sensorreader",
        config=CLIENT_CONFIG,
    )
    yield from C.connect(arguments['--uri'])
    try:
        for sensor in W1ThermSensor.get_available_sensors():
            logging.debug("Sensor: %s", sensor.id)
        while True:
            start = time.time()
            for name, s in SENSORS.items():
                if 'sensor_client' not in s:
                    try:
                        s['sensor_client'] = W1ThermSensor(
                            W1ThermSensor.THERM_SENSOR_DS18B20,
                            s['id'],
                        )
                        logging.info('[%s] sonsor found' % name)
                    except NoSensorFoundError:
                        logging.error('[%s] sonsor not found' % name)
                        continue
                t = s['sensor_client'].get_temperature()
                if t < s['min'] or t > s['max']:
                    logging.warning("[%s] temp %s outside [%s - %s]" % (
                        name, t, s['min'], s['max']
                    ))
                    continue
                now = datetime.now().replace(microsecond=0)
                data = '{}Z,{}'.format(now.isoformat(), t)
                yield from C.publish(
                    s['topic'],
                    bytes(data, 'utf-8'),
                    qos=QOS_2,
                )
            end = time.time()
            time.sleep(max(0, poll_interval - (end - start)))
    except KeyboardInterrupt:
        pass
    except:
        logging.exception("")
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
