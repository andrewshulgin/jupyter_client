import setuptools

setuptools.setup(
    name='jupyter_client',
    version='0.0.1',
    author='Andrew Shulgin',
    author_email='andrewshulginua@gmail.com',
    description='Jupyter Notebook Server Client',
    url='https://github.org/andrewshulgin/jupyter_client',
    license='MIT',
    packages=setuptools.find_packages(),
    setup_requires=['wheel'],
    install_requires=[
        'aiohttp[speedups]',
        'websockets',
    ],
    classifiers=[
        'Programming Language :: Python :: 3.8',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
