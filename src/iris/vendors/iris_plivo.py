# Copyright (c) LinkedIn Corporation. All rights reserved. Licensed under the BSD-2 Clause license.
# See LICENSE in the project root for license information.
# plivo added
from iris.constants import PLIVO_CALL_SUPPORT
from iris.plugins import find_plugin
from iris.custom_import import import_custom_module
import plivo
from iris import db
from sqlalchemy.exc import IntegrityError
import time
import urllib.parse
import logging

logger = logging.getLogger(__name__)


class iris_plivo(object):
    supports = frozenset([PLIVO_CALL_SUPPORT])
    message_id = 0

    def __init__(self, config):
        self.config = config
        self.modes = {
            PLIVO_CALL_SUPPORT: self.send_call,
        }
        self.timeout = config.get('timeout', 10)
        self.gather_endpoint = config.get('gather_endpoint', '/api/v0/plivo/calls/gather')
        push_config = config.get('push_notification', {})
        self.push_active = push_config.get('activated', False)
        if self.push_active:
            self.notifier = import_custom_module('iris.push', push_config['type'])(push_config)

    def get_plivo_client(self):
        return plivo.RestClient(self.config['account_sid'],
                                self.config['auth_token']
                                )

    def generate_message_text(self, message):
        content = []

        for key in ('subject', 'body'):
            value = message.get(key)
            if not isinstance(value, string):
                continue
            value = value.strip()
            if value:
                content.append(value)

        return '. '.join(content)

    def send_call(self, message):
        plugin = find_plugin(message['application'])
        if not plugin:
            raise ValueError('not supported source: %(application)s' % message)

        client = self.get_plivo_client()
        sender = client.calls.create
        if message['application'] in self.config.get('application_override_mapping', {}):
            from_ = self.config['application_override_mapping'][message['application']]
        else:
            from_ = self.config['plivo_number']
        status_callback_url = self.config['relay_base_url'] + '/api/v0/plivo/status'
        content = self.generate_message_text(message)

        payload = {
            'content': content[:480],
            'source': message['application'],
        }

        # If message_id is None or 0, go through says as iris can't handle
        # phone call response without the id
	message_id = message.get('message_id')
        if message_id:
            payload['message_id'] = message_id
            payload['instruction'] = plugin.get_phone_menu_text()
            relay_cb_url = '%s%s?%s' % (
                self.config['relay_base_url'], self.gather_endpoint, urllib.parse.urlencode({k: unicode(v).encode('utf-8') for k, v in payload.iteritems()})
            )
        else:
            relay_cb_url = '%s%s?%s' % (
                self.config['relay_base_url'], self.say_endpoint, urllib.parse.urlencode({k: unicode(v).encode('utf-8') for k, v in payload.iteritems()})
            )

        start = time.time()

        result = sender(to_=message['destination'],
                        from_=from_,
                        answer_url=relay_cb_url,
                        status_callback=status_callback_url)

        send_time = time.time() - start

        try:
            sid = result.sid
        except Exception:
            logger.exception('Failed getting Message SID from Plivo')
            sid = None

        if sid and message_id:
            self.initialize_plivo_message_status(sid, message_id)
        else:
            logger.warning('Not initializing plivo call status row (mid: %s, sid: %s)', message_id, sid)
        
        return send_time

    def send(self, message, customizations=None):
        if self.push_active:
            self.notifier.send_push(message)
        return self.modes[message['mode']](message)
