AC_PREREQ([2.63])
AC_INIT([mauibuild], [0.1.90], [https://github.com/mauios/mauibuild/issues], [mauibuild], [http://www.maui-project.org])
AC_CONFIG_HEADER([config.h])
AC_CONFIG_MACRO_DIR([m4])
AC_CONFIG_AUX_DIR([build-aux])

AM_INIT_AUTOMAKE([1.11 -Wno-portability foreign no-define tar-ustar no-dist-gzip dist-xz])
AM_MAINTAINER_MODE([enable])
AM_SILENT_RULES([yes])

# Check for Python 2.6+
AM_PATH_PYTHON([2.6])

# Check for documentation support and status
AC_CHECK_PROGS([ASCIIDOC], [asciidoc])
AC_MSG_CHECKING([for building documentation])
if test "x$wantdoc" = "xyes" ; then
	if test $ASCIIDOC ; then
		AC_MSG_RESULT([yes, enabled by configure])
	else
		asciidoc="(warning : asciidoc not installed)"
		AC_MSG_RESULT([yes $asciidoc])
	fi
	wantdoc=yes
else
	AC_MSG_RESULT([no, disabled by configure])
	wantdoc=no
fi
AM_CONDITIONAL(WANT_DOC, test "x$wantdoc" = "xyes")

AC_CONFIG_FILES([
Makefile
doc/Makefile
])
AC_OUTPUT

echo "
    Maui Build System (mauibuild) $VERSION
"
