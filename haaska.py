#!/usr/bin/env python3.12
# coding: utf-8

# Copyright (c) 2015 Michael Auchter <a@phire.org>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import json
import logging
import requests
import boto3
from sshtunnel import SSHTunnelForwarder
from base64 import b64decode

logger = logging.getLogger()


class HomeAssistant(object):
    def __init__(self, config):
        self.config = config

        self.session = requests.Session()
        self.session.headers = {
            'Authorization': f'Bearer {config.bearer_token}',
            'content-type': 'application/json',
            'User-Agent': self.get_user_agent()
        }
        self.session.verify = config.ssl_verify
        self.session.cert = config.ssl_client

    def build_url(self, endpoint):
        return f'{self.config.url}/api/{endpoint}'

    def get_user_agent(self):
        library = "Home Assistant Alexa Smart Home Skill"
        aws_region = os.environ.get("AWS_DEFAULT_REGION")
        default_user_agent = requests.utils.default_user_agent()
        return f"{library} - {aws_region} - {default_user_agent}"

    def get(self, endpoint):
        r = self.session.get(self.build_url(endpoint))
        r.raise_for_status()
        return r.json()

    def post(self, endpoint, data, wait=False):
        read_timeout = None if wait else 0.01
        try:
            logger.debug(f'calling {endpoint} with {data}')
            r = self.session.post(self.build_url(endpoint),
                                  data=json.dumps(data),
                                  timeout=(None, read_timeout))
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ReadTimeout:
            # Allow response timeouts after request was sent
            logger.debug(
                f'request for {endpoint} sent without waiting for response')
            return None


class Configuration(object):
    def __init__(self, filename=None, opts_dict=None):
        self._json = {}
        if filename is not None:
            with open(filename) as f:
                self._json = json.load(f)

        if opts_dict is not None:
            self._json = opts_dict

        self.url = self.get_url(self.get(['url', 'ha_url']))
        self.ssl_verify = self.get(['ssl_verify', 'ha_cert'], default=True)
        self.bearer_token = self.get(['bearer_token'], default='')
        self.ssl_client = self.get(['ssl_client'], default='')
        self.debug = self.get(['debug'], default=False)
        self.ssh_enabled = self.get(['ssh_enabled'], default=False)
        if self.ssh_enabled:
            self.ssh_username = self.get(['ssh_username'], default='')
            self.ssh_remote_host_public_url = self.get(
                ['ssh_remote_host_public_url'], default='')
            self.ssh_remote_host_public_port = self.get(
                ['ssh_remote_host_public_port'], default=22)
            self.ssh_remote_host_private_url = self.get(
                ['ssh_remote_host_private_url'], default='0.0.0.0')
            self.ssh_remote_host_private_port = self.get(
                ['ssh_remote_host_private_port'], default=8123)
            self.ssh_local_host_port = self.get(
                ['ssh_local_host_port'], default=8123)
            self.ssh_key_is_encrypted = self.get(
                ['ssh_key_is_encrypted'], default=False)

    def get(self, keys, default=None):
        for key in keys:
            if key in self._json:
                return self._json[key]
        return default

    def get_url(self, url):
        """Returns Home Assistant base url without '/api' or trailing slash"""
        if not url:
            raise ValueError('Property "url" is missing in config')

        return url.replace("/api", "").rstrip("/")


DECRYPTED_SSH_KEY_PASS = ""


def get_decrypted_ssh_key_pass():
    global DECRYPTED_SSH_KEY_PASS
    if not DECRYPTED_SSH_KEY_PASS:
        password = os.environ['ssh_key_pass']
        DECRYPTED_SSH_KEY_PASS = boto3.client('kms').decrypt(
            CiphertextBlob=b64decode(password))['Plaintext']
    return DECRYPTED_SSH_KEY_PASS


def event_handler(event, context):
    config = Configuration('config.json')
    if config.debug:
        logger.setLevel(logging.DEBUG)

    if config.ssh_enabled:
        ssh_tunnel = SSHTunnelForwarder(
            (config.ssh_remote_host_public_url,
             config.ssh_remote_host_public_port),
            ssh_username=config.ssh_username,
            ssh_pkey="./ssh.key",
            ssh_private_key_password=(get_decrypted_ssh_key_pass()
                                      if config.ssh_key_is_encrypted
                                      else None),
            remote_bind_address=(config.ssh_remote_host_private_url,
                                 config.ssh_remote_host_private_port),
            local_bind_address=('0.0.0.0', config.ssh_local_host_port)
        )
        ssh_tunnel.start()

    ha = HomeAssistant(config)
    result = ha.post('alexa/smart_home', event, wait=True)

    if config.ssh_enabled:
        ssh_tunnel.stop()

    return result
