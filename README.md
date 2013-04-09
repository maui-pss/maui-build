Maui OSTree
===========

This is the Maui build system for OSTree.

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
 * fontconfig (for fc-cache, needed during the Yocto build)
 * guestfish
 * guestfsd
 * guestmount
 * libguestfs-tools
 * elfutils (for eu-readelf)

To run ```ostbuild qa-make-disk``` or ```ostbuild qa-pull-deploy``` on Ubuntu 12.10 you will need to make a symbolic link to the right libguestfs path:

```sh
sudo ln -s /usr/lib/guestfs /usr/lib/x86_64-linux-gnu/guestf
```

You also need to build and install *linux-user-chroot* and *ostree*, follow the next sections for more information.

If you want *ostbuild* to print colored output, install the *termcolor* Python module.

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

## Install ostbuild

From the ostbuild checkout directory type:

```sh
./autogen.sh --enable-maintainer-mode
make
sudo make install
```

## Configure ostbuild

```sh
mkdir -p ~/ostreebuild/src/mirrors
mkdir -p ~/ostreebuild/build/tmp

mkdir -p ~/.config
cat > ~/.config/ostbuild.cfg <<EOF
[global]
mirrordir=~/ostreebuild/src/mirrors
workdir=~/ostreebuild/build
manifest=~/git/maui/manifest.json
EOF
```

Now resolve the components and build:

```sh
ostbuild resolve --fetch
ostbuild build --prefix=maui-0.1
```

Every time the manifest file changes you have to time the above commands.

## Remarks

Change every *maui-0.1* occurrency with the version you want to use.
