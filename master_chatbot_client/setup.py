"""Legacy editable-install fallback for environments with older pip tooling."""

from setuptools import find_packages, setup


setup(
    name="master-chatbot-client",
    version="1.0.0",
    description="Python SDK for the Master Chatbot Service",
    packages=find_packages(include=["master_chatbot", "master_chatbot.*"]),
    python_requires=">=3.10",
    install_requires=["httpx>=0.24.0", "pydantic>=2.0"],
    entry_points={"console_scripts": ["master-chatbot=master_chatbot.cli:main"]},
)
