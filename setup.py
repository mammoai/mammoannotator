from setuptools import find_packages, setup
import os

# hacky way to get the version from the __init__.py file
path_to_setup_py = os.path.dirname(os.path.realpath(__file__))
path_to_init_py = os.path.join(path_to_setup_py, "mammoannotator", "__init__.py")
with open(path_to_init_py) as f:
    for line in f:
        if line.startswith("__version__"):
            version = line.split("=")[1].strip().strip('"')
            break

setup(
    name="mammoannotator",
    version=version,
    description="Tools for setting up a LabelStudio app for annotating breast cancer images",
    author="Fernando Cossio",
    author_email="fer_cossio@hotmail.com",
    url="",
    packages=find_packages(),
    package_dir={
        "": ".",
    },
    entry_points={
        "console_scripts": ["mammoannotator=mammoannotator.cli:main"],
    },
    install_requires=[
        "numpy",
        "matplotlib",
        "tqdm",
        "requests",
    ],
    package_data={"": ["config.xml", "instruction.html"]},
)

# Change Log:
# Version 0.1.0:
# - Initial release.
# - Started versioning the tasks.
# - The images are resized to 360 by 360px. Regardless of the original size.
# - Manual end-to-end test with LabelStudio API v 1.4
