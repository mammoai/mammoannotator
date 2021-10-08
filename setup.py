from setuptools import setup, find_packages

setup(
    name='mammoannotator',
    version='0.0',
    description='Tools for setting up a LabelStudio app for annotating breast cancer images',
    author='Fernando Cossio',
    author_email='fer_cossio@hotmail.com',
    url='',
    packages=find_packages(where='src'),
    entry_points={  
    'console_scripts': [
            'mammoannotator=mammoannotator.manage_ls_project:main'
        ],
    },
    install_requires=[
        "numpy",
        "matplotlib",
        "lorem",
        "requests",
    ],
    package_data={
        "":["config.xml"]
    }
)