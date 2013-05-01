mauibuild
=========

This is the Maui build system.

It takes care of building the Yocto base system and build all the
components specified by a manifest JSON file into their own tree.

The Maui Wiki has a much more detailed documentation about the [build procedure](http://wiki.maui-project.org/System/Build).

## Prerequisites

Maui base system is based on [Poky 8.0 (danny)](https://www.yoctoproject.org/download/yocto-project-13-poky-80),
install the **Essential** packages as explained in the [Required Packages for the Host Development System](http://www.yoctoproject.org/docs/1.3/poky-ref-manual/poky-ref-manual.html#required-packages-for-the-host-development-system) section of the reference manual before preceding.

You can also read the [quick start](https://www.yoctoproject.org/docs/current/yocto-project-qs/yocto-project-qs.html) guide to learn more about Yocto.

Also install the following packages:

 * autoconf
 * automake
 * python (2.x version, it must be the default python interpreter)
 * python-gi
 * fontconfig (for fc-cache, needed during the Yocto build)
 * guestfish
 * guestfsd
 * guestmount
 * libguestfs-tools
 * elfutils (for eu-readelf)
 * squashfs-tools
 * xorriso

A 64-bit host operating system is required.

You also need:

 * Linux 2.6.28 or newer
 * *linux-user-chroot* and *ostree*, follow the next sections for more information
 * *asciidoc* if you want to create the man pages
 * The *termcolor* Python module if you want *mauibuild* to print colored output

### Setup guestfs on Ubuntu

To build disk images on Ubuntu 12.10 you will need to make a symbolic link to the right libguestfs path:

```sh
sudo ln -s /usr/lib/guestfs /usr/lib/x86_64-linux-gnu/guestfs
```

This might be needed on other Ubuntu versions as well, although only Ubuntu 12.10 was tested so far.

### Configure FUSE

If you build disk images with an unprivileged user (i.e. not root), your user must be in the *fuse* group
and FUSE must be configured to allow non-root users to specify the *allow_other* or *allow_root*
mount options.

To add the currently logged-in user to the *fuse* group on Debian and Ubuntu systems:

```sh
sudo adduser $USER fuse
```

Now edit */etc/fuse.conf* and uncomment `user_allow_other`.

### Download and install linux-user-chroot

Install the following additional packages:

 * libtool

Here's how you download and install *linux-user-chroot*:

```sh
mkdir ~/git
cd ~/git
git clone git://git.gnome.org/linux-user-chroot
cd linux-user-chroot
./autogen.sh --prefix=/usr --enable-newnet-helper
make
sudo make install
sudo chmod +s /usr/bin/linux-user-chroot{,-newnet}
```

### Download and install ostree

Install the following additional packages:

 * zlib1g-dev
 * libarchive-dev
 * libattr1-dev
 * libglib2.0-dev
 * libsoup2.4-dev
 * xsltproc
 * gtk-doc-tools

Here's how you download and install *ostree*:

```sh
mkdir ~/git
cd ~/git
git clone git://git.gnome.org/ostree
cd ostree
git submodule init
git submodule update
./autogen.sh --prefix=/usr --with-libarchive --enable-documentation --enable-kernel-updates --enable-grub2-hook
make
sudo make install
sudo mkdir /ostree
gcc -static -o ostree-init src/switchroot/ostree-switch-root.c
sudo cp ostree-init /ostree
```

## Download the manifest

Create a directory and checkout the *maui* repository.
Here's an example, assuming Maui 0.1 is the version you are interested in:

```sh
mkdir ~/git
cd ~/git
git clone -b maui-0.1 git://github.com/mauios/maui.git
```

## Install mauibuild

From the *mauibuild* checkout directory type:

```sh
./autogen.sh --enable-maintainer-mode
make
sudo make install
```

## Configure mauibuild

```sh
mkdir -p ~/mauibuildwork
cd ~/mauibuildwork
ln -s ~/git/maui/manifest.json
```

Now resolve the components and build:

```sh
mauibuild make -n resolve
```

Tasks are chained, so after a resolve a build will automatically be executed.

Every time the manifest file changes you have to type the above command.

## Remarks

Change every *maui-0.1* occurrency with the version you want to use.
