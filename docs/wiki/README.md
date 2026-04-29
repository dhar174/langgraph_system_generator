# LangGraph System Generator Wiki

Comprehensive documentation for the LangGraph System Generator project.

## Documentation Pages

### Core Documentation

1. **[Home](Home.md)** - Project overview, vision, and key capabilities
2. **[Getting Started](Getting-Started.md)** - Installation, setup, and first generation
3. **[Architecture Deep Dive](Architecture-Deep-Dive.md)** - Internal architecture and generation pipeline
4. **[Pattern Library Guide](Pattern-Library-Guide.md)** - Complete guide to Router, Subagents, and Critique-Revise patterns
5. **[CLI & API Reference](CLI-and-API-Reference.md)** - Command-line and REST API documentation
6. **[Developer Onboarding](Developer-Onboarding.md)** - Cross-cutting local development, tracing, extension, and output guidance
7. **[Colab Usage](Colab-Usage.md)** - Using generated notebooks in Google Colab

## Quick Links

### For New Users
- Start with [Getting Started](Getting-Started.md) for installation and first steps
- Review [Home](Home.md) to understand what LangGraph System Generator can do
- Try the examples in the `examples/` directory
- Keep the latest framework docs handy:
  - [LangChain docs](https://docs.langchain.com)
  - [LangChain Python API reference](https://reference.langchain.com/python)
  - [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)

### For Developers
- Read [Architecture Deep Dive](Architecture-Deep-Dive.md) to understand internals
- Read [Developer Onboarding](Developer-Onboarding.md) for tracing, plugins,
  expected outputs, and validation commands
- Check [Pattern Library Guide](Pattern-Library-Guide.md) for pattern development
- Review [CLI & API Reference](CLI-and-API-Reference.md) for integration options
- Review [Repository Visualizations](../diagrams/README.md) for the maintainer-focused generator stage/state maps
- Use the README's **Developing Locally** section for the current editable-install
  and validation flow

### For Cloud Users
- See [Colab Usage](Colab-Usage.md) for running notebooks in Google Colab
- Check [CLI & API Reference](CLI-and-API-Reference.md) for Docker deployment
- Use stub-mode notebooks when you want Colab execution without live provider
  calls

## Documentation Organization

```
docs/wiki/
├── Home.md                      # Project overview and introduction
├── Getting-Started.md           # Installation and quickstart guide
├── Architecture-Deep-Dive.md    # Technical architecture details
├── Developer-Onboarding.md      # Cross-cutting development guide
├── Pattern-Library-Guide.md     # Pattern documentation
├── CLI-and-API-Reference.md     # Interface documentation
├── Colab-Usage.md              # Google Colab guide
└── README.md                    # This file
```

## Other Documentation

In addition to this wiki, the project includes:

- **[Main README](../../README.md)**: Quick overview and feature highlights
- **[Pattern Documentation](../patterns.md)**: Detailed pattern library reference
- **[Development Guide](../dev.md)**: Local development setup
- **[Web UI Guide](../WEB_UI_ENHANCEMENTS.md)**: Web interface documentation
- **[Examples](../../examples/)**: Runnable code examples

## Contributing to Documentation

To improve or add documentation:

1. **Edit Existing Pages**: Submit PRs with improvements
2. **Add New Pages**: Create new `.md` files following existing structure
3. **Update Links**: Ensure all cross-references work
4. **Test Examples**: Verify all code examples run correctly
5. **Check Formatting**: Use consistent Markdown formatting

### Documentation Standards

- Use clear, concise language
- Include runnable code examples
- Add diagrams where helpful (Mermaid syntax)
- Cross-link related pages
- Keep pages focused and organized
- Test all code snippets before committing

## Getting Help

- **Issues**: Report problems or request clarifications on GitHub Issues
- **Examples**: See `examples/` directory for working code
- **Tests**: Review `tests/` for usage patterns
- **Community**: Ask questions in GitHub Discussions

## Documentation Coverage

This wiki provides comprehensive coverage of:

✅ Installation and setup  
✅ CLI and API usage  
✅ Pattern library and architecture targets (Router, Subagents, Hybrid, AutoAgent, Critique-Revise)
✅ Architecture and internals  
✅ Local development and onboarding  
✅ Extension points, tracing, and logging  
✅ Multi-format export system  
✅ Structured QA, repair, rollback, and warning surfaces
✅ Google Colab integration  
✅ Troubleshooting and best practices  

## Version

This documentation targets the current **LangGraph System Generator Alpha** release. For the exact version, see the main project README or package metadata.

## License

Documentation is released under the MIT License, same as the project.

---

**Quick Start**: [Getting Started →](Getting-Started.md)
