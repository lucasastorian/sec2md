import re
from typing import List, Optional
from pydantic import BaseModel, Field, computed_field

from sec2md.utils import count_tokens as estimate_tokens  # the chunker's public name for it

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
_WS = re.compile(r'\s+')


def split_sentences(text: str) -> List[str]:
    """Split on .!? followed by whitespace and a capital letter."""
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


class BaseBlock(BaseModel):
    """Base class for markdown blocks."""
    block_type: str = Field(..., description="Type of markdown block")
    content: str = Field(..., description="Block content")
    page: int = Field(..., description="Page number")
    element_ids: Optional[List[str]] = Field(default=None, description="Element IDs backing this block")

    model_config = {"frozen": False}

    @computed_field
    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)


class Sentence(BaseModel):
    """Sentence within a text block."""
    content: str = Field(..., description="Sentence content")

    model_config = {"frozen": False}

    @computed_field
    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)


class TextBlock(BaseBlock):
    block_type: str = Field(default='Text', description="Text block type")

    @computed_field
    @property
    def sentences(self) -> List[Sentence]:
        """Returns the text block sentences"""
        return [Sentence(content=content) for content in split_sentences(self.content)]

    @classmethod
    def from_sentences(cls, sentences: List[Sentence], page: int, element_ids: Optional[List[str]] = None):
        content = " ".join([sentence.content for sentence in sentences])
        return cls(content=content, page=page, block_type='Text', element_ids=element_ids)


class TableBlock(BaseBlock):
    block_type: str = Field(default='Table', description="Table block type")

    def __init__(self, **data):
        if 'content' in data:
            data['content'] = self._to_minified_markdown_static(data['content'])
        super().__init__(**data)

    @staticmethod
    def _to_minified_markdown_static(content: str) -> str:
        """Returns the table in a Minified Markdown format"""
        lines = content.split('\n')
        cleaned_lines = []

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            parts = line.split('|')
            cleaned_parts = [_WS.sub(' ', part.strip()) for part in parts]
            cleaned_line = '|'.join(cleaned_parts)

            if i == 1:
                num_cols = len(cleaned_parts) - 1
                separator = '|' + '|'.join(['---'] * num_cols) + '|'
                cleaned_lines.append(separator)
            else:
                cleaned_lines.append(cleaned_line)

        return '\n'.join(cleaned_lines)


class HeaderBlock(BaseBlock):
    block_type: str = Field(default='Header', description="Header block type")
