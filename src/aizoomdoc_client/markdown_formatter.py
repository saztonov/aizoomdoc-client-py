# -*- coding: utf-8 -*-
"""
Markdown → HTML formatter for QTextBrowser.

Converts markdown text (tables, LaTeX formulas, headings, lists, etc.)
into HTML compatible with Qt's QTextBrowser widget.
"""

import re
from typing import List, Tuple


# ---------------------------------------------------------------------------
# LaTeX → Unicode mappings
# ---------------------------------------------------------------------------

_GREEK_LETTERS = {
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ',
    r'\epsilon': 'ε', r'\varepsilon': 'ε', r'\zeta': 'ζ', r'\eta': 'η',
    r'\theta': 'θ', r'\vartheta': 'ϑ', r'\iota': 'ι', r'\kappa': 'κ',
    r'\lambda': 'λ', r'\mu': 'μ', r'\nu': 'ν', r'\xi': 'ξ',
    r'\pi': 'π', r'\varpi': 'ϖ', r'\rho': 'ρ', r'\varrho': 'ϱ',
    r'\sigma': 'σ', r'\varsigma': 'ς', r'\tau': 'τ', r'\upsilon': 'υ',
    r'\phi': 'φ', r'\varphi': 'ϕ', r'\chi': 'χ', r'\psi': 'ψ',
    r'\omega': 'ω',
    # Uppercase
    r'\Gamma': 'Γ', r'\Delta': 'Δ', r'\Theta': 'Θ', r'\Lambda': 'Λ',
    r'\Xi': 'Ξ', r'\Pi': 'Π', r'\Sigma': 'Σ', r'\Upsilon': 'Υ',
    r'\Phi': 'Φ', r'\Psi': 'Ψ', r'\Omega': 'Ω',
}

_OPERATORS = {
    r'\times': '×', r'\cdot': '·', r'\div': '÷',
    r'\pm': '±', r'\mp': '∓',
    r'\leq': '≤', r'\geq': '≥', r'\neq': '≠',
    r'\approx': '≈', r'\equiv': '≡', r'\sim': '∼',
    r'\ll': '≪', r'\gg': '≫',
    r'\subset': '⊂', r'\supset': '⊃', r'\subseteq': '⊆', r'\supseteq': '⊇',
    r'\in': '∈', r'\notin': '∉', r'\ni': '∋',
    r'\cup': '∪', r'\cap': '∩',
    r'\land': '∧', r'\lor': '∨', r'\neg': '¬',
    r'\forall': '∀', r'\exists': '∃',
    r'\partial': '∂', r'\nabla': '∇',
    r'\infty': '∞',
    r'\propto': '∝',
    r'\angle': '∠',
    r'\perp': '⊥',
    r'\parallel': '∥',
    r'\circ': '∘',
    r'\dots': '…', r'\cdots': '⋯', r'\ldots': '…', r'\vdots': '⋮',
}

_ARROWS = {
    r'\rightarrow': '→', r'\leftarrow': '←',
    r'\Rightarrow': '⇒', r'\Leftarrow': '⇐',
    r'\leftrightarrow': '↔', r'\Leftrightarrow': '⇔',
    r'\uparrow': '↑', r'\downarrow': '↓',
    r'\mapsto': '↦',
}

_BIG_OPERATORS = {
    r'\sum': '∑', r'\prod': '∏', r'\coprod': '∐',
    r'\int': '∫', r'\iint': '∬', r'\iiint': '∭', r'\oint': '∮',
    r'\bigcup': '⋃', r'\bigcap': '⋂',
}

_FUNCTION_NAMES = {
    r'\lim': 'lim', r'\limsup': 'lim sup', r'\liminf': 'lim inf',
    r'\sin': 'sin', r'\cos': 'cos', r'\tan': 'tan',
    r'\arcsin': 'arcsin', r'\arccos': 'arccos', r'\arctan': 'arctan',
    r'\sinh': 'sinh', r'\cosh': 'cosh', r'\tanh': 'tanh',
    r'\sec': 'sec', r'\csc': 'csc', r'\cot': 'cot',
    r'\log': 'log', r'\ln': 'ln', r'\lg': 'lg',
    r'\exp': 'exp', r'\det': 'det', r'\dim': 'dim',
    r'\min': 'min', r'\max': 'max', r'\sup': 'sup', r'\inf': 'inf',
    r'\arg': 'arg', r'\deg': 'deg', r'\gcd': 'gcd',
    r'\mod': 'mod', r'\bmod': 'mod', r'\pmod': 'mod',
    r'\ker': 'ker', r'\hom': 'hom',
}

_MISC_SYMBOLS = {
    r'\sqrt': '√',
    r'\hbar': 'ℏ', r'\ell': 'ℓ',
    r'\Re': 'ℜ', r'\Im': 'ℑ',
    r'\aleph': 'ℵ',
    r'\emptyset': '∅', r'\varnothing': '∅',
    r'\triangle': '△',
    r'\star': '⋆',
    r'\dagger': '†', r'\ddagger': '‡',
    r'\prime': '′',
    r'\langle': '⟨', r'\rangle': '⟩',
    r'\lceil': '⌈', r'\rceil': '⌉',
    r'\lfloor': '⌊', r'\rfloor': '⌋',
    r'\quad': '  ', r'\qquad': '    ',
    r'\,': ' ', r'\;': ' ', r'\!': '',
    r'\text': '',
}

_SUPERSCRIPT_MAP = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    'n': 'ⁿ', 'i': 'ⁱ', 'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ',
    'd': 'ᵈ', 'e': 'ᵉ', 'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ',
    'j': 'ʲ', 'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'o': 'ᵒ',
    'p': 'ᵖ', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ', 'u': 'ᵘ',
    'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 'y': 'ʸ', 'z': 'ᶻ',
    'T': 'ᵀ',
}

_SUBSCRIPT_MAP = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    'a': 'ₐ', 'e': 'ₑ', 'h': 'ₕ', 'i': 'ᵢ', 'j': 'ⱼ',
    'k': 'ₖ', 'l': 'ₗ', 'm': 'ₘ', 'n': 'ₙ', 'o': 'ₒ',
    'p': 'ₚ', 'r': 'ᵣ', 's': 'ₛ', 't': 'ₜ', 'u': 'ᵤ',
    'v': 'ᵥ', 'x': 'ₓ',
}


def latex_to_unicode(latex: str) -> str:
    """Convert a LaTeX math expression to Unicode approximation."""
    text = latex.strip()

    # Remove \displaystyle, \textstyle etc.
    text = re.sub(r'\\(?:display|text|script|scriptscript)style\b', '', text)

    # \text{...} → content as-is
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)

    # \mathrm{...}, \mathbf{...}, \mathit{...} etc. → just the content
    text = re.sub(r'\\math(?:rm|bf|it|sf|tt|cal|bb|frak)\{([^}]*)\}', r'\1', text)

    # \operatorname{...} → content
    text = re.sub(r'\\operatorname\{([^}]*)\}', r'\1', text)

    # \boldsymbol{...}, \bm{...} → content
    text = re.sub(r'\\(?:boldsymbol|bm)\{([^}]*)\}', r'\1', text)

    # \left and \right delimiters (only standalone, not part of \leftarrow etc.)
    text = re.sub(r'\\left(?=[^a-zA-Z]|$)', '', text)
    text = re.sub(r'\\right(?=[^a-zA-Z]|$)', '', text)

    # \frac{a}{b} → a/b  (handles nested braces one level)
    def _replace_frac(m):
        num = m.group(1)
        den = m.group(2)
        # Recursively process numerator and denominator
        num = latex_to_unicode(num)
        den = latex_to_unicode(den)
        if len(num) == 1 and len(den) == 1:
            return f'{num}⁄{den}'  # fraction slash
        return f'({num})/({den})'

    # Match \frac{...}{...} with balanced braces (one level of nesting)
    text = re.sub(
        r'\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        _replace_frac, text
    )

    # \sqrt[n]{x} → ⁿ√x
    def _replace_sqrt_n(m):
        n = m.group(1)
        body = latex_to_unicode(m.group(2))
        sup = ''.join(_SUPERSCRIPT_MAP.get(c, c) for c in n)
        return f'{sup}√({body})'

    text = re.sub(
        r'\\sqrt\[([^\]]+)\]\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        _replace_sqrt_n, text
    )

    # \sqrt{x} → √(x)
    def _replace_sqrt(m):
        body = latex_to_unicode(m.group(1))
        if len(body) <= 2:
            return f'√{body}'
        return f'√({body})'

    text = re.sub(
        r'\\sqrt\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        _replace_sqrt, text
    )

    # Superscripts: ^{...} → Unicode superscripts
    def _replace_super(m):
        content = m.group(1)
        # Recursively process first
        content = latex_to_unicode(content)
        return ''.join(_SUPERSCRIPT_MAP.get(c, c) for c in content)

    text = re.sub(r'\^\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', _replace_super, text)

    # Single-char superscript: ^x → Unicode
    def _replace_super_single(m):
        c = m.group(1)
        return _SUPERSCRIPT_MAP.get(c, '^' + c)

    text = re.sub(r'\^([a-zA-Z0-9+\-])', _replace_super_single, text)

    # Subscripts: _{...} → Unicode subscripts
    def _replace_sub(m):
        content = m.group(1)
        content = latex_to_unicode(content)
        return ''.join(_SUBSCRIPT_MAP.get(c, c) for c in content)

    text = re.sub(r'_\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', _replace_sub, text)

    # Single-char subscript: _x → Unicode
    def _replace_sub_single(m):
        c = m.group(1)
        return _SUBSCRIPT_MAP.get(c, '_' + c)

    text = re.sub(r'_([a-zA-Z0-9])', _replace_sub_single, text)

    # Replace big operators (must come before generic symbol replacement)
    for cmd, sym in _BIG_OPERATORS.items():
        text = text.replace(cmd, sym)

    # Replace Greek letters (longer commands first to avoid partial matches)
    for cmd in sorted(_GREEK_LETTERS, key=len, reverse=True):
        text = text.replace(cmd, _GREEK_LETTERS[cmd])

    # Replace operators
    for cmd in sorted(_OPERATORS, key=len, reverse=True):
        text = text.replace(cmd, _OPERATORS[cmd])

    # Replace arrows
    for cmd in sorted(_ARROWS, key=len, reverse=True):
        text = text.replace(cmd, _ARROWS[cmd])

    # Replace misc symbols
    for cmd in sorted(_MISC_SYMBOLS, key=len, reverse=True):
        text = text.replace(cmd, _MISC_SYMBOLS[cmd])

    # Replace function names (longer first to avoid partial matches)
    for cmd in sorted(_FUNCTION_NAMES, key=len, reverse=True):
        text = text.replace(cmd, _FUNCTION_NAMES[cmd])

    # Clean up remaining braces used for grouping
    text = text.replace('{', '').replace('}', '')

    # Clean up extra whitespace
    text = re.sub(r'  +', ' ', text).strip()

    return text


# ---------------------------------------------------------------------------
# Placeholder system for protecting code blocks
# ---------------------------------------------------------------------------

_CODE_BLOCK_PH = '\x00CODEBLOCK_%d\x00'
_INLINE_CODE_PH = '\x00INLINECODE_%d\x00'
_FORMULA_BLOCK_PH = '\x00FORMULABLOCK_%d\x00'
_FORMULA_INLINE_PH = '\x00FORMULAINLINE_%d\x00'


def _protect_code_blocks(text: str) -> Tuple[str, List[str]]:
    """Extract fenced code blocks into placeholders."""
    blocks: List[str] = []

    def _replacer(m):
        lang = m.group(1) or ''
        code = m.group(2)
        # HTML-escape the code content
        code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        lang_label = f'<div style="font-size:9px; color:#999; margin-bottom:4px;">{lang}</div>' if lang.strip() else ''
        html = (
            f'<div style="background:#2d2d2d; color:#f8f8f2; padding:10px 12px; '
            f'border-radius:6px; font-family:Consolas,\'Courier New\',monospace; '
            f'font-size:12px; white-space:pre-wrap; margin:8px 0; '
            f'border:1px solid #555;">'
            f'{lang_label}'
            f'{code}</div>'
        )
        idx = len(blocks)
        blocks.append(html)
        return _CODE_BLOCK_PH % idx

    text = re.sub(r'```(\w*)\n(.*?)```', _replacer, text, flags=re.DOTALL)
    return text, blocks


def _restore_code_blocks(text: str, blocks: List[str]) -> str:
    """Restore code block placeholders with styled HTML."""
    for i, html in enumerate(blocks):
        text = text.replace(_CODE_BLOCK_PH % i, html)
    return text


def _protect_inline_code(text: str) -> Tuple[str, List[str]]:
    """Extract inline code spans into placeholders."""
    codes: List[str] = []

    def _replacer(m):
        code = m.group(1)
        code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html = (
            f'<code style="background:#f0f0f0; padding:2px 5px; border-radius:3px; '
            f'font-family:Consolas,\'Courier New\',monospace; font-size:12px; '
            f'border:1px solid #ddd;">{code}</code>'
        )
        idx = len(codes)
        codes.append(html)
        return _INLINE_CODE_PH % idx

    text = re.sub(r'`([^`\n]+?)`', _replacer, text)
    return text, codes


def _restore_inline_code(text: str, codes: List[str]) -> str:
    """Restore inline code placeholders."""
    for i, html in enumerate(codes):
        text = text.replace(_INLINE_CODE_PH % i, html)
    return text


# ---------------------------------------------------------------------------
# Formula parsing
# ---------------------------------------------------------------------------

_FORMULA_STYLE_INLINE = (
    'font-family:\'Cambria Math\',\'Times New Roman\',serif; '
    'color:#1a5276;'
)
_FORMULA_STYLE_BLOCK = (
    'background:#f8f9fa; border:1px solid #dee2e6; border-radius:6px; '
    'padding:10px 14px; margin:8px 0; text-align:center; '
    'font-family:\'Cambria Math\',\'Times New Roman\',serif; font-size:14px; '
    'color:#1a5276;'
)


def _format_block_formulas(text: str) -> Tuple[str, List[str]]:
    """Convert $$...$$ block formulas to styled HTML."""
    formulas: List[str] = []

    def _replacer(m):
        raw = m.group(1).strip()
        rendered = latex_to_unicode(raw)
        html = f'<div style="{_FORMULA_STYLE_BLOCK}">{rendered}</div>'
        idx = len(formulas)
        formulas.append(html)
        return _FORMULA_BLOCK_PH % idx

    text = re.sub(r'\$\$(.*?)\$\$', _replacer, text, flags=re.DOTALL)
    return text, formulas


def _restore_block_formulas(text: str, formulas: List[str]) -> str:
    for i, html in enumerate(formulas):
        text = text.replace(_FORMULA_BLOCK_PH % i, html)
    return text


def _format_inline_formulas(text: str) -> Tuple[str, List[str]]:
    """Convert $...$ inline formulas to styled HTML."""
    formulas: List[str] = []

    def _replacer(m):
        raw = m.group(1).strip()
        if not raw:
            return m.group(0)
        rendered = latex_to_unicode(raw)
        html = f'<span style="{_FORMULA_STYLE_INLINE}">{rendered}</span>'
        idx = len(formulas)
        formulas.append(html)
        return _FORMULA_INLINE_PH % idx

    # Match $...$ but not $$ and not escaped \$
    # Also avoid matching $ in the middle of numbers like $100
    text = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', _replacer, text)
    return text, formulas


def _restore_inline_formulas(text: str, formulas: List[str]) -> str:
    for i, html in enumerate(formulas):
        text = text.replace(_FORMULA_INLINE_PH % i, html)
    return text


# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------

_TABLE_CELL_STYLE = 'border:1px solid #ccc; padding:6px 10px;'
_TABLE_HEADER_STYLE = 'border:1px solid #ccc; padding:6px 10px; font-weight:bold; background-color:#f0f0f0;'


def _format_tables(text: str) -> str:
    """Convert markdown pipe tables to HTML tables."""
    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        # Detect table start: line with pipes, followed by separator line
        if (i + 1 < len(lines)
                and '|' in lines[i]
                and re.match(r'^\s*\|[\s\-:|]+\|\s*$', lines[i + 1])):

            table_lines = []
            # Collect header
            table_lines.append(lines[i])
            # Collect separator
            separator = lines[i + 1]
            table_lines.append(separator)
            j = i + 2

            # Collect body rows
            while j < len(lines) and '|' in lines[j] and lines[j].strip().startswith('|'):
                table_lines.append(lines[j])
                j += 1

            # Parse alignment from separator
            sep_cells = [c.strip() for c in separator.strip().strip('|').split('|')]
            alignments = []
            for cell in sep_cells:
                cell = cell.strip()
                if cell.startswith(':') and cell.endswith(':'):
                    alignments.append('center')
                elif cell.endswith(':'):
                    alignments.append('right')
                else:
                    alignments.append('left')

            # Build HTML table
            html = (
                '<table border="1" cellpadding="6" cellspacing="0" '
                'style="border-collapse:collapse; border:1px solid #ccc; margin:8px 0; '
                'width:auto;">'
            )

            # Header row
            header_cells = [c.strip() for c in table_lines[0].strip().strip('|').split('|')]
            html += '<tr>'
            for ci, cell in enumerate(header_cells):
                align = alignments[ci] if ci < len(alignments) else 'left'
                html += f'<td style="{_TABLE_HEADER_STYLE} text-align:{align};">{cell}</td>'
            html += '</tr>'

            # Body rows
            for row_line in table_lines[2:]:
                cells = [c.strip() for c in row_line.strip().strip('|').split('|')]
                html += '<tr>'
                for ci, cell in enumerate(cells):
                    align = alignments[ci] if ci < len(alignments) else 'left'
                    html += f'<td style="{_TABLE_CELL_STYLE} text-align:{align};">{cell}</td>'
                html += '</tr>'

            html += '</table>'
            result.append(html)
            i = j
        else:
            result.append(lines[i])
            i += 1

    return '\n'.join(result)


# ---------------------------------------------------------------------------
# Block-level elements
# ---------------------------------------------------------------------------

def _format_headers(text: str) -> str:
    """Convert # headers to styled HTML."""
    sizes = {1: 20, 2: 17, 3: 15, 4: 14, 5: 13, 6: 12}

    def _replacer(m):
        level = len(m.group(1))
        content = m.group(2).strip()
        sz = sizes.get(level, 12)
        return (
            f'<div style="font-size:{sz}px; font-weight:bold; '
            f'margin:10px 0 6px 0; color:#222;">{content}</div>'
        )

    text = re.sub(r'^(#{1,6})\s+(.+)$', _replacer, text, flags=re.MULTILINE)
    return text


def _format_blockquotes(text: str) -> str:
    """Convert > blockquotes to styled HTML."""
    lines = text.split('\n')
    result = []
    in_quote = False
    quote_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('> ') or stripped == '>':
            content = stripped[2:] if stripped.startswith('> ') else ''
            quote_lines.append(content)
            in_quote = True
        else:
            if in_quote:
                quote_content = '<br>'.join(quote_lines)
                result.append(
                    f'<div style="border-left:3px solid #ccc; padding-left:12px; '
                    f'color:#555; margin:6px 0; font-style:italic;">'
                    f'{quote_content}</div>'
                )
                quote_lines = []
                in_quote = False
            result.append(line)

    if in_quote:
        quote_content = '<br>'.join(quote_lines)
        result.append(
            f'<div style="border-left:3px solid #ccc; padding-left:12px; '
            f'color:#555; margin:6px 0; font-style:italic;">'
            f'{quote_content}</div>'
        )

    return '\n'.join(result)


def _format_lists(text: str) -> str:
    """Convert markdown lists to HTML lists."""
    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Unordered list
        ul_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if ul_match:
            items = []
            while i < len(lines):
                m = re.match(r'^(\s*)[-*+]\s+(.+)$', lines[i])
                if m:
                    items.append(m.group(2))
                    i += 1
                else:
                    break
            html = '<ul style="margin:4px 0 4px 20px; padding:0;">'
            for item in items:
                html += f'<li style="margin:2px 0;">{item}</li>'
            html += '</ul>'
            result.append(html)
            continue

        # Ordered list
        ol_match = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
        if ol_match:
            items = []
            while i < len(lines):
                m = re.match(r'^(\s*)\d+\.\s+(.+)$', lines[i])
                if m:
                    items.append(m.group(2))
                    i += 1
                else:
                    break
            html = '<ol style="margin:4px 0 4px 20px; padding:0;">'
            for item in items:
                html += f'<li style="margin:2px 0;">{item}</li>'
            html += '</ol>'
            result.append(html)
            continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def _format_hr(text: str) -> str:
    """Convert --- or *** to horizontal rule."""
    return re.sub(
        r'^[ \t]*[-*_]{3,}[ \t]*$',
        '<hr style="border:none; border-top:1px solid #ccc; margin:10px 0;">',
        text,
        flags=re.MULTILINE
    )


# ---------------------------------------------------------------------------
# Inline elements
# ---------------------------------------------------------------------------

def _format_inline(text: str) -> str:
    """Convert inline markdown: bold, italic, strikethrough, links."""
    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic: *text* or _text_ (but not inside words for _)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)', r'<i>\1</i>', text)

    # Strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # Links: [text](url)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" style="color:#2980b9; text-decoration:underline;">\1</a>',
        text
    )

    # Images: ![alt](url) — show as linked image placeholder
    text = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        r'<a href="\2" style="color:#2980b9;">[Изображение: \1]</a>',
        text
    )

    return text


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def format_message(text: str) -> str:
    """
    Convert markdown text to HTML suitable for QTextBrowser.

    Handles: code blocks, inline code, LaTeX formulas (block and inline),
    tables, headers, blockquotes, lists, horizontal rules, bold, italic,
    strikethrough, links.
    """
    if not text:
        return ''

    # 1. Protect code blocks (``` ... ```)
    text, code_blocks = _protect_code_blocks(text)

    # 2. Protect inline code (` ... `)
    text, inline_codes = _protect_inline_code(text)

    # 3. Block LaTeX formulas ($$ ... $$) — before inline formulas
    text, block_formulas = _format_block_formulas(text)

    # 4. Inline LaTeX formulas ($ ... $)
    text, inline_formulas = _format_inline_formulas(text)

    # 5. Tables
    text = _format_tables(text)

    # 6. Headers
    text = _format_headers(text)

    # 7. Blockquotes
    text = _format_blockquotes(text)

    # 8. Lists
    text = _format_lists(text)

    # 9. Horizontal rules
    text = _format_hr(text)

    # 10. Inline formatting (bold, italic, strikethrough, links)
    text = _format_inline(text)

    # 11. Convert remaining newlines to <br>
    text = text.replace('\n', '<br>')

    # 12. Restore all placeholders
    text = _restore_block_formulas(text, block_formulas)
    text = _restore_inline_formulas(text, inline_formulas)
    text = _restore_inline_code(text, inline_codes)
    text = _restore_code_blocks(text, code_blocks)

    return text
