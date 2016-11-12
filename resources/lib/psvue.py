# -*- coding: utf-8 -*-
"""
A Kodi-agnostic library for PlayStation Vue
"""
import os
import json
import codecs
import cookielib
import time
import calendar
import uuid
import base64
from datetime import datetime, timedelta
from urllib import urlencode

import requests
import m3u8
import iso8601


class psvue(object):
    def __init__(self, save_path, debug=False, verify_ssl=True):
        self.save_path = save_path
        self.debug = debug
        self.app_version = '2_6_1'
        self.base_url = 'https://sonyios.secure.footprint.net/%s/pad/' % self.app_version
        self.verify_ssl = verify_ssl
        self.http_session = requests.Session()
        self.cookie_file = os.path.join(self.save_path, 'cookies')
        self.credentials_file = os.path.join(self.save_path, 'credentials')
        self.cookie_jar = cookielib.LWPCookieJar(self.cookie_file)
        try:
            self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except IOError:
            pass
        self.http_session.cookies = self.cookie_jar
        self.valid_session = self.is_session_valid()
        self.config = self.get_config()

    class LoginFailure(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def log(self, string):
        if self.debug:
            try:
                print '[psvue]: %s' % string
            except UnicodeEncodeError:
                # we can't anticipate everything in unicode they might throw at
                # us, but we can handle a simple BOM
                bom = unicode(codecs.BOM_UTF8, 'utf8')
                print '[psvue]: %s' % string.replace(bom, '')
            except:
                pass

    def make_request(self, url, method, payload=None, headers=None, return_req=False):
        """Make an HTTP request. Return the response."""
        self.log('Request URL: %s' % url)
        try:
            if method == 'get':
                req = self.http_session.get(url, params=payload, headers=headers, allow_redirects=False, verify=self.verify_ssl)
            elif method == 'put':
                req = self.http_session.put(url, params=payload, headers=headers, allow_redirects=False, verify=self.verify_ssl)
            else:  # post
                req = self.http_session.post(url, data=payload, headers=headers, allow_redirects=False, verify=self.verify_ssl)
            self.log('Response code: %s' % req.status_code)
            self.log('Response: %s' % req.content)
            self.log('Headers: %s' % req.headers)
            self.cookie_jar.save(ignore_discard=True, ignore_expires=False)
            if return_req:
                return req
            else:
                return req.content
        except requests.exceptions.ConnectionError as error:
            self.log('Connection Error: - %s' % error.message)
            raise
        except requests.exceptions.RequestException as error:
            self.log('Error: - %s' % error.value)
            raise

    def get_grant_code(self):
        """Try to save grant code needed for PS Vue authentication."""
        url = 'https://auth.api.sonyentertainmentnetwork.com/2.0/oauth/authorize'
        params = {
            'client_id': 'dee6a88d-c3be-4e17-aec5-1018514cee40',
            'redirect_uri': 'https://vue.playstation.com/watch/html/auth-redirect.html?requestId=mlbam',
            'response_type': 'code',
            'scope': 'psn:s2s',
            'prompt': 'none'
        }

        req = self.make_request(url, 'get', payload=params, return_req=True)
        try:
            self.save_credentials(code=req.headers['x-np-grant-code'])
            return True
        except KeyError:
            self.log('Unable to save grant code. Login attempt was most likely unsuccessful.')
            return False

    def login_to_account(self, username, password):
        """Blindly login to PlayStation Network."""
        url = 'https://auth.api.sonyentertainmentnetwork.com/login.do'
        payload = {
            'params': base64.b64encode('request_locale=en_US&request_theme=liquid&disableLinks=SENLink'),
            'j_username': username,
            'rememberSignIn': 'on',
            'j_password': password
        }

        self.make_request(url, 'post', payload=payload)

    def authenticate(self):
        """Attempt to authenticate to the PlayStation Vue API."""
        url = 'https://sentv-user-auth.totsuko.tv/sentv_user_auth/ws/web/oauth2/token'
        payload = {
            'device_type_id': 'ipad',
            'device_id': self.get_credentials()['device_id'],
            'code': self.get_credentials()['code'],
            'issuer_id': '4'
        }

        data = self.make_request(url, 'get', payload=payload)
        json_data = json.loads(data)
        if json_data['body']['status'] == 'AUTHENTICATED':
            self.save_credentials(expiry_date=json_data['body']['expiry_date'])
        else:
            error_message = json_data['header']['error']['message']
            raise self.LoginFailure(error_message)

    def login(self, username=None, password=None):
        """Complete login process for PlayStation Vue."""
        if username and password:
            self.login_to_account(username, password)
            if not self.get_grant_code():
                raise self.LoginFailure('Login failed.')
            else:
                try:
                    self.authenticate()
                except self.LoginFailure:
                    raise
        else:
            raise self.LoginFailure('No username and password supplied.')

    def is_session_valid(self):
        """Return whether the PS Vue session is valid."""
        utcnow = datetime.utcnow()
        expiry_date = self.parse_datetime(self.get_credentials()['expiry_date'])
        expiry_date = expiry_date.replace(tzinfo=None)

        if expiry_date > utcnow:
            return True
        else:
            return False

    def get_stream_url(self, airing_id):
        """Return the stream URL for a program."""
        stream_url = {}
        url = 'https://media-framework.totsuko.tv/media-framework/media/v2.1/stream/airing/%s' % airing_id
        stream_data = self.make_request(url, 'get')
        stream_dict = json.loads(stream_data)
        stream_url['manifest'] = stream_dict['body']['video']
        stream_url['bitrates'] = self.parse_m3u8_manifest(stream_url['manifest'])

        return stream_url

    def get_profiles(self):
        """Return a list of the PS Vue profiles."""
        profiles = []
        url = self.config['epgUserSessionBaseURL'] + 'profile/ids'
        profiles_data = self.make_request(url, 'get')
        profiles_dict = json.loads(profiles_data)['body']['profiles']

        for profile in profiles_dict:
            profiles.append(profile)

        return profiles

    def get_profile_names(self):
        """Return a list of the PS Vue profile names."""
        profile_names = []
        profiles = self.get_profiles()

        for profile in profiles:
            profile_names.append(profile['profile_name'])

        return profile_names

    def set_profile(self, profile_name):
        """Attempt to set the profile cookies.
           Save the returned profile data in a dict as it's required for some POST requests."""
        profiles = self.get_profiles()
        data = False
        for profile in profiles:
            if profile['profile_name'] == profile_name:
                url = self.config['epgUserSessionBaseURL'] + 'profile/%s' % profile['profile_id']
                data = self.make_request(url, 'get')
                break

        if data:
            json_data = json.loads(data)
            profile_data = {
                'profile_data': {
                    'favorites': json_data['body']['favorites']
                }
            }
            self.save_credentials(profile_data=profile_data)
            return True
        else:
            self.log('No profile name in response matched the provided profile name.')
            return False

    def get_categories(self):
        """Return all PS Vue categories."""
        categories = []
        url = self.base_url + 'menu.json'
        data = self.make_request(url, 'get')
        json_data = json.loads(data)['body']['sections']

        for section in json_data:
            for item in section['items']:
                if item['template_type'] == 'category':
                    categories.append(item)

        return categories

    def parse_category_sortings(self, uri, offset='0', size='999'):
        """Parse the available category sortings and return them in a dict."""
        category_sortings = []
        url = self.base_url + uri
        data = self.make_request(url, 'get')
        json_data = json.loads(data)['body']

        for item in json_data['expandable_grids']:
            if 'request_method' in item.keys():
                request_method = item['request_method'].lower()
            else:
                request_method = 'get'

            if 'sort' in json_data.keys():
                for value in json_data['sort']['values']:
                    title = value['value']
                    sort_option = value['key']
                    item_uri = item['url'].replace('<sort>', sort_option)
                    category_sorting = {
                        'title': title,
                        'uri': item_uri,
                        'request_method': request_method
                    }
                    category_sortings.append(category_sorting)
            else:
                title = item['title']
                item_uri = item['url'].replace('<sort>', item['default_sort_option'])
                category_sorting = {
                    'title': title,
                    'uri': item_uri,
                    'request_method': request_method
                }
                category_sortings.append(category_sorting)

        for sorting in category_sortings:
            sorting['uri'] = sorting['uri'].replace('<offset>', offset)
            sorting['uri'] = sorting['uri'].replace('<size>', size)

        return category_sortings

    def parse_channel_sortings(self, channel_id, type='channel', offset='0', size='999'):
        """Parse the available channel sortings and return them in a dict."""
        channel_sortings = []
        url = self.base_url + self.config['channel']
        data = self.make_request(url, 'get')
        json_data = json.loads(data)['body']

        for key in json_data.keys():
            try:
                channel_sorting = {
                    'title': json_data[key]['title'],
                    'uri': json_data[key]['url'].replace('<section>', json_data[key]['detail_section']),
                    'request_method': 'get'
                }
                channel_sortings.append(channel_sorting)
            except TypeError:
                for item in json_data[key]:
                    channel_sorting = {
                        'title': item['title'],
                        'uri': item['url'].replace('<section>', item['detail_section']),
                        'request_method': 'get'
                    }
                    channel_sortings.append(channel_sorting)

        for sorting in channel_sortings:
            sorting['uri'] = sorting['uri'].replace('<type>', type)
            sorting['uri'] = sorting['uri'].replace('<id>', channel_id)
            sorting['uri'] = sorting['uri'].replace('<offset>', offset)
            sorting['uri'] = sorting['uri'].replace('<size>', size)

        return channel_sortings

    def get_programs(self, request_method, uri=None, program_id=None, search_query=None, expiration_filter=None, offset='0', size='999'):
        """Retrieve the programs by providing an URI (from the parsed sortings)/program ID/search query."""
        if uri:
            url = self.config['epgContentBaseURL'] + uri
        elif program_id:
            url = self.config['epgContentBaseURL'] + 'details/items/program/%s/episodes/offset/%s/size/%s' % (program_id, offset, size)
            if expiration_filter:  # should be a string in ISO8601 format
                url = url + '/expiration_filter/%s' % expiration_filter
        elif search_query:
            url = self.config['epgContentBaseURL'] + 'search/items/%s/offset/%s/size/%s' % (search_query, offset, size)
        else:
            self.log('No URI/program ID/search query supplied.')
            url = None

        if request_method == 'post':
            # profile_data is required with all post requests
            payload = json.dumps(self.get_credentials()['profile_data'])
            headers = {'Content-Type': 'application/json'}
        else:
            payload = None
            headers = None

        if url:
            data = self.make_request(url, method=request_method, payload=payload, headers=headers)
            json_data = json.loads(data)
            programs = json_data['body']['items']
            for program in programs:
                if program_id:
                    program['detailed'] = True
                else:
                    program['detailed'] = False
            return programs
        else:
            return False

    def parse_m3u8_manifest(self, manifest_url):
        """Return the stream URL along with its bitrate."""
        streams = {}
        m3u8_manifest = self.make_request(manifest_url, 'get')
        m3u8_header = {'Cookie': 'reqPayload=' + self.get_cookie_by_name('reqPayload').value}
        m3u8_obj = m3u8.loads(m3u8_manifest)
        for playlist in m3u8_obj.playlists:
            bitrate = int(playlist.stream_info.bandwidth) / 1000
            if playlist.uri.startswith('http'):
                stream_url = playlist.uri
            else:
                stream_url = manifest_url[:manifest_url.rfind('/') + 1] + playlist.uri
            streams[str(bitrate)] = stream_url + '|' + urlencode(m3u8_header)

        return streams

    def get_cookie_by_name(self, name):
        for cookie in self.cookie_jar:
            if cookie.name == name:
                return cookie

    def get_credentials(self):
        """Get the credentials from file and return it in a dict."""
        try:
            with open(self.credentials_file, 'r') as fh_credentials:
                return json.loads(fh_credentials.read())
        except IOError:
            self.reset_credentials()
        with open(self.credentials_file, 'r') as fh_credentials:
            return json.loads(fh_credentials.read())

    def reset_credentials(self):
        """Reset the credentials file to default."""
        credentials = {}
        utcnow = datetime.utcnow()
        credentials['device_id'] = str(uuid.uuid4())
        credentials['code'] = None
        credentials['expiry_date'] = utcnow.isoformat()
        credentials['profile_data'] = None
        with open(self.credentials_file, 'w') as fh_credentials:
            fh_credentials.write(json.dumps(credentials))

    def save_credentials(self, device_id=None, code=None, expiry_date=None, profile_data=None):
        """Save credentials to file."""
        credentials = {}
        if not device_id:
            device_id = self.get_credentials()['device_id']
        if not code:
            code = self.get_credentials()['code']
        if not expiry_date:
            expiry_date = self.get_credentials()['expiry_date']
        if not profile_data:
            profile_data = self.get_credentials()['profile_data']

        credentials['device_id'] = device_id
        credentials['code'] = code
        credentials['expiry_date'] = expiry_date
        credentials['profile_data'] = profile_data

        with open(self.credentials_file, 'w') as fh_credentials:
            fh_credentials.write(json.dumps(credentials))

    def get_config(self):
        """Return the config in a dict. Re-download if the config version doesn't match self.app_version."""
        config_path = os.path.join(self.save_path, 'configuration.json')
        try:
            config = json.load(open(config_path))['body']
            config_version = int(str(config['versioning']['version']).replace('.', ''))
            version_to_use = int(str(self.app_version).replace('_', ''))
            if config_version != version_to_use:
                self.download_config()
                config = json.load(open(config_path))['body']
            return config
        except IOError:
            self.download_config()
            config = json.load(open(config_path))['body']
            return config

    def download_config(self):
        """Download the PS Vue iPad JSON configuration."""
        config_path = os.path.join(self.save_path, 'configuration.json')
        config_data = self.make_request(self.base_url + 'configuration.json', 'get')
        with open(config_path, 'w') as fh_config:
            fh_config.write(config_data)

    def utc_to_local(self, utc_dt):
        """Convert UTC datetime object to local time."""
        # get integer timestamp to avoid precision lost
        timestamp = calendar.timegm(utc_dt.timetuple())
        local_dt = datetime.fromtimestamp(timestamp)
        assert utc_dt.resolution >= timedelta(microseconds=1)
        return local_dt.replace(microsecond=utc_dt.microsecond)

    def parse_datetime(self, iso8601_string, localize=False):
        """Parse ISO8601 string to datetime object."""
        datetime_obj = iso8601.parse_date(iso8601_string)
        if localize:
            return self.utc_to_local(datetime_obj)
        else:
            return datetime_obj
