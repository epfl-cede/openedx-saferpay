import io
import os
from setuptools import find_packages, setup

here = os.path.abspath(os.path.dirname(__file__))

with io.open(os.path.join(here, "README.rst"), "rt", encoding="utf8") as f:
    readme = f.read()

setup(
    name="openedx-saferpay",
    version="10.0.0",
    url="https://github.com/epfl-cede/openedx-saferpay",
    project_urls={
        "Documentation": "https://github.com/epfl-cede/openedx-saferpay",
        "Code": "https://github.com/epfl-cede/openedx-saferpay",
        "Issue tracker": "https://github.com/epfl-cede/openedx-saferpay/issues",
    },
    license="AGPLv3",
    author="Overhang.io",
    author_email="contact@overhang.io",
    description="Saferpay payment processor for Open edX's Ecommerce",
    long_description=readme,
    long_description_content_type="text/x-rst",
    packages=find_packages(exclude=["tests*"]),
    include_package_data=True,
    python_requires=">=3.5",
    install_requires=[],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.5",
    ],
)
