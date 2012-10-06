AC_PREREQ([2.63])
AC_INIT([maui-ostree], [2012.3], [pierluigi.fiorini@gmail.com], [maui-ostree], [http://www.maui-project.org])
AC_CONFIG_HEADER([config.h])
AC_CONFIG_MACRO_DIR([m4])
AC_CONFIG_AUX_DIR([build-aux])

AM_INIT_AUTOMAKE([1.11 -Wno-portability foreign no-define tar-ustar no-dist-gzip dist-xz])
AM_MAINTAINER_MODE([enable])
AM_SILENT_RULES([yes])

AM_PATH_PYTHON([2.6])

AC_ARG_ENABLE(buildsystem,
	    AS_HELP_STRING([--disable-buildsystem], [Don't install buildsystem]),,
	    enable_buildsystem=yes)
AM_CONDITIONAL(BUILDSYSTEM, test x$enable_buildsystem != xno)

AC_CONFIG_FILES([
Makefile
])
AC_OUTPUT

echo "
    Maui-OSTree $VERSION
"
