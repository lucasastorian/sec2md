import re
from abc import ABC
from typing import List

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


class BaseBlock(ABC):
    block_type: str

    def __init__(self, content: str, page: int):
        self.content = content
        self.page = page

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)


class Sentence:

    def __init__(self, content: str):
        self.content = content

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)


class TextBlock(BaseBlock):
    block_type: str = 'Text'

    def __init__(self, content: str, page: int):
        super().__init__(content=content, page=page)

    @property
    def sentences(self) -> List[Sentence]:
        """Returns the text block sentences"""
        return [Sentence(content=content) for content in split_sentences(self.content)]

    @classmethod
    def from_sentences(cls, sentences: List[Sentence], page: int):
        content = " ".join([sentence.content for sentence in sentences])
        return cls(content=content, page=page)


class AudioParagraphBlock(BaseBlock):
    block_type: str = "Text"

    def __init__(self, content: str, page: int, paragraph_id: int, audio_start: float, audio_end: float):
        super().__init__(content=content, page=page)
        self.paragraph_id = paragraph_id
        self.audio_start = audio_start
        self.audio_end = audio_end

    @property
    def sentences(self) -> List[Sentence]:
        """Returns the text block sentences"""
        return [Sentence(content=content) for content in split_sentences(self.content)]

    def format(self) -> dict:
        """Formats the audio paragraphs"""
        return {"id": self.paragraph_id, "content": self.content, "start": self.audio_start, "end": self.audio_end}


class TableBlock(BaseBlock):
    block_type: str = 'Table'

    def __init__(self, content: str, page: int):
        super().__init__(content=content, page=page)
        self.content = self._to_minified_markdown()

    def _to_minified_markdown(self) -> str:
        """Returns the table in a Minified Markdown format"""
        lines = self.content.split('\n')
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
    block_type = 'Header'

    def __init__(self, content: str, page: int):
        super().__init__(content=content, page=page)
