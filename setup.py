from pathlib import Path

from setuptools import find_packages, setup


BASE_DIR = Path(__file__).parent
README = (BASE_DIR / "README.md").read_text(encoding="utf-8")


setup(
    name="langgraph-system-generator",
    version="0.1.0",
    description="LangGraph Notebook Foundry scaffolding",
    long_description=README,
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "full": [
            "langgraph>=0.2.0,<1.0.0",
            "langchain>=0.3.0,<1.0.0",
            "langchain-openai>=0.2.0,<1.0.0",
            "langchain-community>=0.3.0,<1.0.0",
            "nbformat>=5.9.0",
            "nbconvert>=7.14.0",
            "python-docx>=1.1.0",
            "reportlab>=4.0.0",
            "faiss-cpu>=1.7.4",
            "chromadb>=0.4.0",
            "sentence-transformers>=2.2.0",
            "aiohttp>=3.9.0",
            "beautifulsoup4>=4.12.0",
        ],
        "dev": [
            "black>=23.0.0",
            "ruff>=0.1.0",
            "mypy>=1.7.0",
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
        ],
    },
    python_requires=">=3.9",
    author="LangGraph Contributors",
    author_email="support@langgraph.dev",
    url="https://github.com/langchain-ai/langgraph-system-generator",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Intended Audience :: Developers",
        "Development Status :: 3 - Alpha",
        "Topic :: Software Development :: Libraries",
    ],
)
