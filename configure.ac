AC_PREREQ([2.63])
AC_INIT([mauibuild], [0.2.90], [https://github.com/mauios/mauibuild/issues], [mauibuild], [http://www.maui-project.org])
AC_CONFIG_HEADER([config.h])
AC_CONFIG_MACRO_DIR([m4])
AC_CONFIG_AUX_DIR([build-aux])

AM_INIT_AUTOMAKE([1.11 -Wno-portability foreign no-define tar-ustar no-dist-gzip dist-xz])
AM_MAINTAINER_MODE([enable])
AM_SILENT_RULES([yes])

# Check for Python 2.6+
AM_PATH_PYTHON([2.6])

# Man pages are optional
AC_ARG_ENABLE(man,
              [AC_HELP_STRING([--disable-man],
                              [Disable man pages generation from Docbook])],
              enable_man=no,
              enable_man=yes)
AM_CONDITIONAL(ENABLE_MAN, test x$enable_man != xno)

if test "x$enable_man" = "xyes"; then
    # Look for xsltproc
    AC_PATH_PROG([XSLTPROC], [xsltproc])
    AM_CONDITIONAL([HAVE_XSLTPROC], [test "x$XSLTPROC" != "x"])

    # Check for docbook manpages stylesheet
    AC_MSG_CHECKING([for docbook manpages stylesheet])
    MANPAGES_STYLESHEET=http://docbook.sourceforge.net/release/xsl/current/manpages/docbook.xsl
    AC_PATH_PROGS_FEATURE_CHECK([XSLTPROC_TMP], [xsltproc],
                                AS_IF([`"$ac_path_XSLTPROC_TMP" --nonet "$MANPAGES_STYLESHEET" > /dev/null 2>&1`],
                                      [HAVE_MANPAGES_STYLESHEET=yes]))
    if test "x$HAVE_MANPAGES_STYLESHEET" = "xyes"; then
        AM_CONDITIONAL([HAVE_MANPAGES_STYLESHEET], true)
        AC_SUBST(MANPAGES_STYLESHEET)
        AC_MSG_RESULT([yes])
    else
        AM_CONDITIONAL([HAVE_MANPAGES_STYLESHEET], false)
        AC_MSG_RESULT([no])
    fi
else
    AM_CONDITIONAL([HAVE_XSLTPROC], false)
    AM_CONDITIONAL([HAVE_MANPAGES_STYLESHEET], false)
fi

AC_CONFIG_FILES([
Makefile
doc/Makefile
])
AC_OUTPUT
AC_MSG_RESULT([
        $PACKAGE_NAME $VERSION

        prefix:                  ${prefix}

        enable man:              ${enable_man}
])
