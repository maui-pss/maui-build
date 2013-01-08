Maui OSTree
===========

This is the Maui build system for OSTree.

It takes care of building the yocto-based base system and build all the
components specified by a manifest JSON file into their own tree.

Check out from another directory the *maui* repository.
Here's an example, assuming Maui 0.1 is the version you are interested in:

```sh
cd ~
git clone -b maui-0.1 git://github.com/mauios/maui.git
```

Then get back to this directory and build *ostbuild*:

```sh
./configure
make
sudo make install
```

Configure *ostbuild*:

```sh
mkdir -p ~/ostreebuild/src/mirrors
mkdir -p ~/ostreebuild/build/tmp

mkdir -p ~/.config
cat > ~/.config/ostbuild.cfg <<EOF
[global]
mirrordir=~/ostreebuild/src/mirrors
workdir=~/ostreebuild/build
manifest=~/maui/manifest.json
EOF
```

Now resolve the components and build (always assuming that maui-0.1 is the version you are interesed in):

```sh
ostbuild resolve --fetch
ostbuild build --prefix=maui-0.1
```

Change every *maui-0.1* occurrency with the version you want to use.
