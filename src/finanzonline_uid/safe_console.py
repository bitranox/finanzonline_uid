"""Encode-safe console output.

Purpose
-------
Wraps :func:`click.echo` so a console whose codepage cannot represent a glyph
degrades that glyph instead of aborting the command.

Why
---
Console output is a sink with an encoding the program does not choose. Python
hands stdout to a Windows console at codepage 1252 with ``errors="strict"``, so
writing ``✓`` raises ``UnicodeEncodeError: 'charmap' codec can't encode
character '\\u2713'`` and the command exits non-zero -- after its real work has
already succeeded, which is the part that misleads. ``click.echo`` does not
protect against this; the exception propagates.

Degrading at the SINK keeps the glyphs where they are wanted: an email body or
a UTF-8 terminal still receives ``✓``, and only a stream that genuinely cannot
encode it sees ``[OK]``. Callers therefore write the glyph they mean and never
branch on the platform.

Contents
--------
* :data:`ASCII_FALLBACKS` - the glyph-to-ASCII map
* :func:`ascii_fallback` - transliterate text for a target encoding
* :func:`encode_safe` - degrade text only when the encoding rejects it
* :func:`echo` - the :func:`click.echo` replacement every module uses
* :func:`safe_stream` - the same protection for a writer this module does not
  own, such as the one a :class:`rich.console.Console` writes through
"""

from __future__ import annotations

import io
import sys
from collections.abc import Iterable, Iterator
from types import TracebackType
from typing import IO, Any, BinaryIO, Final, TextIO

import rich_click as click

ASCII_FALLBACKS: Final[dict[str, str]] = {
    "✓": "[OK]",  # check mark
    "✔": "[OK]",  # heavy check mark
    "✅": "[OK]",  # white heavy check mark
    "✗": "[X]",  # ballot X
    "✘": "[X]",  # heavy ballot X
    "❌": "[X]",  # cross mark
    "⚠": "[!]",  # warning sign
    "️": "",  # variation selector 16, trails an emoji glyph and carries no text
    "•": "-",  # bullet
    "≥": ">=",
    "≤": "<=",
    "→": "->",
    "←": "<-",
    # The quotation marks are spelled as escapes on purpose: written literally
    # they are indistinguishable from ASCII ' and " in most editors, which is
    # exactly the confusion ruff's RUF001 exists to flag.
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u201c": '"',  # left double quotation mark
    "\u201d": '"',  # right double quotation mark
    "…": "...",
}

#: Encodings that represent every code point, so the check can be skipped.
_UNIVERSAL_ENCODINGS: Final[frozenset[str]] = frozenset({"utf-8", "utf8", "utf-16", "utf16", "utf-32", "utf32"})


def _stream_encoding(file: IO[Any] | None, *, err: bool = False) -> str | None:
    """Return the target stream's encoding, or None when it cannot be determined.

    An unknown encoding means the caller gets the original text: guessing would
    degrade output that may well have been fine.

    With no explicit `file` the answer comes from ``sys.stdout``/``sys.stderr``,
    which is what :func:`click.echo` resolves its own default target from. click
    exposes no supported way to ask for that stream: ``get_text_stream`` was
    deprecated in click 8.5.0 and is removed in 9.0, its documented replacement
    being to let ``echo`` resolve the stream itself.
    """
    stream = file if file is not None else (sys.stderr if err else sys.stdout)
    encoding = getattr(stream, "encoding", None)
    return encoding if isinstance(encoding, str) else None


def ascii_fallback(text: str, encoding: str) -> str:
    """Rewrite `text` so it survives `encoding`.

    Known glyphs become their ASCII equivalent from :data:`ASCII_FALLBACKS`;
    anything else the codec still cannot represent becomes ``?``. Text the
    encoding already accepts is returned unchanged.

    Parameters
    ----------
    text:
        The message as the caller wrote it.
    encoding:
        The target stream's encoding, e.g. ``"cp1252"``.

    Returns
    -------
    str
        A string that :meth:`str.encode` accepts for `encoding`.
    """
    mapped = "".join(ASCII_FALLBACKS.get(character, character) for character in text)
    return mapped.encode(encoding, errors="replace").decode(encoding)


def encode_safe(text: str, encoding: str | None) -> str:
    """Return `text` if `encoding` accepts it, else its ASCII fallback.

    The check runs BEFORE the write on purpose. Writing first and catching
    ``UnicodeEncodeError`` would leave the already-encoded prefix on the stream,
    so the retry would duplicate it.
    """
    if encoding is None or encoding.lower() in _UNIVERSAL_ENCODINGS:
        return text
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return ascii_fallback(text, encoding)
    return text


def echo(message: object = "", *, file: IO[Any] | None = None, err: bool = False, nl: bool = True) -> None:
    """Write `message` to the console, degrading anything it cannot encode.

    Drop-in for :func:`click.echo` for the arguments this project uses.

    Parameters
    ----------
    message:
        The text to write. Non-string values are stringified as click does.
    file:
        Target stream. Defaults to click's stdout (or stderr when `err`).
    err:
        Write to stderr instead of stdout.
    nl:
        Append a newline.

    Side Effects
    ------------
    Writes to the given stream.
    """
    text = message if isinstance(message, str) else str(message)
    click.echo(encode_safe(text, _stream_encoding(file, err=err)), file=file, err=err, nl=nl)


class _SafeWriter(TextIO):
    """A write-only text stream that degrades what the wrapped stream cannot encode.

    Why
        Rich renders through a writer this module does not control, and it
        raises the same ``UnicodeEncodeError`` on a legacy codepage rather than
        substituting. Wrapping the writer applies the fallback to every segment
        rich emits without rich needing to know.

        With no explicit stream the target is resolved at WRITE time, not at
        construction. A module-level ``Console(file=safe_stream())`` built at
        import would otherwise capture the interpreter's original stdout, and
        anything that later swaps ``sys.stdout`` - click's ``CliRunner``,
        ``contextlib.redirect_stdout``, pytest's capture - would be bypassed
        and its buffer would come back empty.

        It is a full :class:`typing.TextIO` because rich's ``Console(file=...)``
        is typed ``IO[str]``. Only writing is supported; reading, seeking and
        ``fileno`` raise :class:`io.UnsupportedOperation` like any in-memory
        stream. ``fileno`` in particular must not hand out the target's
        descriptor: rich would then take its legacy Windows path for a standard
        stream and write around :meth:`write`, skipping the fallback.
    """

    def __init__(self, stream: TextIO | None) -> None:
        self._stream = stream

    def _target(self) -> TextIO:
        return self._stream if self._stream is not None else sys.stdout

    def write(self, s: str, /) -> int:
        """Write `s`, degrading anything the current target cannot encode."""
        target = self._target()
        encoding = getattr(target, "encoding", None)
        return target.write(encode_safe(s, encoding if isinstance(encoding, str) else None))

    def writelines(self, lines: Iterable[str], /) -> None:
        """Write each line through :meth:`write`."""
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        """Flush the current target."""
        self._target().flush()

    def isatty(self) -> bool:
        """Report the target's tty-ness, so rich keeps its styling."""
        return self._target().isatty()

    @property
    def encoding(self) -> str:
        """Expose the target's encoding; rich inspects it.

        An unknown encoding reads as ``utf-8``, the value rich itself assumes
        for a writer without one.
        """
        encoding = getattr(self._target(), "encoding", None)
        return encoding if isinstance(encoding, str) else "utf-8"

    @property
    def errors(self) -> str | None:
        """No error handler of its own: unencodable text is degraded in :meth:`write`."""
        return None

    @property
    def line_buffering(self) -> bool:
        """Buffering belongs to the target."""
        return False

    @property
    def newlines(self) -> None:
        """Nothing is read, so no newline style was seen."""
        return None

    @property
    def buffer(self) -> BinaryIO:
        """There is no byte buffer: bytes would bypass the fallback."""
        raise io.UnsupportedOperation("buffer")

    @property
    def mode(self) -> str:
        """Write-only text mode."""
        return "w"

    @property
    def name(self) -> str:
        """A descriptive name; the writer is not a file."""
        return "<safe_console>"

    @property
    def closed(self) -> bool:
        """The writer never closes: the target belongs to someone else."""
        return False

    def close(self) -> None:
        """Do nothing; closing the writer must not close a stream it does not own."""

    def fileno(self) -> int:
        """Refuse, so rich treats the writer as a non-standard stream (see the class docstring)."""
        raise io.UnsupportedOperation("fileno")

    def readable(self) -> bool:
        """Write-only."""
        return False

    def writable(self) -> bool:
        """Write-only."""
        return True

    def seekable(self) -> bool:
        """Not seekable."""
        return False

    def read(self, n: int = -1, /) -> str:
        """Refuse: write-only."""
        raise io.UnsupportedOperation("read")

    def readline(self, limit: int = -1, /) -> str:
        """Refuse: write-only."""
        raise io.UnsupportedOperation("readline")

    def readlines(self, hint: int = -1, /) -> list[str]:
        """Refuse: write-only."""
        raise io.UnsupportedOperation("readlines")

    def seek(self, offset: int, whence: int = 0, /) -> int:
        """Refuse: not seekable."""
        raise io.UnsupportedOperation("seek")

    def tell(self) -> int:
        """Refuse: not seekable."""
        raise io.UnsupportedOperation("tell")

    def truncate(self, size: int | None = None, /) -> int:
        """Refuse: not seekable."""
        raise io.UnsupportedOperation("truncate")

    def __iter__(self) -> Iterator[str]:
        """Refuse: write-only."""
        raise io.UnsupportedOperation("iteration")

    def __next__(self) -> str:
        """Refuse: write-only."""
        raise io.UnsupportedOperation("iteration")

    def __enter__(self) -> TextIO:
        """Return the writer itself."""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None, /) -> None:
        """Do nothing; see :meth:`close`."""


def safe_stream(stream: TextIO | None = None) -> TextIO:
    """Wrap a stream so unencodable text degrades instead of raising.

    Use for a writer handed to a third-party renderer. For this project's own
    output use :func:`echo` instead.

    Parameters
    ----------
    stream:
        The destination text stream. Omit it (or pass None) to follow
        ``sys.stdout`` as it is at each write, which is what a module-level
        renderer needs so test harnesses can still capture the output.

    Returns
    -------
    TextIO
        A write-only text stream; see :class:`_SafeWriter` for what it refuses.
    """
    return _SafeWriter(stream)


__all__ = [
    "ASCII_FALLBACKS",
    "ascii_fallback",
    "echo",
    "encode_safe",
    "safe_stream",
]
