# -*- coding: utf-8 -*-
"""
A Kodi add-on for PlayStation Vue
"""
import sys
import os
import urllib
import urlparse
import json
from datetime import datetime

from resources.lib.psvue import psvue

import xbmc
import xbmcaddon
import xbmcvfs
import xbmcgui
import xbmcplugin

addon = xbmcaddon.Addon()
addon_path = xbmc.translatePath(addon.getAddonInfo('path'))
addon_profile = xbmc.translatePath(addon.getAddonInfo('profile'))
language = addon.getLocalizedString
logging_prefix = '[%s-%s]' % (addon.getAddonInfo('id'), addon.getAddonInfo('version'))

if not xbmcvfs.exists(addon_profile):
    xbmcvfs.mkdir(addon_profile)

_url = sys.argv[0]  # get the plugin url in plugin:// notation
_handle = int(sys.argv[1])  # get the plugin handle as an integer number

username = addon.getSetting('email')
password = addon.getSetting('password')
profile = addon.getSetting('profile_name')
if addon.getSetting('verify_ssl') == 'false':
    verify_ssl = False
else:
    verify_ssl = True

debug_cmd = {  # determine if debug logging is activated in kodi
               'jsonrpc': '2.0',
               'method': 'Settings.GetSettingValue',
               'params': {'setting': 'debug.showloginfo'},
               'id': '1'
               }
debug_dict = json.loads(xbmc.executeJSONRPC(json.dumps(debug_cmd)))
debug = debug_dict['result']['value']

vue = psvue(addon_profile, debug, verify_ssl)


def addon_log(string):
    if debug:
        msg = '%s: %s' % (logging_prefix, string)
        xbmc.log(msg=msg, level=xbmc.LOGDEBUG)


def get_user_input(heading):
    keyboard = xbmc.Keyboard('', heading)
    keyboard.doModal()
    if keyboard.isConfirmed():
        user_input = keyboard.getText()
        addon_log('User input string: %s' % user_input)
    else:
        user_input = None

    if user_input and len(user_input) > 0:
        return user_input
    else:
        return None


def get_numeric_input(heading):
    dialog = xbmcgui.Dialog()
    numeric_input = dialog.numeric(0, heading)

    if len(numeric_input) > 0:
        return str(numeric_input)
    else:
        return None


def ask_bitrate(bitrates):
    """Presents a dialog for user to select from a list of bitrates.
    Returns the value of the selected bitrate."""
    options = []
    for bitrate in bitrates:
        options.append(bitrate + ' Kbps')
    selected_bitrate = dialog('select', language(30010), options=options)
    if selected_bitrate is not None:
        return bitrates[selected_bitrate]
    else:
        return None


def select_bitrate(manifest_bitrates=None):
    """Returns a bitrate while honoring the user's preference."""
    bitrate_setting = int(addon.getSetting('preferred_bitrate'))
    if bitrate_setting == 0:
        preferred_bitrate = 'highest'
    elif bitrate_setting == 1:
        preferred_bitrate = 'limit'
    else:
        preferred_bitrate = 'ask'

    manifest_bitrates.sort(key=int, reverse=True)
    if preferred_bitrate == 'highest':
        return manifest_bitrates[0]
    elif preferred_bitrate == 'limit':
        allowed_bitrates = []
        max_bitrate_allowed = int(addon.getSetting('max_bitrate_allowed'))
        for bitrate in manifest_bitrates:
            if max_bitrate_allowed >= int(bitrate):
                allowed_bitrates.append(str(bitrate))
        if allowed_bitrates:
            return allowed_bitrates[0]
        else:
            addon_log('No bitrate in stream matched the maximum bitrate allowed.')
            return None
    else:
        return ask_bitrate(manifest_bitrates)


def dialog(dialog_type, heading, message=None, options=None, nolabel=None, yeslabel=None):
    dialog = xbmcgui.Dialog()
    if dialog_type == 'ok':
        dialog.ok(heading, message)
    elif dialog_type == 'yesno':
        return dialog.yesno(heading, message, nolabel=nolabel, yeslabel=yeslabel)
    elif dialog_type == 'select':
        ret = dialog.select(heading, options)
        if ret > -1:
            return ret
        else:
            return None


def add_item(title, parameters, items=False, folder=True, playable=False, set_info=False, set_art=False,
             watched=False, set_content=False):
    listitem = xbmcgui.ListItem(label=title)
    if playable:
        listitem.setProperty('IsPlayable', 'true')
        folder = False
    if set_art:
        listitem.setArt(set_art)
    else:
        listitem.setArt({'icon': os.path.join(addon_path, 'icon.png')})
        listitem.setArt({'fanart': os.path.join(addon_path, 'fanart.jpg')})
    if set_info:
        listitem.setInfo('video', set_info)
    if not watched:
        listitem.addStreamInfo('video', {'duration': 0})
    if set_content:
        xbmcplugin.setContent(_handle, set_content)

    recursive_url = _url + '?' + urllib.urlencode(parameters)

    if items is False:
        xbmcplugin.addDirectoryItem(_handle, recursive_url, listitem, folder)
    else:
        items.append((recursive_url, listitem, folder))
        return items


def login_process():
    try:
        vue.login(username, password)
    except vue.LoginFailure as error:
        if error.value == 'Login failed.':
            dialog('ok', language(30004), language(30005))
        elif error.value == 'No username and password supplied.':
            dialog('ok', language(30004), language(30015))
        else:
            dialog('ok', language(30004), error.value)
        sys.exit(0)


def coloring(text, meaning):
    """Return the text wrapped in appropriate color markup."""
    if meaning == 'catchup' or meaning == 'dvr':
        color = 'FF1E88F3'
    elif meaning == 'live':
        color = 'FFD20815'
    elif meaning == 'vod':
        color = 'FFABCC05'
    elif meaning == 'coming_up':
        color = 'FF333333'
    colored_text = '[COLOR=%s]%s[/COLOR]' % (color, text)
    return colored_text


def select_profile():
    profiles = vue.get_profile_names()
    if not profile:
        if len(profiles) == 1:
            profile_name = profiles[0]
            addon.setSetting('profile_name', profile_name)
            return vue.set_profile(profile_name)
        else:
            ret = dialog('select', heading=language(30016), options=profiles)
            if ret is not None:
                profile_name = profiles[ret]
                addon.setSetting('profile_name', profile_name)
                return vue.set_profile(profile_name)
            else:
                return False
    else:
        if vue.set_profile(profile):
            return True
        else:
            addon.setSetting('profile_name', '')  # reset profile if set_profile fails
            return False


def list_categories():
    categories = vue.get_categories()
    for category in categories:
        title = category['title']
        uri = category['url']
        params = {
            'action': 'list_sortings_category',
            'type': 'category',
            'uri': uri
        }

        add_item(title, params)
    xbmcplugin.endOfDirectory(_handle)


def list_sortings(type, uri=None, channel_id=None):
    if type == 'category':
        sortings = vue.parse_category_sortings(uri)
    elif type == 'channel':
        sortings = vue.parse_channel_sortings(channel_id)

    if len(sortings) == 1:  # list programs directly when there's only one sorting option
        list_programs(sortings[0]['request_method'], sortings[0]['uri'])
    else:
        for sorting in sortings:
            params = {
                'action': 'list_programs',
                'uri': sorting['uri'],
                'request_method': sorting['request_method']
            }

            add_item(sorting['title'], params)
        xbmcplugin.endOfDirectory(_handle)


def list_programs(request_method, uri=None, program_id=None, expiration_filter=None):
    items = []
    programs = vue.get_programs(request_method, uri, program_id, expiration_filter)
    for program in programs:
        program_type = program['sentv_type']
        program_id = program['id']
        detailed = program['detailed']
        playable = False
        info = return_info(program)
        art = return_art(program)
        content = None

        if program_type == 'channel':
            list_title = program['title']
            params = {
                'action': 'list_sortings_channel',
                'type': 'channel',
                'channel_id': program_id
            }
        else:
            title = info['title']
            content = 'tvshows'

            airing_status = []
            for airing in program['airings']:
                status = airing['badge'].replace('_', ' ').upper()
                status_colored = coloring(status, airing['badge'])
                if status_colored not in airing_status:
                    airing_status.append(status_colored)
            airing_status = '/'.join(airing_status)

            list_title = '%s: %s' % (airing_status, title)

            if not detailed:
                if program['is_favorite']:
                    expiration_filter = program['favorite_date']  # filter from date program was marked as favorite
                else:
                    utcnow = datetime.utcnow()
                    expiration_filter = utcnow.isoformat()  # filter out items that have expired
                params = {
                    'action': 'list_programs_detailed',
                    'request_method': 'get',
                    'program_id': program_id,
                    'expiration_filter': expiration_filter
                }
            elif program['playable']:
                params = {
                    'action': 'play',
                    'airings_data': json.dumps(parse_airings(program['airings']))
                }
                playable = True
            else:
                params = {
                    'action': 'dialog',
                    'dialog_type': 'ok',
                    'heading': 'Error',
                    'message': 'This content is not playable.'
                }

        items = add_item(list_title, params, playable=playable, set_art=art, set_info=info, set_content=content, items=items)

    xbmcplugin.addDirectoryItems(_handle, items, len(items))
    xbmcplugin.endOfDirectory(_handle)


def return_info(program):
    program_type = program['sentv_type']
    detailed = program['detailed']
    title = program.get('title')
    season = program.get('season_num')
    episode = program.get('episode_num')
    genres = []
    for genre in program['genres']:
        genres.append(genre['genre'])
    genre = ', '.join(genres)

    if program_type != 'Movies':
        tvshowtitle = program.get('title')
    else:
        tvshowtitle = None

    try:
        airing_date_obj = vue.parse_datetime(program['airing_date'], localize=True)
        aired = airing_date_obj.strftime('%Y-%m-%d')
    except KeyError:
        aired = None

    if detailed:
        if program_type != 'Movies':
            title = program.get('display_episode_title')
            plot = program.get('synopsis')
            mediatype = 'episode'
        else:
            mediatype = 'movie'
    else:
        if program.get('series_synopsis'):
            plot = program.get('series_synopsis')
        else:
            plot = program.get('synopsis')

        if program_type == 'Movies':
            mediatype = 'movie'
        else:
            mediatype = 'tvshow'

    info = {
        'title': title,
        'tvshowtitle': tvshowtitle,
        'plot': plot,
        'season': season,
        'episode': episode,
        'genre': genre,
        'aired': aired,
        'mediatype': mediatype
    }

    return info


def return_art(program):
    program_type = program['sentv_type']
    try:
        program_images = program['urls']
        highest_res = 0
        for image in program_images:
            image_res = int(image['width'])
            if image_res > highest_res:
                program_image = image['src']
                highest_res = image_res
    except KeyError:
        program_image = None
    except TypeError:
        program_image = None

    try:
        channel_images = program['channel']['urls']
        highest_res = 0
        for image in channel_images:
            image_res = int(image['width'])
            if image_res > highest_res:
                channel_image = image['src']
                highest_res = image_res
    except KeyError:
        channel_image = None
    except TypeError:
        channel_image = None

    if program_type != 'channel':
        thumb = program_image
        clearlogo = channel_image
        fanart = program_image
        cover = program_image
    else:
        thumb = program_image
        clearlogo = program_image
        fanart = None
        cover = None

    art = {
        'thumb': thumb,
        'fanart': fanart,
        'cover': cover,
        'clearlogo': clearlogo
    }

    return art


def parse_airings(airings_data):
    airings = []

    for item in airings_data:
        airing = {
            'title': '%s (%s)' % (item['channel_name'], item['type'].upper()),
            'airing_id': item['airing_id'],
            'channel_id': item['channel_id']
        }
        airings.append(airing)

    return airings


def play(airings_data):
    airings_json = json.loads(airings_data)
    if len(airings_json) == 1:
        stream_url = vue.get_stream_url(airings_json[0]['airing_id'])
        addon_log(stream_url)
    else:
        stream_url = False

    if stream_url:
        bitrate = select_bitrate(stream_url['bitrates'].keys())
        if bitrate:
            play_url = stream_url['bitrates'][bitrate]
            playitem = xbmcgui.ListItem(path=play_url)
            playitem.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(_handle, True, listitem=playitem)


def init():
    if select_profile():
        list_categories()
    else:
        dialog('ok', language(30004), language(30017))


def router(paramstring):
    """Router function that calls other functions depending on the provided paramstring."""
    params = dict(urlparse.parse_qsl(paramstring))
    if params:
        if params['action'] == 'list_sortings_category':
            list_sortings(params['type'], uri=params['uri'])
        elif params['action'] == 'list_sortings_channel':
            list_sortings(params['type'], channel_id=params['channel_id'])
        elif params['action'] == 'list_programs':
            list_programs(params['request_method'], params['uri'])
        elif params['action'] == 'list_programs_detailed':
            list_programs(params['request_method'], program_id=params['program_id'],
                          expiration_filter=params['expiration_filter'])
        elif params['action'] == 'play':
            play(params['airings_data'])
        elif params['action'] == 'dialog':
            dialog(params['dialog_type'], params['heading'], params['message'])
    else:
        init()


if __name__ == '__main__':
    if not vue.valid_session:
        login_process()
    router(sys.argv[2][1:])  # trim the leading '?' from the plugin call paramstring
