# -*- coding: utf-8 -*-
import hashlib
import json
import time
from builtins import KeyboardInterrupt

import requests
from confluent_kafka.avro import AvroConsumer, SerializerError, CachedSchemaRegistryClient
from confluent_kafka.avro.serializer.message_serializer import MessageSerializer
from confluent_kafka.cimpl import KafkaError

from config import cfg
from logger import log

s = requests.Session()


def generate_token_from(url_without_token, secret_key):
    str_content = (url_without_token + secret_key).encode()
    digest = hashlib.md5(str_content).hexdigest()
    return digest[:20]


def send_to_nacta_platform(msgs):
    log.info('send_to_nacta_platform')
    records = []
    for msg in msgs:
        periods = json.loads(msg.get('periods')).get('periods')
        slot_period_start = periods[int(msg.get('slot_of_day')) - 1].get('start') if len(periods) >= int(
            msg.get('slot_of_day')) else None
        if msg.get('date') and msg.get('uid') and slot_period_start and msg.get('course_code') and msg.get(
                'attendance_time') and msg.get("channel"):
            records.append(
                {
                    'username': msg.get('user_name'),
                    'timestamp': '{}T{}+08:00'.format(
                        msg.get('access_at'),
                        slot_period_start),
                    'building': msg.get('building_name'),
                    'room': msg.get('room_name'),
                    'action': msg.get('access') == 'ALLOWED' if 'OPEN' else 'DENY',
                    'direction': 'in',
                    'evidence_type': msg.get("access_way"),
                    'evidence_id': msg.get('card_no')
                }
            )
        else:
            log.debug("remove invalid data, msg: {}".format(msg))

    log.info(records)
    log.info("deal msgs size is : {}".format(len(records)))

    if len(records) < len(msgs):
        log.warning('Fields should not be NULL, please check vw_door_lock_record')
    if len(records) == 0:
        return True

    timestamp = int(time.time())
    url_partial = '{}?app_key={}&ts={}'.format(cfg['common']['nacta_api_url'], cfg['common']['app_key'],
                                               timestamp)
    token = generate_token_from(url_partial, cfg['common']['secret_key'])
    target_url = 'http://{}{}&token={}'.format(cfg['common']['nacta_api_host'], url_partial, token)

    try:
        response = s.post(target_url, json={'records': records}, timeout=30)
    except requests.RequestException as e:
        log.error(e)
        return False
    except requests.ConnectTimeout as e:
        log.error(e)
        return False
    if response.status_code != 201:
        log.error('{}, {}'.format(response.status_code, response.text))
        return False
    log.info('{}, {}'.format(response.status_code, response.json().get('message')))
    return True


consumer = AvroConsumer({
    'bootstrap.servers': cfg['kafka']['bootstrap_servers'],
    'group.id': cfg['kafka']['group_id'],
    'schema.registry.url': cfg['kafka']['schema_registry_url'],
    'default.topic.config': {'auto.offset.reset': 'smallest'},
    'enable.auto.commit': False
})


def run_consumer():
    log.info('consumer started')

    consumer.subscribe([cfg['kafka']['topics']])
    running = True
    schema_registry = CachedSchemaRegistryClient(url=cfg['kafka']['schema_registry_url'])
    _serializer = MessageSerializer(schema_registry)
    while running:
        try:
            msg = consumer.consume(num_messages=50, timeout=1)
            if msg:
                msg_list = []
                for m in msg:
                    if m.error():
                        if m.error().code() != KafkaError._PARTITION_EOF:
                            log.error(m.error())
                            continue
                    else:
                        log.debug(m.value())
                        msg_list.append(_serializer.decode_message(m.value()))

                log.info("msgs size is {}".format(len(msg_list)))
                if send_to_nacta_platform(msg_list):
                    consumer.commit(asynchronous=True)
                    log.info("deal with msgs end")

        except SerializerError as e:
            log.error('Message deserialization failed: {}'.format(e))
            running = False
        except KeyboardInterrupt:
            print('Aborted by user')
            running = False

    consumer.close()
    log.info('consumer closed')


if __name__ == '__main__':
    run_consumer()
