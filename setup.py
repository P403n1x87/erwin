# This file is part of "erwin" which is released under GPL.
#
# See file LICENCE or go to http://www.gnu.org/licenses/ for full license
# details.
#
# Erwin is a cloud storage synchronisation service.
#
# Copyright (c) 2020 Gabriele N. Tornetta <phoenix1987@gmail.com>.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from setuptools import setup, find_packages


setup(
    name="erwin",
    version="0.2.1",
    description="File synchronisation daemon for cloud storage service providers",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/ph403n1x87/erwin",
    author="Gabriele N. Tornetta",
    author_email="phoenix1987@gmail.com",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End User/Desktop",
        "Topic :: Desktop Environment :: File Managers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    keywords="file-syhchronization cloud-storage",
    packages=find_packages(),
    python_requires=">=3.6",
    install_requires=[
        "ansimarkup",
        "appdirs",
        "PyYAML",
        "watchdog",
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
    ],
    tests_require=["pytest"],
    entry_points={"console_scripts": ["erwin=erwin.__main__:main"]},
    project_urls={
        "Bug Reports": "https://github.com/ph403n1x87/erwin/issues",
        "Funding": "https://donate.pypi.org",
        "Say Thanks!": "http://saythanks.io/to/example",
        "Source": "https://github.com/ph403n1x87/erwin",
    },
)
