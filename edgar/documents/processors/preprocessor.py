"""
HTML preprocessor for cleaning and normalizing HTML before parsing.
"""

import re

from edgar.documents.config import ParserConfig
from edgar.documents.utils.html_utils import remove_xml_declaration


class HTMLPreprocessor:
    """
    Preprocesses HTML to fix common issues and normalize content.

    Handles:
    - Character encoding issues
    - Malformed HTML
    - Excessive whitespace
    - Script/style removal
    - Entity normalization
    """

    def __init__(self, config: ParserConfig):
        """Initialize preprocessor with configuration."""
        self.config = config

        # Pre-compile regex patterns for performance
        self._compiled_patterns = self._compile_patterns()

    _MARKUP = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<[/!?]?[a-zA-Z](?:[^<>\"']|\"[^\"]*\"|'[^']*')*>", re.S)

    @classmethod
    def _text_only(cls, html: str, transform) -> str:
        """Apply a text cleanup outside markup, preserving attribute values."""
        parts = []
        start = 0
        for tag in cls._MARKUP.finditer(html):
            parts.extend((transform(html[start:tag.start()]), tag[0]))
            start = tag.end()
        parts.append(transform(html[start:]))
        return ''.join(parts)

    def _compile_patterns(self):
        """Pre-compile frequently used regex patterns."""
        return {
            # Encoding and cleanup
            'control_chars': re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'),

            # Script/style removal
            'script_tags': re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
            'style_tags': re.compile(r'<style[^>]*>.*?</style>', re.IGNORECASE | re.DOTALL),
            'link_tags': re.compile(r'<link[^>]*>', re.IGNORECASE),
            'comments': re.compile(r'<!--.*?-->', re.DOTALL),
            'ix_hidden': re.compile(r'<ix:hidden[^>]*>.*?</ix:hidden>', re.IGNORECASE | re.DOTALL),
            'ix_header': re.compile(r'<ix:header[^>]*>.*?</ix:header>', re.IGNORECASE | re.DOTALL),

            # Malformed tags
            'br_tags': re.compile(r'<br(?![^>]*/)>', re.IGNORECASE),
            'img_tags': re.compile(r'<img([^>]+)(?<!/)>', re.IGNORECASE),
            'input_tags': re.compile(r'<input([^>]+)(?<!/)>', re.IGNORECASE),
            'hr_tags': re.compile(r'<hr(?![^>]*/)>', re.IGNORECASE),
            'nested_p_open': re.compile(r'<p>\s*<p>', re.IGNORECASE),
            'nested_p_close': re.compile(r'</p>\s*</p>', re.IGNORECASE),

            # Whitespace normalization
            'multiple_spaces': re.compile(r'[ \t]+'),
            'multiple_newlines': re.compile(r'\n{3,}'),
            # Empty tags removal - combined pattern for all removable tags.
            # The inner run is captured because a tag holding only whitespace is not
            # empty: filers use a styled spacer span ('Safari</span><span
            # style="font-size:5.85pt"> </span><span>in the EU') to set the width of a
            # word gap, and deleting it outright glued the words either side. Same rule
            # as everywhere else in this file — collapse to a space, never delete.
            'empty_tags': re.compile(
                r'<(?:span|div|p|font|b|i|u|strong|em)\b[^>]*>(\s*)</(?:span|div|p|font|b|i|u|strong|em)>',
                re.IGNORECASE
            ),
            'empty_self_closing': re.compile(
                r'<(?:span|div|p|font|b|i|u|strong|em)\b[^>]*/>\s*',
                re.IGNORECASE
            ),

            # Common issues
            "multiple_br": re.compile(
                r"<br\s*/?>\s*<br\s*/?>\s*<br\s*/?>(?:\s*<br\s*/?>)*\s*",
                re.IGNORECASE,
            ),
            'space_before_punct': re.compile(r'\s+([.,;!?])'),
            "missing_space_after_punct": re.compile(r"(\w{2})([.!?])(?=[A-Z])"),
        }

    def process(self, html: str) -> str:
        """
        Preprocess HTML content.

        Args:
            html: Raw HTML content

        Returns:
            Cleaned HTML ready for parsing
        """
        # Remove BOM if present
        if html.startswith('\ufeff'):
            html = html[1:]

        # Remove XML declaration if present
        html = remove_xml_declaration(html)

        # Fix common character encoding issues
        html = self._text_only(html, self._fix_encoding_issues)

        # Remove script and style tags
        html = self._remove_script_style(html)

        # Normalize entities
        html = self._text_only(html, self._normalize_entities)

        # Fix malformed tags
        html = self._fix_malformed_tags(html)

        # Normalize whitespace if not preserving
        if not self.config.preserve_whitespace:
            html = self._normalize_whitespace(html)

        # Remove empty tags
        html = self._remove_empty_tags(html)

        # Fix common HTML issues
        html = self._fix_common_issues(html)

        return html

    def _fix_encoding_issues(self, html: str) -> str:
        """Fix common character encoding issues."""
        # Replace Windows-1252 characters with Unicode equivalents
        replacements = {
            '\x91': "'",  # Left single quote
            '\x92': "'",  # Right single quote
            '\x93': '"',  # Left double quote
            '\x94': '"',  # Right double quote
            '\x95': '•',  # Bullet
            '\x96': '–',  # En dash
            '\x97': '—',  # Em dash
            '\xa0': ' ',  # Non-breaking space
        }

        for old, new in replacements.items():
            html = html.replace(old, new)

        # Remove other control characters
        html = self._compiled_patterns['control_chars'].sub('', html)

        return html

    def _remove_script_style(self, html: str) -> str:
        """Remove script and style tags with content."""
        # Use pre-compiled patterns for better performance
        html = self._compiled_patterns['script_tags'].sub('', html)
        html = self._compiled_patterns['style_tags'].sub('', html)
        html = self._compiled_patterns['link_tags'].sub('', html)
        html = self._compiled_patterns['comments'].sub('', html)
        html = self._compiled_patterns['ix_hidden'].sub('', html)
        html = self._compiled_patterns['ix_header'].sub('', html)

        return html

    def _normalize_entities(self, html: str) -> str:
        """Normalize HTML entities."""
        # Common entity replacements
        entities = {
            '&nbsp;': ' ',
            '&ensp;': ' ',
            '&emsp;': '  ',
            '&thinsp;': ' ',
            '&#160;': ' ',
            '&#32;': ' ',
            '&zwj;': '',  # Zero-width joiner
            '&zwnj;': '',  # Zero-width non-joiner
            '&#8203;': '',  # Zero-width space
        }

        for entity, replacement in entities.items():
            html = html.replace(entity, replacement)

        # Fix double-encoded entities
        html = html.replace('&amp;amp;', '&amp;')
        html = html.replace('&amp;nbsp;', ' ')
        html = html.replace('&amp;lt;', '&lt;')
        html = html.replace('&amp;gt;', '&gt;')

        return html

    def _fix_malformed_tags(self, html: str) -> str:
        """Fix common malformed tag issues."""
        # Use pre-compiled patterns for better performance
        html = self._compiled_patterns['br_tags'].sub('<br/>', html)
        html = self._compiled_patterns['img_tags'].sub(r'<img\1/>', html)
        html = self._compiled_patterns['input_tags'].sub(r'<input\1/>', html)
        html = self._compiled_patterns['hr_tags'].sub('<hr/>', html)
        html = self._compiled_patterns['nested_p_open'].sub('<p>', html)
        html = self._compiled_patterns['nested_p_close'].sub('</p>', html)

        return html

    def _normalize_whitespace(self, html: str) -> str:
        """Collapse text whitespace without changing ids, URLs or style values."""
        def text(value):
            value = self._compiled_patterns['multiple_spaces'].sub(' ', value)
            value = self._compiled_patterns['multiple_newlines'].sub('\n\n', value)
            return re.sub(r'^\s+|\s+$', ' ', value)

        html = self._text_only(html, text)
        # Block spacing is outside complete tags, including quoted > characters.
        def block(match):
            tag = match[0]
            if re.match(r'<(?:div|p|h[1-6]|table|tr|ul|ol|li|blockquote)\b', tag, re.I):
                return '\n' + tag
            if re.match(r'</(?:div|p|h[1-6]|table|tr|ul|ol|li|blockquote)\b', tag, re.I):
                return tag + '\n'
            return tag
        return self._MARKUP.sub(block, html).strip()

    def _remove_empty_tags(self, html: str) -> str:
        """Remove empty tags that don't contribute content.

        A tag holding whitespace leaves that whitespace behind: it was a word gap the
        filer drew with a styled spacer element, and removing it would glue the words
        either side. A genuinely empty tag leaves nothing.
        """
        # Use pre-compiled combined patterns instead of looping
        def replacement(match, paired=True):
            # Empty anchors still establish TOC boundaries for source slicing.
            opening = match.group(0).split('>', 1)[0]
            if self.config.track_source and re.search(r'\sid\s*=', opening, re.I):
                return match.group(0)
            return ' ' if paired and match.group(1) else ''

        html = self._compiled_patterns['empty_tags'].sub(replacement, html)
        html = self._compiled_patterns['empty_self_closing'].sub(
            lambda m: replacement(m, paired=False), html)

        # The substitution above can put a space next to one the whitespace pass already
        # left, so re-collapse. Skipped when whitespace is preserved verbatim.
        if not self.config.preserve_whitespace:
            html = self._text_only(html, lambda text: self._compiled_patterns['multiple_spaces'].sub(' ', text))

        return html

    def _fix_common_issues(self, html: str) -> str:
        """Fix other common HTML issues."""
        # Use pre-compiled patterns for better performance
        html = self._compiled_patterns['multiple_br'].sub('<br/><br/>', html)
        def text(value):
            value = self._compiled_patterns['space_before_punct'].sub(r'\1', value)
            value = self._compiled_patterns['missing_space_after_punct'].sub(r'\1\2 ', value)
            return value.replace('\u200b', '').replace('\ufeff', '')
        html = self._text_only(html, text)

        # Fix common typos in tags (simple string replace is faster than regex)
        html = html.replace('<tabel', '<table')
        html = html.replace('</tabel>', '</table>')

        return html
