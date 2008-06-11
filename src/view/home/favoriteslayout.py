# Copyright (C) 2008 One Laptop Per Child
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import logging
import math
import hashlib

import gobject
import gtk
import hippo

from sugar.graphics import style
from sugar import activity

_logger = logging.getLogger('FavoritesLayout')

class FavoritesLayout(gobject.GObject, hippo.CanvasLayout):
    __gtype_name__ = 'FavoritesLayout'

    def __init__(self):
        gobject.GObject.__init__(self)
        self.box = None
        self.fixed_positions = {}

    def do_set_box(self, box):
        self.box = box

    def do_get_height_request(self, for_width):
        return 0, gtk.gdk.screen_height() - style.GRID_CELL_SIZE

    def do_get_width_request(self):
        return 0, gtk.gdk.screen_width()

    def _compare_activities(self, icon_a, icon_b):
        if hasattr(icon_a, 'installation_time') and \
                hasattr(icon_b, 'installation_time'):
            return icon_b.installation_time - icon_a.installation_time
        else:
            return 0

    def append(self, icon):
        self.box.insert_sorted(icon, 0, self._compare_activities)
        relative_x, relative_y = icon.fixed_position
        if relative_x >= 0 and relative_y >= 0:
            width = gtk.gdk.screen_width()
            height = gtk.gdk.screen_height() - style.GRID_CELL_SIZE
            self.fixed_positions[icon] = (relative_x * 1000 / width,
                                           relative_y * 1000 / height)
        self.update_icon_sizes()

    def remove(self, icon):
        del self.fixed_positions[icon]
        self.box.remove(icon)
        self.update_icon_sizes()

    def move_icon(self, icon, x, y):
        if icon not in self.box.get_children():
            raise ValueError('Child not in box.')

        width = gtk.gdk.screen_width()
        height = gtk.gdk.screen_height() - style.GRID_CELL_SIZE
        registry = activity.get_registry()
        registry.set_activity_position(icon.get_bundle_id(), icon.get_version(),
                                       x * width / 1000, y * height / 1000)

        self.fixed_positions[icon] = (x, y)
        self.box.emit_request_changed()

    def update_icon_sizes(self):
        pass

    def do_allocate(self, x, y, width, height, req_width, req_height,
                    origin_changed):
        raise NotImplementedError()

class RandomLayout(FavoritesLayout):
    __gtype_name__ = 'RandomLayout'

    def __init__(self):
        FavoritesLayout.__init__(self)

    def append(self, icon):
        FavoritesLayout.append(self, icon)
        icon.props.size = style.STANDARD_ICON_SIZE

    def do_allocate(self, x, y, width, height, req_width, req_height,
                    origin_changed):
        for child in self.box.get_layout_children():
            # We need to always get requests to not confuse hippo
            min_w_, child_width = child.get_width_request()
            min_h_, child_height = child.get_height_request(child_width)

            if child.item in self.fixed_positions:
                x, y = self.fixed_positions[child.item]
            else:
                name_hash = hashlib.md5(child.item.get_bundle_id())
                
                x = int(name_hash.hexdigest()[:5], 16) % (width - child_width)
                y = int(name_hash.hexdigest()[-5:], 16) % (height - child_height)
                
                # TODO Handle collisions

            child.allocate(int(x), int(y), child_width, child_height,
                            origin_changed)

_MINIMUM_RADIUS = style.XLARGE_ICON_SIZE / 2 + style.DEFAULT_SPACING + \
        style.STANDARD_ICON_SIZE * 2
_MAXIMUM_RADIUS = (gtk.gdk.screen_height() - style.GRID_CELL_SIZE) / 2 - \
        style.STANDARD_ICON_SIZE - style.DEFAULT_SPACING

class RingLayout(FavoritesLayout):
    __gtype_name__ = 'RingLayout'

    def __init__(self):
        FavoritesLayout.__init__(self)

    def _calculate_radius_and_icon_size(self, children_count):
        angle = 2 * math.pi / children_count

        # what's the radius required without downscaling?
        distance = style.STANDARD_ICON_SIZE + style.DEFAULT_SPACING
        icon_size = style.STANDARD_ICON_SIZE
        
        if children_count == 1:
            radius = 0
        else:
            radius = math.sqrt(distance ** 2 /
                    (math.sin(angle) ** 2 + (math.cos(angle) - 1) ** 2))
        
        if radius < _MINIMUM_RADIUS:
            # we can upscale, if we want
            icon_size += style.STANDARD_ICON_SIZE * \
                    (0.5 * (_MINIMUM_RADIUS - radius) / _MINIMUM_RADIUS)
            radius = _MINIMUM_RADIUS
        elif radius > _MAXIMUM_RADIUS:
            radius = _MAXIMUM_RADIUS
            # need to downscale. what's the icon size required?
            distance = math.sqrt((radius * math.sin(angle)) ** 2 + \
                    (radius * (math.cos(angle) - 1)) ** 2)
            icon_size = distance - style.DEFAULT_SPACING
        
        return radius, icon_size

    def _calculate_position(self, radius, icon_size, index, children_count):
        width, height = self.box.get_allocation()
        angle = index * (2 * math.pi / children_count) - math.pi / 2
        x = radius * math.cos(angle) + (width - icon_size) / 2
        y = radius * math.sin(angle) + (height - icon_size -
                                        style.GRID_CELL_SIZE) / 2
        return x, y

    def _get_children_in_ring(self):
        children = self.box.get_layout_children()
        width, height = self.box.get_allocation()
        children_in_ring = []
        for child in children:
            if child.item in self.fixed_positions:
                x, y = self.fixed_positions[child.item]
                distance_to_center = math.hypot(x - width / 2, y - height / 2)
                # TODO at what distance should we consider a child inside the ring?
            else:
                children_in_ring.append(child)

        return children_in_ring

    def update_icon_sizes(self):
        children_in_ring = self._get_children_in_ring()
        if children_in_ring:
            radius_, icon_size = \
                    self._calculate_radius_and_icon_size(len(children_in_ring))

            for n in range(len(children_in_ring)):
                child = children_in_ring[n]
                child.item.props.size = icon_size

        for child in self.box.get_layout_children():
            if child not in children_in_ring:
                child.item.props.size = style.STANDARD_ICON_SIZE

    def do_allocate(self, x, y, width, height, req_width, req_height,
                    origin_changed):
        children_in_ring = self._get_children_in_ring()
        if children_in_ring:
            radius, icon_size = \
                    self._calculate_radius_and_icon_size(len(children_in_ring))

            for n in range(len(children_in_ring)):
                child = children_in_ring[n]

                x, y = self._calculate_position(radius, icon_size, n,
                                                len(children_in_ring))

                # We need to always get requests to not confuse hippo
                min_w_, child_width = child.get_width_request()
                min_h_, child_height = child.get_height_request(child_width)

                child.allocate(int(x), int(y), child_width, child_height,
                               origin_changed)

        for child in self.box.get_layout_children():
            if child in children_in_ring:
                continue

            # We need to always get requests to not confuse hippo
            min_w_, child_width = child.get_width_request()
            min_h_, child_height = child.get_height_request(child_width)

            x, y = self.fixed_positions[child.item]

            child.allocate(int(x), int(y), child_width, child_height,
                            origin_changed)
