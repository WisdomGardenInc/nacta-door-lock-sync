# -*- coding: utf-8 -*-
import time
import json
from builtins import KeyboardInterrupt

import requests
from confluent_kafka.avro import AvroConsumer, SerializerError, CachedSchemaRegistryClient
from confluent_kafka.avro.serializer.message_serializer import MessageSerializer
from confluent_kafka.cimpl import KafkaError

from config import cfg
from logger import log

s = requests.Session()
token_info = {}
auth_url = cfg['common']['nacta_api_host'] + cfg['common']['nacta_auth_url'] + \
           '?grant_type=client_credentials&scope=door_event'


def get_token():
    # 这里的授权头是base64(clientid:clientsecret)组成的
    current_timestamp = int(time.time())
    if 'access_token' in token_info.keys() and int(token_info.get('expired_time')) >= int(current_timestamp):
        return token_info.get('access_token')
    try:
        s.headers = {
            'Authorization': cfg['common']['authorization_header']
        }
        response = s.post(auth_url).content.decode()
        token_result = json.loads(response)
        token_info['access_token'] = token_result['token_type'] + ' ' + token_result['access_token']
        token_info['expired_time'] = int(token_result['expires_in']) + current_timestamp - 100
        return token_info.get('access_token')
    except requests.RequestException as e:
        log.error(e)
        return ''
    except requests.ConnectTimeout as e:
        log.error(e)
        return ''


def send_to_nacta_platform(msgs):
    log.info('send_to_nacta_platform')
    body = {}
    for msg in msgs:
        if msg.get('access_at') and msg.get('building_name') and msg.get('room_name') and msg.get('action'):
            body = {
                'username': msg.get('user_name'),
                'timestamp': msg.get('access_at'),
                'building': msg.get('building_name'),
                'room': msg.get('room_name'),
                'action': msg.get('access') == 'ALLOWED' if 'OPEN' else 'DENY',
                'direction': 'in',
                'evidence_type': msg.get("access_way"),
                'evidence_id': msg.get('card_no')
            }
        else:
            log.debug("remove invalid data, msg: {}".format(msg))

        log.info(body)

        target_url = '{}{}'.format(cfg['common']['nacta_api_host'], cfg['common']['nacta_sync_url'])

        try:
            token = get_token()
            s.headers = {'Authorization': token}
            response = s.post(target_url, json.dumps(body), timeout=30)
        except requests.RequestException as e:
            log.error(e)
        except requests.ConnectTimeout as e:
            log.error(e)
        if response.status_code != 201:
            log.error('{}, {}'.format(response.status_code, response.text))
        log.info('{}, {}'.format(response.status_code, response.json().get('message')))


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
