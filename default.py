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

vue = psvue(addon_profile, True, verify_ssl)


def addon_log(string):
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
        if not select_profile():
            dialog('ok', language(30004), language(30017))
            vue.reset_profile()
            sys.exit(0)
    except vue.VueError as error:
        if error.value == 'Login failed.':
            dialog('ok', language(30004), language(30005))
        elif error.value == 'No username and password supplied.':
            dialog('ok', language(30004), language(30015))
        else:
            dialog('ok', language(30004), error.value)
        sys.exit(0)


def coloring(text, meaning):
    """Return the text wrapped in appropriate color markup."""
    if meaning == 'CATCHUP' or meaning == 'DVR':
        color = 'FF1E88F3'
    elif meaning == 'LIVE':
        color = 'FFD20815'
    elif meaning == 'VOD':
        color = 'FFABCC05'
    elif meaning == 'COMING UP':
        color = 'FFF28E02'
    elif meaning == 'channel':
        color = 'FFF202DE'
    elif meaning == 'time':
        color = 'FFFFFF12'
    colored_text = '[COLOR=%s]%s[/COLOR]' % (color, text)
    return colored_text


def select_profile():
    profile_id = vue.get_credentials()['profile_id']
    profiles = vue.get_profiles()
    profile_names = vue.return_profile_names(profiles)
    if str(profile_id) not in str(profiles):
        if len(profiles) == 1:
            profile_id = profiles[0]['profile_id']
            return vue.refresh_profile_data(profile_id)
        else:
            ret = dialog('select', heading=language(30016), options=profile_names)
            if ret is not None:
                profile_id = profiles[ret]['profile_id']
                return vue.refresh_profile_data(profile_id)
            else:
                return False
    else:
        return True

def list_search():
    title = language(30021)
    params = {'action': 'search'}
    add_item(title, params)


def search():
    search_query = get_user_input(language(30022))
    if search_query:
        list_programs(request_method='get', search_query=search_query)
    else:
        addon_log('No search query provided.')
        list_categories()


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

    list_search()
    add_item(language(30024), {'action': 'list_all_channels'})
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


def live_on_top(program):
    """List live programs at the top of the listing."""
    airing_status = []
    for airing in program['airings']:
        if airing['badge'] == 'live':
            return -1
    return 1


def list_programs(request_method, uri=None, program_id=None, search_query=None, expiration_filter=None):
    items = []
    programs = vue.get_programs(request_method, uri, program_id, search_query, expiration_filter)
    if program_id:
        programs.sort(key=lambda x: x['airing_date'])  # sort detailed listing by date
        programs.sort(key=live_on_top)

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
            try:
                channel = program['channel']['name']
            except KeyError:
                channel = program['airings'][0]['channel_name']
            channel_colored = coloring(channel, 'channel')

            airing_status = []
            for airing in program['airings']:
                status = airing['badge'].replace('_', ' ').upper()
                status_colored = coloring(status, status)
                if status_colored not in airing_status:
                    airing_status.append(status_colored)
            if coloring('COMING UP', 'COMING UP') in airing_status and len(airing_status) > 1:
                # hide 'COMING UP' if it's also available as live/vod
                airing_status.remove(coloring('COMING UP', 'COMING UP'))
            airing_status = '/'.join(airing_status)

            if detailed:
                now = datetime.now()
                now_date = now.date()
                airing_date_obj = vue.parse_datetime(program['airing_date'], localize=True)
                airing_date = airing_date_obj.date()
                if addon.getSetting('time_notation') == '0': # 12 hour clock
                    airing_time = airing_date_obj.strftime('%I:%M %p')  # 12 hour clock
                else:
                    airing_time = airing_date_obj.strftime('%H:%M')
                if airing_date == now_date:
                    start_time = coloring(airing_time, 'time')
                else:
                    start_time = coloring('%s %s', 'time') % (airing_date_obj.strftime('%Y-%m-%d'), airing_time)
                list_title = '%s %s %s: %s' % (start_time, airing_status, channel_colored, title)
            else:
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
    plot = program.get('synopsis')
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
            mediatype = 'episode'
        else:
            mediatype = 'movie'
    else:
        if program.get('series_synopsis'):
            plot = program.get('series_synopsis')
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
        if item['badge'] != 'coming_up':
            airing = {
                'title': '%s (%s)' % (item['channel_name'], coloring(item['badge'].upper(), item['badge'].replace('_', ' ').upper())),
                'airing_id': item['airing_id'],
                'channel_id': item['channel_id']
            }
            airings.append(airing)

    return airings


def play(airings_data):
    airings_json = json.loads(airings_data)
    if len(airings_json) == 1:
        stream_url = vue.get_stream_url(airings_json[0]['airing_id'])
    else:
        versions = []
        for airing in airings_json:
            versions.append(airing['title'])
        selected_version = dialog('select', language(30023), options=versions)
        if selected_version is not None:
            stream_url = vue.get_stream_url(airings_json[selected_version]['airing_id'])
        else:
            return False

    if stream_url:
        bitrate = select_bitrate(stream_url['bitrates'].keys())
        if bitrate:
            play_url = stream_url['bitrates'][bitrate]
            playitem = xbmcgui.ListItem(path=play_url)
            playitem.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(_handle, True, listitem=playitem)


def play_channel(channel_id):
    stream_url = vue.get_stream_url(channel_id=channel_id)
    if stream_url:
        bitrate = select_bitrate(stream_url['bitrates'].keys())
        if bitrate:
            play_url = stream_url['bitrates'][bitrate]
            playitem = xbmcgui.ListItem(path=play_url)
            playitem.setProperty('IsPlayable', 'true')
            xbmcplugin.setResolvedUrl(_handle, True, listitem=playitem)

def list_all_channels():
    channels = vue.get_programs('get', 'channels/items/all/sort/channeltype/offset/0/size/999')

    for channel in channels:
        params = {
            'action': 'play_channel',
            'channel_id': channel['id']
        }
        add_item(channel['title'], params, set_art=return_art(channel), playable=True)
    xbmcplugin.endOfDirectory(_handle)


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
        elif params['action'] == 'search':
            search()
        elif params['action'] == 'play_channel':
            play_channel(params['channel_id'])
        elif params['action'] == 'list_all_channels':
            list_all_channels()
    else:
        list_categories()


if __name__ == '__main__':
    if not vue.valid_session:
        login_process()

    try:
        router(sys.argv[2][1:])  # trim the leading '?' from the plugin call paramstring
    except vue.VueError as error:
        if error.value == 'The user\'s geo-location has changed.':
            login_process()
            router(sys.argv[2][1:])
        elif error.value == 'There is a problem with your access.  Please close the application and then sign in again to ensure that your most recent information is used to access your subscription service.   (Error 1007)':
            login_process()
            router(sys.argv[2][1:])
        else:
            dialog('ok', 'Error', error.value)
