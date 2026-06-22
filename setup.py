from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'cobot1'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
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
            'move = cobot1.move:main',
            'move2 = cobot1.move2:main',
            'open_bottle = cobot1.open_bottle:main',
            'pour_water = cobot1.pour_water:main',
            'pick_place_pill = cobot1.pick_place_pill:main',
            'insert_straw = cobot1.insert_straw:main',
            'turn_off_switch = cobot1.turn_off_switch:main',
            'pull_place_tissue = cobot1.pull_place_tissue:main',
            'care_server = cobot1.nodes.care_server:main',
            'ex01_joint_motion = cobot1.ex01_joint_motion:main',
            'ex02_linear_motion = cobot1.ex02_linear_motion:main',
            'ex03_circle_motion = cobot1.ex03_circle_motion:main',
            'ex04_transform_kinematics = cobot1.ex04_transform_kinematics:main',
            'ex05_motion_settings = cobot1.ex05_motion_settings:main',
            'ex06_robot_status = cobot1.ex06_robot_status:main',
        ],
    },
)
