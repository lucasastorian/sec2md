import re
from typing import List
from pydantic import BaseModel, Field, computed_field

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


def estimate_tokens(text: str) -> int:
    """
    Calculate token count for text.

    Uses tiktoken with cl100k_base encoding (gpt-3.5-turbo/gpt-4) if available.
    Falls back to character/4 heuristic if tiktoken is not installed.
    """
    if TIKTOKEN_AVAILABLE:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    else:
        # Fallback: simple heuristic
        return max(1, len(text) // 4)


def split_sentences(text: str) -> List[str]:
    """Simple regex-based sentence splitter"""
    # Split on .!? followed by whitespace and capital letter or end of string
    # Handles common abbreviations like Mr., Dr., Inc., etc.
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]


class BaseBlock(BaseModel):
    """Base class for markdown blocks."""
    block_type: str = Field(..., description="Type of markdown block")
    content: str = Field(..., description="Block content")
    page: int = Field(..., description="Page number")

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
    def from_sentences(cls, sentences: List[Sentence], page: int):
        content = " ".join([sentence.content for sentence in sentences])
        return cls(content=content, page=page, block_type='Text')


class AudioParagraphBlock(BaseBlock):
    block_type: str = Field(default="Text", description="Audio paragraph block type")
    paragraph_id: int = Field(..., description="Paragraph ID")
    audio_start: float = Field(..., description="Audio start time")
    audio_end: float = Field(..., description="Audio end time")

    @computed_field
    @property
    def sentences(self) -> List[Sentence]:
        """Returns the text block sentences"""
        return [Sentence(content=content) for content in split_sentences(self.content)]

    def format(self) -> dict:
        """Formats the audio paragraphs"""
        return {"id": self.paragraph_id, "content": self.content, "start": self.audio_start, "end": self.audio_end}


class TableBlock(BaseModel):
    block_type: str = Field(default='Table', description="Table block type")
    content: str = Field(..., description="Table content")
    page: int = Field(..., description="Page number")

    model_config = {"frozen": False}

    def __init__(self, **data):
        if 'content' in data:
            data['content'] = self._to_minified_markdown_static(data['content'])
        super().__init__(**data)

    @computed_field
    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)

    @staticmethod
    def _to_minified_markdown_static(content: str) -> str:
        """Returns the table in a Minified Markdown format"""
        lines = content.split('\n')
        cleaned_lines = []

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            parts = line.split('|')
            cleaned_parts = [re.sub(r'\s+', ' ', part.strip()) for part in parts]
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
