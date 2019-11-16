"""
display - Show Information
Usage:
    display [-h | --help]
    display [options]

Options:
    -h --help           Show this screen.
    --uri=<mqttclient>  MQTT broker URI [default: localhost]
"""
import os
import time
import json
import docopt
try:
    import Queue as queue
except Exception:
    import queue

import pygame

import paho.mqtt.client as mqtt


# Colours
WHITE = (255, 255, 255)
RED = (255, 0, 0)

os.putenv('SDL_FBDEV', '/dev/fb1')

BASE_TOPIC = "/house/heating"
BASE_TEMP_TOPIC = BASE_TOPIC + "/sensors/temp"
BASE_STATE_TOPIC = BASE_TOPIC + "/state"


def on_connect(client, userdata, flags, rc):
    userdata.put(('connected', True))
    client.subscribe(BASE_TEMP_TOPIC + '/#', qos=2)
    client.subscribe(BASE_STATE_TOPIC + '/#', qos=2)


def on_disconnect(client, userdata, rc):
    userdata.put(('connected', False))


def on_flow_temp(client, userdata, msg):
    temp = msg.payload.decode('utf-8').rsplit(',', 1)[-1]
    userdata.put(('flow', float(temp)))


def on_air_temp(client, userdata, msg):
    temp = msg.payload.decode('utf-8').rsplit(',', 1)[-1]
    userdata.put(('air', float(temp)))


def on_state(client, userdata, msg):
    state = msg.payload.decode('utf-8').split(',', 1)[-1]
    state = json.loads(state)
    userdata.put(('state', state))


QUEUE = queue.Queue()

VALUES = {
    "connected": False,
}

TS = {
}


def run(arguments):
    global VALUES, QUEUE

    pygame.init()
    pygame.mouse.set_visible(False)
    lcd = pygame.display.set_mode((320, 240))
    lcd.fill((0, 0, 0))
    pygame.display.update()
    font_big = pygame.font.Font(None, 60)
    font_half = pygame.font.Font(None, 30)

    client = mqtt.Client(userdata=QUEUE)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.message_callback_add(
        BASE_TEMP_TOPIC + '/flow',
        on_flow_temp)
    client.message_callback_add(
        BASE_TEMP_TOPIC + '/outside_air_temp',
        on_air_temp)
    client.message_callback_add(
        BASE_TOPIC + '/state/state',
        on_state)
    client.connect_async(arguments['--uri'])
    client.loop_start()

    try:
        right = font_half.size('-99.9')[0] + 3
        colOffsets = [
            0,
            -(320 - right),
            -320,
        ]
        lineHeight = font_big.size('L')[1] + 1
        while True:
            name = None
            try:
                name, value = QUEUE.get(timeout=0.3)
            except queue.Empty:
                pass
            ev = pygame.event.poll()
            if ev.type == pygame.QUIT:
                break
            if name is not None:
                VALUES[name] = value
                TS[name] = time.time()

            lcd.fill((0, 0, 0))

            textColor = WHITE
            if not VALUES.get('connected', False):
                textColor = RED

            def drawCol(line, col, text, font=font_big, lineOffset=0):
                text_surface = font.render(text, True, textColor)
                size = font.size(text)
                pos = [colOffsets[col], line * lineHeight]
                if pos[0] < 0:
                    pos[0] = -pos[0] - size[0]
                pos[1] += size[1] * lineOffset
                lcd.blit(text_surface, pygame.Rect(pos, size))

            def showLine(line, text, value=None, up=None, down=None, ts=None):
                drawCol(line, 0, text)
                if value is not None:
                    drawCol(line, 1, value)
                if up is not None:
                    drawCol(line, 2, up, font_half)
                if down is not None:
                    drawCol(line, 2, down, font_half, 1)
                if ts is not None:
                    length = int((time.time() - ts) * 10)
                    if length <= 320:
                        pygame.draw.rect(
                            lcd,
                            (0, 255, 0),
                            pygame.Rect(
                                0, (line + 1) * lineHeight - 5,
                                length, 3)
                        )

            state = VALUES.get('state', {})
            settings = state.get('settings', {})
            nominal = float(state.get('nominal', 0.0))
            tolerance = float(settings.get('tolerance', 0.0))
            nominal_min = nominal - tolerance
            nominal_max = nominal + tolerance
            a = float(settings.get('a', 0.0))
            b = float(settings.get('b', 0.0))

            showLine(0,
                     'Luft',
                     '%.1f' % VALUES.get('air', 0.0),
                     ts=TS.get('air'))
            showLine(1,
                     'Soll',
                     value='%.1f' % nominal,
                     up='%.1f' % nominal_max,
                     down='%.1f' % nominal_min,
                     ts=TS.get('state'))
            showLine(2,
                     'Ist',
                     '%.1f' % VALUES.get('flow', 0.0),
                     ts=TS.get('flow'))
            text = '-'
            pump_state = state.get('heat_pump')
            if pump_state == 1:
                text = 'EIN'
            elif pump_state == 0:
                text = 'AUS'
            showLine(3, 'Pumpe', text, ts=TS.get('state'))
            drawCol(4, 2, '%.2f*t + %.2f' % (a, b), font_half, 1)

            pygame.display.update()
    finally:
        client.loop_stop()
        pygame.quit()

if __name__ == '__main__':
    arguments = docopt.docopt(__doc__)
    run(arguments)
