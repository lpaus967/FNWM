from setuptools import setup, find_packages

setup(
    name="fnwm",
    version="0.1.0",
    description="Fisheries National Water Model Intelligence Engine",
    author="onWater Engineering Team",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        # Dependencies will be read from requirements.txt
    ],
)
