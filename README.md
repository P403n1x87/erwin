<p align="center">
  <br>
  <img src="art/logo.png" alt="Erwin">
  <br>
</p>

<h1 align="center">Meet Erwin</h1>

<p align="center">Erwin likes to put stuff in boxes for safekeeping and synchronisation across devices,
using Google Drive as cloud storage service. He's both useless and useful, until you
try him for the first time :).</p>


<p align="center">
  <a href="https://travis-ci.org/P403n1x87/erwin">
    <img src="https://travis-ci.org/P403n1x87/erwin.svg?branch=master"
         alt="Travis CI Build Status">
  </a>
  <img src="https://img.shields.io/badge/version-0.1.1--beta-blue.svg"
       alt="Version 0.1.1-beta">
  <a href="https://github.com/P403n1x87/erwin/blob/master/LICENSE.md">
    <img src="https://img.shields.io/badge/license-GPLv3-ff69b4.svg"
         alt="LICENSE">
  </a>
</p>

<p align="center">
  <a href="#synopsis"><b>Synopsis</b></a>&nbsp;&bull;
  <a href="#installation"><b>Installation</b></a>&nbsp;&bull;
  <a href="#usage"><b>Usage</b></a>&nbsp;&bull;
  <a href="#compatibility"><b>Compatibility</b></a>&nbsp;&bull;
  <a href="#contribute"><b>Contribute</b></a>
</p>

<p align="center">
  <a href="https://www.patreon.com/bePatron?u=19221563">
    <img src="https://img.shields.io/endpoint.svg?url=https%3A%2F%2Fshieldsio-patreon.herokuapp.com%2FP403n1x87&style=for-the-badge" />
  </a><br/>

  <a href="https://www.buymeacoffee.com/Q9C1Hnm28" target="_blank">
    <img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" />
  </a>
</p>


# Synopsis

<p style="background:#FFCCCC;padding:12px;border-radius: 6px; border: solid 1px #FF8888;">
⚠️ <b>WARNING</b> Erwin is still in beta and not extensively tested. Whilst your remote files are pretty safe, it cannot be completely excluded at the moment that local files won't be lost. Use at your own risk, and if you do, please always make backup copies of important files first!</p>

Erwin is a cloud storage synchronisation service. Currently it works with Google
Drive and allows you to have a mirror local copy of the files stored on your
Google Drive account.

There are some known restrictions at the moment. There is no support for Google
Docs, which means that you won't see these files in your local copy.
Furthermore, Google Drive allows for multiple files to have the same name within
the same directory. Most local file systems don't allow for a similar thing, so
Erwin will work as expected for you only if you make sure never to use the same
name for files within the same folder.

# Installation

Erwin can be installed directly from GitHub with

~~~ bash
pip install git+https://github.com/P403n1x87/erwin
~~~


# Usage

Once installed, Erwin can be launched simply with

~~~
erwin
~~~

On the first boot, you will be prompted to enter some configuration, like an
alias for your account, and the path where you want the files to be synchronised
locally (e.g. `/home/gabriele/GoogleDrive`).

It is recommended to wrap Erwin around a systemd (user) service for easy control
and automatic startup on login (see, e.g.,
https://wiki.archlinux.org/index.php/Systemd/User for details).



# Compatibility

Erwin has been tested with Python 3.6 on Ubuntu 18.04.

# Contribute

Any help with improving Erwin is very welcome :).
