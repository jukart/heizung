# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

requires = [
    'gevent',
    'pyramid',
    'hbmqtt',
]

setup(
    name='heizung',
    author='Jürgen Kartnaller',
    author_email='juergen@kartnaller.at',
    version='0.0.0',
    packages=find_packages('src'),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
    ],
    entry_points={
    },
)
