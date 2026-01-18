"""Shared utilities for pattern generators."""

from typing import Optional


def build_llm_init(
    model: str,
    temperature: float,
    api_base: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Build ChatOpenAI initialization string with optional parameters.
    
    Args:
        model: The LLM model identifier
        temperature: Temperature for LLM sampling (0.0-2.0)
        api_base: Optional custom API base URL
        max_tokens: Optional maximum tokens for LLM response
        
    Returns:
        String representation of ChatOpenAI initialization code
        
    Example:
        >>> build_llm_init("gpt-5-mini", 0.7)
        'ChatOpenAI(model="gpt-5-mini", temperature=0.7)'
        >>> build_llm_init("gpt-5-mini", 0, api_base="https://custom.api", max_tokens=1000)
        'ChatOpenAI(model="gpt-5-mini", temperature=0, base_url="https://custom.api", max_tokens=1000)'
    """
    params = [f'model="{model}"', f'temperature={temperature}']
    if api_base:
        params.append(f'base_url="{api_base}"')
    if max_tokens:
        params.append(f'max_tokens={max_tokens}')
    return f"ChatOpenAI({', '.join(params)})"
