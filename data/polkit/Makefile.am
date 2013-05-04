# Copyright (C) 2013 Pier Luigi Fiorini <pierluigi.fiorini@gmail.com>
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

org.maui.mauibuild.policy: org.maui.mauibuild.policy.in Makefile
	sed -e s,@libdir\@,$(libdir), \
	    -e s,@libexecdir\@,$(libexecdir), \
	    -e s,@datarootdir\@,$(datarootdir), \
	    -e s,@pkgdatadir\@,$(pkgdatadir), \
	    $< > $@.tmp && mv $@.tmp $@

actionsdir = $(datarootdir)/polkit-1/actions
actions_DATA =				\
	org.maui.mauibuild.policy	\
	$(NULL)

EXTRA_DIST = org.maui.mauibuild.policy.in
