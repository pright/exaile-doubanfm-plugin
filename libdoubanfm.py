# -*- coding: utf-8 -*-
# Copyright (C) 2008-2012 Sun Ning <classicning@gmail.com>
# Copyright (C) 2012 Yu Shijun <yushijun110@gmail.com>
# Copyright (C) 2012 Liu Guyue <watermelonlh@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
#
# The developers of the Exaile media player hereby grant permission
# for non-GPL compatible GStreamer and Exaile plugins to be used and
# distributed together with GStreamer and Exaile. This permission is
# above and beyond the permissions granted by the GPL license by which
# Exaile is covered. If you modify this code, you may extend this
# exception to your version of the code, but you are not obligated to
# do so. If you do not wish to do so, delete this exception statement
# from your version.


import urllib
import httplib
import json
import re
import random
import contextlib

__all__ = ['DoubanFM', 'DoubanLoginException', 'DoubanFMChannels']

class DoubanTrack(object):
    def __init__(self, **data):
        self.props = {}
        for name in data:
            self.props[name] = data[name]

    def get_start_value(self):
        return "%sg%sg0" % (self.sid, self.ssid)

    def get_uri(self):
        return "http://douban.fm/?start=%s&cid=0" % (self.get_start_value())

    def __getattr__(self, name):
        if name in self.props:
            return self.props[name]
        else:
            return None

class DoubanLoginException(Exception):
    def __init__(self, **kwargs):
        self.data = kwargs


class DoubanFM(object):
    def __init__ (self, username, password, captcha_id=None, captcha_solution=None):
        """Initialize a douban.fm session.
        * username - the user's email on douban.com
        * password - the user's password on douban.com
        """

	self.token = None
	self.user_id = None
	self.expire = None
        self._channel = 0
        self.__login(username, password)
        self.__load_channels()

    def __load_channels(self):
        f = urllib.urlopen('http://www.douban.com/j/app/radio/channels')
        #f = urllib.urlopen('http://www.douban.com/j/app/radio/channels?version=100&app_name=radio_desktop_win')
        data = f.read()
        f.close()
        channels = json.loads(data)
        self.channels = {}
        #red channel
        #self.channels['Red Heart'] = -3
        #Personal Radio High
        #self.channels['Personal Radio High'] = -4
        #Personal Radio Easy
        #self.channels['Personal Radio Easy'] = -5
        for channel in channels['channels']:
            self.channels[channel['name']] = channel['channel_id']

    @property
    def channel(self):
        """ current channel """
        return self._channel

    @channel.setter
    def channel(self, value):
        """ setter for current channel
        * value - channel id, **not channel name**
        """
        self._channel = value

    def __login(self, username, password):
        """
        login douban, get the session token
        """
	login_form = {'email':username, 'password':password,
		 'app_name':'radio_desktop_win', 'version':100}
        data = urllib.urlencode(login_form)
        contentType = "application/x-www-form-urlencoded"

        headers = {"Content-Type":contentType}
        with contextlib.closing(httplib.HTTPSConnection("www.douban.com")) as conn:
            conn.request("POST", "/j/app/login", data, headers)
            result = conn.getresponse().read()
	    data = json.loads(result)
	    err = data["err"]
	    if cmp(err, "ok"):
	        raise DoubanLoginException(**data)
            self.token = data["token"]
	    self.user_id = data["user_id"]
            self.expire = data['expire']

    def __check_login_captcha(self, webpage):
        captcha_re = re.compile(r'captcha\?id=([\w\d]+?)&amp;')
        finder = captcha_re.search(webpage)
        if finder:
            return finder.group(1)
        else:
            return None

    def __format_list(self, sidlist, verb=None):
        """
        for sidlist with ite verb status
        """
        if sidlist is None or len(sidlist) == 0:
            return ''
        else:
            if verb is not None:
                return ''.join(map(lambda s: '|'+str(s)+':'+str(verb), sidlist))
            else:
                return ''.join(map(lambda s: '|'+str(s), sidlist))

    def __get_default_params (self, typename=None):
        """
        default request parameters, for override
        """
        params = {}
        #for i in ['aid', 'channel', 'du', 'h', 'r', 'rest', 'sid', 'type', 'uid']:
            #params[i] = ''

        #params['r'] = random.random()
        #params['uid'] = self.uid
        params['channel'] = self.channel
	params['app_name'] = 'radio_desktop_win'
	params['version'] = 100
	params['user_id'] = self.user_id
	params['expire'] = self.expire
	params['token'] = self.token

        if typename is not None:
            params['type'] = typename

        return params

    def __remote_fm(self, params, start=None):
        """
        io with douban.fm
        """
        data = urllib.urlencode(params)
        with contextlib.closing(httplib.HTTPConnection("douban.fm")) as conn:
            conn.request('GET', "/j/app/radio/people?"+data)
            result = conn.getresponse().read()
            return result

### playlist related

    def json_to_douban_tracks(self, item):
        return DoubanTrack(**item)

    def new_playlist(self, history=[]):
        """
        retrieve a new playlist
        * history -  history song ids. optional.
        """
        params = self.__get_default_params('n')
        params['h'] = self.__format_list(history, True)

        results = self.__remote_fm(params)

        return map(self.json_to_douban_tracks, json.loads(results)['song'])

    def del_song(self, sid, aid, rest=[]):
        """
        delete a song from your playlist
        * sid - song id
        * aid - album id
        * rest - rest song ids in current playlist
        """
        params = self.__get_default_params('b')
        params['sid'] = sid
        params['aid'] = aid
        params['rest'] = self.__format_list(rest)

        results = self.__remote_fm(params)
        return map(self.json_to_douban_tracks, json.loads(results)['song'])

    def fav_song(self, sid, aid):
        """
        mark a song as favorite
        * sid - song id
        * aid - album id
        """
        params = self.__get_default_params('r')
        params['sid'] = sid
        params['aid'] = aid

        self.__remote_fm(params)
        ## ignore the response

    def unfav_song(self, sid, aid):
        """
        unmark a favorite song
        * sid - song id
        * aid - album id
        """
        params = self.__get_default_params('u')
        params['sid'] = sid
        params['aid'] = aid

        self.__remote_fm(params)

    def skip_song(self, sid, aid, history=[]):
        """
        skip a song, tell douban that you have skipped the song.
        * sid - song id
        * aid - album id
        * history - your playlist history(played songs and skipped songs)
        """
        params = self.__get_default_params('s')
        params['h'] = self.__format_list(history[:50])
        params['sid'] = sid
        params['aid'] = aid

        results = self.__remote_fm(params)
        return map(self.json_to_douban_tracks, json.loads(results)['song'])

    def played_song(self, sid, aid, du=0):
        """
        tell douban that you have finished a song
        * sid - song id
        * aid - album id
        * du - time your have been idle
        """
        params  = self.__get_default_params('e')
        params['sid'] = sid
        params['aid'] = aid
        params['du'] = du

        self.__remote_fm(params)

    def played_list(self, sid, history=[]):
        """
        request more playlist items
        * history - your playlist history(played songs and skipped songs)
        """
        params = self.__get_default_params('p')
        params['h'] = self.__format_list(history[:50])
        params['sid'] = sid

        results = self.__remote_fm(params)
        return map(self.json_to_douban_tracks, json.loads(results)['song'])

#### recommand related

    def __parse_ck(self, content):
        """parse ck from recommend form"""
        prog = re.compile(r'name=\\"ck\\" value=\\"([\w\d]*?)\\"')
        finder = prog.search(content)
        if finder:
            return finder.group(1)
        return None

    def recommend(self, uid, comment, title=None, t=None, ck=None):
        """recommend a uid with some comment. ck is optional, if
        not provided, we will try to fetch a ck."""

        t = t or 'W'
        if ck is None:
        ## get recommend ck
            url = "http://www.douban.com/j/recommend?type=%s&uid=%s&rec=" % (t,uid)
            with contextlib.closing(httplib.HTTPConnection("music.douban.com")) as conn:
                conn.request('GET', url)
                result = conn.getresponse().read()
                ck = self.__parse_ck(result)

        if ck:
            post = {'ck':ck, 'comment':comment, 'novote':1, 'type':t, 'uid':uid}
            if title:
                post['title'] = title

            ## convert unicode chars to bytes
            data = urllib.urlencode(post)
            ## ck ?
            accept = 'application/json'
            content_type= 'application/x-www-form-urlencoded; charset=UTF-8'
            header = {"Accept": accept,
                    "Content-Type":content_type, }

            with contextlib.closing(httplib.HTTPConnection("www.douban.com")) as conn:
                conn.request('POST', "/j/recommend", data, header)
                conn.getresponse().read()



