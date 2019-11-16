"""
regler - Heizungsregler
Usage:
    regler [-h | --help]
    regler [options]

Options:
    -h --help        Show this screen.
    --uri=CLIENT     MQTT broker URI [default: mqtt://localhost]
    --settings=FILE  Settings file in JSON format
                     [default: /etc/house/settings.json]
    --log=FILE       Logfile [default: /var/log/house/regler.log]
    -v               log level DEBUG
    --loop-time=INT  calculation loop time [default: 30]
"""
import copy
import time
import json
from datetime import datetime
import asyncio
import docopt
import logging

from hbmqtt.client import MQTTClient, ClientException  # noqa
from hbmqtt.mqtt.constants import QOS_2  # noqa

BASE_TOPIC = "/house/heating"
SENSOR_BASE_TOPIC = BASE_TOPIC + '/sensors'
ACTOR_BASE_TOPIC = BASE_TOPIC + '/actors'
STATE_BASE_TOPIC = BASE_TOPIC + '/state'

PUMP_ON = 1
PUMP_OFF = 0


CLIENT_CONFIG = {
    "default_qos": QOS_2,
    "broker": {
        "cleansession": True
    }
}


state = {
    "settings": {
        "a": -0.2,
        "b": 28,
        "tolerance": 1.0,
        "mode": "auto",
        "modified": datetime.now().isoformat()
    },
    "nominal": None,
    "heat_pump": PUMP_OFF,
    "heat_pump_ts": int(time.time()),
    "alarm": False,
    "alarm_code": -1,
}


class Value(object):

    def __init__(self, topic, value):
        self.topic = topic
        self.setValue(value)

    def setValue(self, value):
        self.value = value
        self.ts = datetime.now().replace(microsecond=0)


class PushValue(Value):

    def publish(self):
        return (
            self.topic,
            bytes('{}Z,{}'.format(self.ts.isoformat(), self.value), 'utf-8'),
        )


class JSONPushValue(Value):

    def publish(self):
        return (
            self.topic,
            bytes('{}Z,{}'.format(
                    self.ts.isoformat(),
                    json.dumps(self.value)
                ), 'utf-8'),
        )


sensors = {
    "flow": Value(
        SENSOR_BASE_TOPIC + "/temp/flow",
        None),
    "outside_air_temp": Value(
        SENSOR_BASE_TOPIC + "/temp/outside_air_temp",
        None),
}
push_state = {
    'heat_pump': PushValue(
        ACTOR_BASE_TOPIC + "/heat_pump",
        state['heat_pump']),
    "state": JSONPushValue(
        STATE_BASE_TOPIC + "/state",
        state),
}


@asyncio.coroutine
def run(arguments):
    global SUBSCRIPTIONS
    readSettings()
    loop_time = int(arguments['--loop-time'])
    retry = True
    while retry:
        C = MQTTClient(
            BASE_TOPIC + "/regler",
            config=CLIENT_CONFIG,
        )
        yield from C.connect(arguments['--uri'])
        yield from C.subscribe([(s[0], QOS_2) for s in SUBSCRIPTIONS])
        C1 = MQTTClient(
            BASE_TOPIC + "/regler1",
            config=CLIENT_CONFIG,
        )
        yield from C1.connect(arguments['--uri'])
        try:
            push_state['heat_pump'].setValue(state['heat_pump'])
            yield from C.publish(*push_state['heat_pump'].publish())
            yield from C.publish(*push_state['state'].publish())
            start = time.time()
            while True:
                packet = None
                wait_time = max(loop_time - (time.time() - start), 0)
                logging.debug("wait_time= %s", wait_time)
                try:
                    message = yield from C.deliver_message(timeout=wait_time)
                    packet = message.publish_packet
                except asyncio.TimeoutError:
                    pass
                if packet:
                    executePacket(packet)
                if (time.time() - start) > loop_time:
                    start = time.time()
                    calculateNominal()
                    calulateHeatPumpState()
                    push_state['heat_pump'].setValue(state['heat_pump'])
                    yield from C.publish(*push_state['heat_pump'].publish())
                    yield from C.publish(*push_state['state'].publish())
        except KeyboardInterrupt:
            retry = False
        except ClientException as e:
            logging.exception("Client exception: %s" % e)
        except Exception as e:
            logging.exception("Unknown exception: %s" % e)
        finally:
            yield from C.unsubscribe([s[0] for s in SUBSCRIPTIONS])
            yield from C.disconnect()
        if retry:
            print("retry")


def pushData(C):
    global push_state, state
    push_state['heat_pump'].setValue(state['heat_pump'])
    yield from C.publish(*push_state['heat_pump'].publish())
    yield from C.publish(*push_state['state'].publish())


no_calc = False


def calculateNominal():
    global no_calc, state, sensors
    outside_air_temp = sensors['outside_air_temp']
    oat = outside_air_temp.value
    if oat is None:
        print('no oat')
        if not no_calc:
            logging.error('No outside air temperature')
            no_calc = True
        return False
    no_calc = False
    settings = state['settings']
    a = float(settings['a'])
    b = float(settings['b'])
    n = a * oat + b
    state['nominal'] = n
    return True


def calulateHeatPumpState():
    global state, sensors
    oat = sensors['outside_air_temp'].value
    current = sensors['flow'].value
    tolerance = float(state['settings']['tolerance'])
    nominal = state['nominal']
    pump = state['heat_pump']
    old_pump = pump
    pump_ts = state['heat_pump_ts']
    if nominal is None or current is None or oat is None:
        # no valid values
        pump = PUMP_OFF
    elif oat > 18.0:
        # never heat above this outside temp
        pump = PUMP_OFF
    elif pump == PUMP_ON and current > (nominal + tolerance):
        pump = PUMP_OFF
    elif pump == PUMP_OFF and current < (nominal - tolerance):
        pump = PUMP_ON
    now = time.time()
    if old_pump != pump and (pump_ts is None or (now - pump_ts) > 60):
        state['heat_pump'] = pump
        state['heat_pump_ts'] = int(now)


def executePacket(packet):
    global SUBSCRIPTIONS
    topic = packet.variable_header.topic_name
    for t, f in SUBSCRIPTIONS:
        if topic.startswith(t.strip('#')):
            data = packet.payload.data.decode('utf-8')
            f(topic, data)
            break


def updateTemp(topic, data):
    global sensors
    sensorName = topic.rsplit('/', 1)[-1]
    if sensorName in sensors:
        data = data.split(',')
        sensors[sensorName].setValue(float(data[-1]))


def updateSettings(topic, data):
    global state
    settingName = topic.rsplit('/', 1)[-1]
    state['settings'][settingName] = data
    storeSettings()


def executeCommand(topic, data):
    pass


SUBSCRIPTIONS = [
    ('/house/heating/sensors/temp/#', updateTemp),
    ('/house/heating/settings/#', updateSettings),
    ('/house/heating/command/#', executeCommand),
]


old_settings = copy.deepcopy(state['settings'])


def storeSettings():
    global old_settings, state, arguments
    settings = state['settings']
    if old_settings != settings:
        settings["modified"] = datetime.now().isoformat()
        old_settings = copy.deepcopy(settings)
        with open(arguments['--settings'], 'a') as s:
            s.write(json.dumps(settings))
            s.write('\n')


def readSettings():
    global old_settings, state, arguments
    lastLine = None
    with open(arguments['--settings'], 'r') as s:
        while True:
            line = s.readline()
            if not line:
                break
            if not line.startswith('#'):
                lastLine = line.strip()
    if lastLine:
        s = json.loads(lastLine)
        state['settings'] = s
        old_settings = copy.deepcopy(state['settings'])
    logging.info('readSettings: %s', state['settings'])

arguments = None

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
