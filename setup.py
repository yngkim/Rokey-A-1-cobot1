from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'cobot1'

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
]

for root, _dirs, files in os.walk('web/dist'):
    if files:
        rel = os.path.relpath(root, 'web/dist')
        dest = os.path.join('share', package_name, 'web', 'dist')
        if rel != '.':
            dest = os.path.join(dest, rel)
        data_files.append((dest, [os.path.join(root, f) for f in files]))

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=data_files,
    install_requires=['setuptools', 'PyYAML'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='rokey@todo.todo',
    description='Bedside care robot tasks for Doosan M0609 (elderly/patient assistance)',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'open_bottle = cobot1.open_bottle:main',
            'pour_water = cobot1.pour_water:main',
            'pick_place_pill = cobot1.pick_place_pill:main',
            'place_on_charger = cobot1.place_on_charger:main',
            'pick_from_charger = cobot1.pick_from_charger:main',
            'care_server = cobot1.nodes.care_server:main',
            'care_web_api = cobot1.bridge.api_server:main',
        ],
    },
)
