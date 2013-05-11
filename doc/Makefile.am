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

MANPAGES =				\
	mauibuild.1			\
	mauibuild-checkout.1		\
	mauibuild-git-mirror.1		\
	mauibuild-make.1		\
	mauibuild-make-resolve.1	\
	mauibuild-make-bdiff.1		\
	mauibuild-make-build.1		\
	mauibuild-make-builddisks.1	\
	mauibuild-make-buildlive.1	\
	mauibuild-make-zdisks.1
MANPAGES_ALIASES =

XML_FILES =			\
	${patsubsts %.1,%.xml,${patsubst %.5,%.xml,%.xml,$(MANPAGES)}}
CLEANFILES =
EXTRA_DIST = $(XML_FILES)

if ENABLE_MAN
if HAVE_XSLTPROC
if HAVE_MANPAGES_STYLESHEET

CLEANFILES += $(MANPAGES) $(MANPAGES_ALIASES)
EXTRA_DIST += $(MANPAGES) $(MANPAGES_ALIASES)
dist_man_MANS = $(MANPAGES) $(MANPAGES_ALIASES)

XSLTPROC_FLAGS = \
	--stringparam man.authors.section.enabled 0	\
	--stringparam man.copyright.section.enabled 0	\
	--stringparam funcsynopsis.style ansi		\
	--stringparam man.output.quietly 1		\
	--nonet

XSLTPROC_PROCESS_MAN =					\
	$(AM_V_GEN)$(MKDIR_P) $(dir $@) &&		\
	$(XSLTPROC) -o $@ $(XSLTPROC_FLAGS) $(MANPAGES_STYLESHEET) $<

%.1: %.xml
	$(XSLTPROC_PROCESS_MAN)

%.5: %.xml
	$(XSLTPROC_PROCESS_MAN)

endif # HAVE_MANPAGES_STYLESHEET
endif # HAVE_XSLTPROC
endif # ENABLE_MAN
