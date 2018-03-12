"""
Setup script for hmm_wrapper
"""

from setuptools import setup

version_num = (1, 3, 1)
version = '.'.join([str(n) for n in version_num])

setup(name='hmm_wrapper',
      version = version,
      description = 'hmm_wrapper for cellh5.py',
      author = 'Christoph Sommer, Rudolf Hoefler, Tong LI',
      author_email = 'christoph.sommer@imba.oeaw.ac.at, rudolf.hoefler@gmail.com',
      license = 'LGPL',
      # url = 'http://cellh5.org',
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
      package_data={'hmm_wrapper': ['hmm_constraint.xsd']},
      # install_requires=['vigra'],
      )
