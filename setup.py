from setuptools import setup, find_packages

setup(
    name="agent_mcp_demo",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "fastapi>=0.68.1",
        "uvicorn>=0.15.0",
        "PyGithub>=1.55",
        "python-dotenv>=0.19.0",
        "requests>=2.26.0",
        "mcp>=1.10.1",
        "httpx>=0.27.0",
        "pydantic>=1.10.12",
        "pytz>=2021.1",
        "markdown>=3.3.4",
    ],
    python_requires=">=3.8",
)