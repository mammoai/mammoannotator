from setuptools import setup, find_packages

setup(
    name='mammoannotator',
    version='0.0',
    description='Tools for setting up a LabelStudio app for annotating breast cancer images',
    author='Fernando Cossio',
    author_email='fer_cossio@hotmail.com',
    url='',
    packages=[],
    package_dir={
        "": ".",
    },
    entry_points={  
        'console_scripts': [
                'mammoannotator=mammoannotator.cli:main'
            ],
    },
    install_requires=[
        "numpy",
        "matplotlib",
        "tqdm",
        "requests",
    ],
    package_data={
        "":["config.xml", "instruction.html"]
    }
)