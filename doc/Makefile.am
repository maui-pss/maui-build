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

ASCIIDOC_MANS =					\
	mauibuild.1				\
	mauibuild-checkout.1			\
	mauibuild-git-mirror.1			\
	mauibuild-make.1			\
	mauibuild-make-resolve.1		\
	mauibuild-make-build.1			\
	mauibuild-make-bdiff.1			\
	mauibuild-make-builddisks.1		\
	mauibuild-make-zdisks.1			\
	mauibuild-make-buildlive.1

EXTRA_DIST =					\
	mauibuild.1.txt				\
	mauibuild-checkout.1.txt		\
	mauibuild-git-mirror.1.txt		\
	mauibuild-make.1.txt			\
	mauibuild-make-resolve.1.txt		\
	mauibuild-make-build.1.txt		\
	mauibuild-make-builddisks.1.txt		\
	mauibuild-make-zdisks.1.txt		\
	mauibuild-make-buildlive.1.txt		\
	$(ASCIIDOC_MANS)

MOSTLYCLEANFILES = $(ASCIIDOC_MANS)

dist-hook:
	$(MAKE) $(AM_MAKEFLAGS) clean
	$(MAKE) $(AM_MAKEFLAGS) all

man_MANS =
dist_man_MANS = $(ASCIIDOC_MANS)

ASCIIDOC_OPTS =						\
	-f $(srcdir)/asciidoc.conf			\
	-a mauibuild_version="$(PACKAGE_VERSION)"	\
	-a mauibuild_date="`date +%Y-%m-%d`"		\
	-a pkgdatadir=$(pkgdatadir)			\
	-a localstatedir=$(localstatedir)		\
	-a sysconfdir=$(sysconfdir)

A2X_OPTS =											\
	--no-xmllint										\
	-d manpage										\
	-f manpage										\
	--xsltproc-opts='-param man.endnotes.list.enabled 0 -param man.endnotes.are.numbered 0'	\
	--destination-dir='./'

$(ASCIIDOC_MANS): asciidoc.conf footer.txt Makefile.am
	$(AM_V_GEN)a2x $(A2X_OPTS) --asciidoc-opts="$(ASCIIDOC_OPTS) --out-file=./$@.xml" $(srcdir)/$@.txt

mauibuild.1: mauibuild.1.txt
mauibuild-checkout.1: mauibuild-checkout.1.txt
mauibuild-git-mirror.1: mauibuild-git-mirror.1.txt
mauibuild-make.1: mauibuild-make.1.txt
mauibuild-make-resolve.1: mauibuild-make-resolve.1.txt
mauibuild-make-build.1: mauibuild-make-build.1.txt
mauibuild-make-bdiff.1: mauibuild-make-bdiff.1.txt
mauibuild-make-builddisks.1: mauibuild-make-builddisks.1.txt
mauibuild-make-zdisks.1: mauibuild-make-zdisks.1.txt
mauibuild-make-buildlive.1: mauibuild-make-buildlive.1.txt
