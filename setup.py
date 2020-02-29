from setuptools import setup, find_packages


setup(
    name="erwin",
    version="0.1.4",
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
