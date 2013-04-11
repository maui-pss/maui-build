# vim: et:ts=4:sw=4
# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
# Copyright (C) 2005 Zoran Isailovski
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

#
# C#'s event mechanism for Python, see
# http://code.activestate.com/recipes/410686/
#

class Event(object):
    class NotDeclared(Exception):
        pass

    class Slot:
        def __init__(self, name):
            self.targets = []
            self.__name__ = name

        def __repr__(self):
            return "event '%s'" % self.__name__

        def __call__(self, *args, **kwargs):
            for target in self.targets:
                target(*args, **kwargs)

        def __iadd__(self, target):
            self.targets.append(target)
            return self

        def __isub__(self, target):
            while target in self.targets:
                self.targets.remove(target)
            return self

        def __len__(self):
            return len(self.targets)

        def __iter__(self):
            def gen():
                for target in self.targets:
                    yield target
            return gen()

        def __getitem__(self, key):
            return self.targets[key]

    def __getattr__(self, name):
        if name not in self.__class__.__events__:
            raise Event.NotDeclared("Event '%s' is not declared" % name)
        self.__dict__[name] = Event.Slot(name)
        return self.__dict__[name]

    def __repr__(self):
        return "<%s.%s object at %s>" % (self.__class__.__module__,
                                         self.__class_.__name__,
                                         hex(id(self)))

    __str__ = __repr__

    def __len__(self):
        return len(self.__dict__.items())

    def __iter__(self):
        def gen(dictitems=self.__dict__.items()):
            for attr, val in dictitems:
                if isinstance(val, Event.Slot):
                    yield val
        return gen()
