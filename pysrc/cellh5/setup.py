"""
setup.py

Setup script for cellh5.py

This script installs only the library

>>>import cellh5
"""

__author__ = 'tongli.bioinfo@gmail.com'

from setuptools import setup

version_num = (1, 3, 1)
version = '.'.join([str(n) for n in version_num])

setup(name='cellh5',
      version = version,
      description = 'module for easy acces of cellh5 files',
      author = 'Christoph Sommer, Rudolf Hoefler',
      author_email = 'christoph.sommer@imba.oeaw.ac.at, rudolf.hoefler@gmail.com',
      license = 'LGPL',
      url = 'http://cellh5.org',
      classifiers=[
            # How mature is this project? Common values are
            #   3 - Alpha
            #   4 - Beta
            #   5 - Production/Stable
            'Development Status :: 3 - Alpha',

            # Indicate who your project is intended for
            'Intended Audience :: Developers',
            # Pick your license as you wish (should match "license" above)
            'License :: LGPL',

            # Specify the Python versions you support here. In particular, ensure
            # that you indicate whether you support Python 2, Python 3 or both.
            'Programming Language :: Python :: 3.6',
      ],
      package_dir = {'hmm_wrapper': 'hmm_wrapper'},
      py_modules = ['cellh5', 'cellh5write'],
      packages=['hmm_wrapper'],
      # If there are data files included in your packages that need to be
      # installed, specify them here.  If using Python 2.6 or less, then these
      # have to be included in MANIFEST.in as well.
      package_data={'hmm_wrapper': ['hmm_constraint.xsd']},
      # install_requires=['vigra'],
      )
