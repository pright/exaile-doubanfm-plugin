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

from libdoubanfm import DoubanFM, DoubanTrack, DoubanLoginException
from doubanfm_mode import DoubanFMMode
from doubanfm_cover import DoubanFMCover
from doubanfm_dbus import DoubanFMDBusController
from captcha_dialog import CaptchaDialog

import dbfm_pref

import gtk
import time
import urllib
from string import Template


from xl import common, event, main, playlist, xdg, settings, trax, providers, player
from xl.radio import *
from xl.nls import gettext as _
from xl.trax import Track
from xlgui import guiutil
from xlgui.accelerators import Accelerator
from xlgui.widgets import menu, menuitems, dialogs, playlist, notebook


DOUBANFM = None

def enable(exaile):
    if exaile.loading:
        event.add_callback(_enable, "exaile_loaded")
    else:
        _enable(None, exaile, None)

def _enable(device, exaile, nothing):
    global DOUBANFM

    DOUBANFM = DoubanRadioPlugin(exaile)

def disable(exaile):
    global DOUBANFM
    DOUBANFM.destroy(exaile)

def get_preferences_pane():
    return dbfm_pref

SHARE_TEMPLATE = {'kaixin001': "http://www.kaixin001.com/repaste/bshare.php?rurl=%s&rcontent=&rtitle=%s",
        'renren': "http://www.connect.renren.com/share/sharer?title=%s&url=%s",
        'sina': "http://v.t.sina.com.cn/share/share.php?appkey=3015934887&url=%s&title=%s&source=&sourceUrl=&content=utf-8&pic=%s",
        'twitter': "http://twitter.com/share?text=%s&url=%s",
        'fanfou': "http://fanfou.com/sharer?u=%s&t=%s&d=&s=bm",
        'douban': "http://shuo.douban.com/!service/share?name=%s&href=%s&image=%s&text=&desc=(%s)&apikey=0ace3f74eb3bd5d8206abe5ec1b38188&target_type=rec&target_action=0&object_kind=3043&object_id=%s"}

class DoubanRadioPlugin(object):
    @common.threaded
    def __init__(self, exaile):
        self.exaile = exaile
        ## mark if a track is skipped instead of end normally
        self.skipped = False
        self.pre_init()

    def pre_init(self):
        self.captcha_dialog = None
        self.__create_pre_init_menu_item()

    @common.threaded
    def do_init(self, captcha_id=None, captcha_solution=None):
        username = settings.get_option("plugin/douban_radio/username")
        password = settings.get_option("plugin/douban_radio/password")
        try:
            self.doubanfm = DoubanFM(username, password)
        except DoubanLoginException as e:
	    self.exaile.gui.main.message.show_error(
	        _('Douban FM Error'),
	        _('Failed to login to douban.fm with your credential'))
	    return

        self.channels = self.doubanfm.channels

        self.__create_menu_item__()

        self.check_to_enable_dbus()

        self.__register_events()

        self.doubanfm_cover = DoubanFMCover()
        providers.register('covers', self.doubanfm_cover)

        self.doubanfm_mode = DoubanFMMode(self.exaile, self)

    def show_captcha_dialog(self, captcha_id):
        if self.captcha_dialog is None:
            self.captcha_dialog = CaptchaDialog(self)

        captcha_url = "http://www.douban.com/misc/captcha?id=%s&amp;size=s" % captcha_id
        self.captcha_dialog.set_captcha(captcha_id, captcha_url)
        self.captcha_dialog.show()

    @staticmethod
    def __translate_channels():
        d = {}
        for k in DoubanFMChannels.keys():
            d[_(k)] = DoubanFMChannels[k]
        return d

    def __register_events(self):
        event.add_callback(self.check_to_load_more, 'playback_track_start')
        event.add_callback(self.close_playlist, 'quit_application')
        event.add_callback(self.play_feedback, 'playback_track_end')

        if self.dbus_controller:
            self.dbus_controller.register_events()

    def __unregister_events(self):
        event.remove_callback(self.check_to_load_more, 'playback_track_start')
        event.remove_callback(self.close_playlist, 'quit_application')
        event.remove_callback(self.play_feedback, 'playback_track_end')

        if self.dbus_controller:
            self.dbus_controller.unregister_events()

    @common.threaded
    def mark_as_skip(self, track):
        self.skipped = True
        playlist = self.get_current_playlist()

        rest_sids = self.get_rest_sids(playlist)

        ## play next song
        #self.exaile.gui.main.QUEUE.next()
        player.QUEUE.next()

        sid = track.get_tag_raw('sid')[0]
        aid = track.get_tag_raw('aid')[0]
        songs = self.doubanfm.skip_song(sid, aid, history=self.get_history_sids(playlist))
        self.load_more_tracks(songs)

    def load_more_tracks(self, songs):

        #if self.get_tracks_remain() > 5:
        #    start = self.get_current_pos()+4
        #    end = len(playlist)-1
        #    playlist.remove_tracks(start, end)


        if self.get_tracks_remain() < 5:
            tracks = map(self.create_track_from_douban_song, songs)
            playlist = self.get_current_playlist()
            playlist.extend(tracks)


    @common.threaded
    def mark_as_like(self, track):
        sid = track.get_tag_raw('sid')[0]
        aid = track.get_tag_raw('aid')[0]
        self.doubanfm.fav_song(sid, aid)
        track.set_tag_raw('fav', '1')

    @common.threaded
    def mark_as_dislike(self, track):
        sid = track.get_tag_raw('sid')[0]
        aid = track.get_tag_raw('aid')[0]

        track.set_tag_raw('fav', '0')
        self.doubanfm.unfav_song(sid, aid)

    @common.threaded
    def mark_as_recycle(self, track):
        self.skipped = True
        playlist = self.get_current_playlist()

        rest_sids = self.get_rest_sids(playlist)

        ## remove the track
        self.remove_current_track()
        ## play next song
        #self.exaile.gui.main.queue.next()
        player.QUEUE.next()


        sid = track.get_tag_raw('sid')[0]
        aid = track.get_tag_raw('aid')[0]
        songs = self.doubanfm.del_song(sid, aid, rest=rest_sids)

        self.load_more_tracks(songs)

    def get_rest_sids(self, playlist):
        playlist = self.get_current_playlist()

        #current_tracks = playlist.get_tracks()
        current_tracks = self.get_tracks(playlist)
        rest_tracks = current_tracks[playlist.get_current_position()+1:]
        rest_sids = self.tracks_to_sids(rest_tracks)
        return rest_sids

    def share(self, target, track):
        if target not in SHARE_TEMPLATE:
            return None

        templ = SHARE_TEMPLATE[target]
        data = {}
        data['title'] = track.get_tag_raw('title')[0]
        data['artist'] = track.get_tag_raw('artist')[0]
        data['sid'] = track.get_tag_raw('sid')[0]
        data['ssid'] = track.get_tag_raw('ssid')[0]
        data['picture'] = track.get_tag_raw('cover_url')[0]

        track = DoubanTrack(**data)

        if target == 'renren':
            title = track.title + ", " + track.artist
            p = templ % tuple(map(urllib.quote_plus, [title.encode('utf8'), track.get_uri()]))
            return p
        if target == 'kaixin001':
            title = track.title + ", " + track.artist
            p = templ % tuple(map(urllib.quote_plus, [track.get_uri(), title.encode('utf8')]))
            return p
        if target == 'sina':
            title = track.title + ", " + track.artist
            p = templ % tuple(map(urllib.quote_plus, [track.get_uri(), title.encode('utf8'), track.picture]))
            return p
        if target == 'twitter':
            title = track.title + ", " + track.artist
            p = templ % tuple(map(urllib.quote_plus, [title.encode('utf8'), track.get_uri()]))
            return p
        if target == 'fanfou':
            title = track.title + ", " + track.artist
            p = templ % tuple(map(urllib.quote_plus, [track.get_uri(), title.encode('utf8')]))
            return p
        if target == 'douban':
            p = templ % tuple(map(urllib.quote_plus, [track.title.encode('utf8'),track.get_uri(), track.picture, "Exaile DoubanFM Plugin",track.sid]))
            return p

    def get_tracks_remain(self):
        pl = self.get_current_playlist()
        total = len(pl)
        cursor = pl.get_current_position()
        return total-cursor-1

    def get_current_track(self):
        pl = self.get_current_playlist()
        if isinstance(pl, DoubanFMPlaylist):
            #return pl.get_tracks()[pl.get_current_pos()]
            return pl.get_current()
        else:
            return None

    def remove_current_track(self):
        pl = self.get_current_playlist()
        del pl[pl.get_current_position()]

    def tracks_to_sids(self, tracks):
        return map(lambda t: t.get_tag_raw('sid')[0], tracks)

    @common.threaded
    def play_feedback(self, type, player, current_track):
        if self.skipped:
            self.skipped = False
            return
        track = current_track
        if track.get_tag_raw('sid'):
            sid = track.get_tag_raw('sid')[0]
            aid = track.get_tag_raw('aid')[0]
            if sid is not None and aid is not None:
                self.doubanfm.played_song(sid, aid)

    def get_current_playlist(self):
        page_num = self.exaile.gui.main.playlist_notebook.get_current_page();
        page = self.exaile.gui.main.playlist_notebook.get_nth_page(page_num);
        return page.playlist
#        return self.exaile.gui.main.get_selected_playlist().playlist

    def close_playlist(self, type, exaile, data=None):
        removed = 0
        for i,page in enumerate(exaile.gui.main.playlist_notebook):
            if isinstance(page.playlist, DoubanFMPlaylist):
                page.tab.close()
                removed += 1

    def check_to_load_more(self, type, player, track):
        playlist = self.get_current_playlist()
        if isinstance(playlist, DoubanFMPlaylist):
            ## check if last one
            ## playlist.index(track), len(playlist.get_tracks())
            if self.get_tracks_remain() <= 1:
                self.load_more(playlist)

    def get_tracks(self, playlist):
        current_tracks = []
        for i, x in enumerate(playlist):
            current_tracks.append(x)
        return current_tracks

    def get_history_sids(self, playlist):
        current_tracks = self.get_tracks(playlist)
        sids = self.tracks_to_sids(current_tracks)
        return sids


    def load_more(self, playlist):
        sids = self.get_history_sids(playlist)
        current_sid = sids[playlist.get_current_position()]
        retry = 0
        while retry < 1:
            try:
                songs = self.doubanfm.played_list(current_sid, sids)
            except:
                retry += 1
                continue

            if len(songs) > 0:
                tracks = map(self.create_track_from_douban_song, songs)
                #playlist.add_tracks(tracks)
                playlist.extend(tracks)
                break
            else:
                retry += 1

    def __create_menu_item__(self):
        providers.unregister('menubar-file-menu',self.premenu)

        self.menu=gtk.Menu()
        for channel_name  in self.channels.keys():
            menuItem = gtk.MenuItem(_(channel_name))

            menuItem.connect('activate', self.active_douban_radio, self.channels[channel_name])
            self.menu.append(menuItem)
            menuItem.show()
        self.premenu=menu.simple_menu_item('Open Douban.fm',[],_('_Open Douban.fm'),
                                           None, None,[],self.menu)
        providers.register('menubar-file-menu',self.premenu)

        self.modemenu=menu.simple_menu_item('DoubanFM Mode',[],_('_DoubanFM Mode'),
                                            gtk.STOCK_FULLSCREEN,self.show_mode,
                                            accelerator='<Control>D')
        self.accelerator_mode = Accelerator('<Control>D',self.show_mode)
        providers.register('menubar-view-menu',self.modemenu)
        providers.register('mainwindow-accelerators', self.accelerator_mode)

    def __create_pre_init_menu_item(self):
        self.premenu=menu.simple_menu_item('Connect to Douban.fm',[],_('_Connect to Douban.fm'),
                                           gtk.STOCK_ADD, lambda e,r,t,y:self.do_init(),
                                           accelerator='<Control>C')
        self.accelerator_pre = Accelerator('<Control>C',lambda e,r,t,y:self.do_init())
        providers.register('menubar-file-menu',self.premenu)
        providers.register('mainwindow-accelerators', self.accelerator_pre)


    def create_track_from_douban_song(self, song):
        track = Track(song.url)
        track.set_tag_raw('sid', song.sid)
        track.set_tag_raw('aid', song.aid)
        track.set_tag_raw('ssid', song.ssid or '')

        track.set_tag_raw('uri', song.url)
        track.set_tag_raw('cover_url', song.picture)
        track.set_tag_raw('title', song.title)
        track.set_tag_raw('artist', song.artist)
        track.set_tag_raw('album', song.albumtitle)
        track.set_tag_raw('fav', str(song.like) or '0')

        return track

    def show_mode(self, *e):
        self.doubanfm_mode.show()

    def create_playlist(self, name, channel, initial_tracks=[]):
        plist = DoubanFMPlaylist(name, channel, initial_tracks)
        #plist.set_ordered_tracks(initial_tracks)

        plist.set_repeat_mode("disabled")
#        plist.set_random(False)
        plist.set_dynamic_mode("disabled")

        return plist

    def get_current_channel(self):
        return self.get_current_playlist().channel

    def active_douban_radio(self, type, channel_id, auto=False):
        self.doubanfm.channel = channel_id
        try:
            songs = self.doubanfm.new_playlist()
        except:
            dialog = gtk.MessageDialog(self.exaile.gui.main.window, 0,
                    gtk.MESSAGE_ERROR, gtk.BUTTONS_OK,
                    _('Failed to retrieve playlist, try again.'))
            dialog.run()
            dialog.destroy()
            return

        tracks = map(self.create_track_from_douban_song, songs)
        channel_name = self.channel_id_to_name(channel_id)
        plist = self.create_playlist(
                'DoubanFM %s' % channel_name, channel_id, tracks)
        self.exaile.gui.main.playlist_notebook.create_tab_from_playlist(plist)
#        self.exaile.gui.main.add_playlist(plist)

        if auto:
            self._stop()
            self._play()

    def _stop(self):
        player.PLAYER.stop()

    def _play(self):
        ## ref xlgui.main.on_playpause_button_clicked
        guimain = self.exaile.gui.main
        pl = guimain.get_selected_playlist()
        #guimain.queue.set_current_playlist(pl.playlist)
        player.QUEUE.set_current_playlist(pl.playlist)
        #if pl:
        #    track = pl.get_selected_track()
        #    if track:
        #        pl.playlist.set_current_pos((pl.playlist.index(track)))

        # set to play the first song in playlist
        pl.playlist.set_current_position(-1)
        player.QUEUE.play()

    def destroy(self, exaile):
        try:
            providers.unregister('covers', self.doubanfm_cover)
            if self.menuItem :
                self.get_menu('menubar-file-menu').remove(self.menuItem)
            if self.modeMenuItem:
                self.get_menu('menubar-view-menu').remove(self.modeMenuItem)
                exaile.gui.main.remove_accel_group(self.accels)
            self.__unregister_events()

            self.doubanfm_mode.destroy()

            if self.dbus_controller:
                self.dbus_controller.on_exit()
                self.dbus_controller.unregister_events()
                self.dbus_controller.release_dbus()
        except:
            pass

    def get_menu(self, menu_id):
        return providers.get(menu_id)

    def check_to_enable_dbus(self):
        if settings.get_option('plugin/douban_radio/dbus_indicator'):
            self.dbus_controller = DoubanFMDBusController(self)
            self.dbus_controller.acquire_dbus()
            self.dbus_controller.on_init()
        else:
            self.dbus_controller = None

    def channel_id_to_name(self, channel_id):
        for k,v in self.channels.items():
            if v == channel_id:
                return k
        return None

class DoubanFMPlaylist(playlist.Playlist):
    def __init__(self, name, channel, initTracks):
        playlist.Playlist.__init__(self, name, initTracks)
        self.channel = channel

