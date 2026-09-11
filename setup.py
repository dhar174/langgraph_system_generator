from pathlib import Path

from setuptools import find_packages, setup


BASE_DIR = Path(__file__).parent
README = (BASE_DIR / "README.md").read_text(encoding="utf-8")

CORE_DEPENDENCIES = [
    "pydantic>=2.13.5",
    "pydantic-settings>=2.15.0",
    "python-dotenv>=1.2.3",
]

API_DEPENDENCIES = [
    "fastapi>=0.141.1",
    "uvicorn>=0.52.4",
    "sse-starlette>=3.4.11",
]

FULL_DEPENDENCIES = [
    "langgraph>=1.2.11,<2.0.0",
    "langchain>=1.4.0,<2.0.0",
    "langchain-openai>=1.6.2,<2.0.0",
    "langchain-community>=0.4.2,<1.0.0",
    "nbformat>=5.11.1",
    "nbconvert>=7.17.1",
    "jupyter_client>=8.10.0",
    "nbclient>=0.11.0",
    "ipykernel>=7.3.0",
    "python-docx>=1.2.0",
    "reportlab>=5.0.1",
    "faiss-cpu>=1.15.0",
    "chromadb>=1.5.9",
    "sentence-transformers>=6.0.1",
    "aiohttp>=3.14.3",
    "beautifulsoup4>=4.15.0",
    "httpx>=0.28.1",
    *API_DEPENDENCIES,
]

DEV_DEPENDENCIES = [
    *FULL_DEPENDENCIES,
    "black>=26.5.1",
    "ruff>=0.16.7",
    "mypy>=2.3.1",
    "pytest>=9.1.1",
    "pytest-asyncio>=1.4.0",
    "pytest-cov>=7.1.0",
    "httpx-sse>=0.4.3",
]


setup(
    name="langgraph-system-generator",
    version="1.0.0",
    description="LangGraph Notebook Foundry scaffolding",
    long_description=README,
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    package_data={
        "langgraph_system_generator.api": ["static/*"],
    },
    install_requires=CORE_DEPENDENCIES,
    extras_require={
        "api": API_DEPENDENCIES,
        "full": FULL_DEPENDENCIES,
        "dev": DEV_DEPENDENCIES,
    },
    entry_points={
        "console_scripts": [
            "lnf=langgraph_system_generator.cli:main",
        ],
    },
    python_requires=">=3.10",
    author="LangGraph Contributors",
    author_email="support@langgraph.dev",
    url="https://github.com/dhar174/langgraph_system_generator",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Intended Audience :: Developers",
        "Development Status :: 5 - Production/Stable",
        "Topic :: Software Development :: Libraries",
    ],
)
