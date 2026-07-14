"""Validate peptide sequences in a Polars DataFrame.

A sequence is a peptide when every character is a standard amino acid — no
spaces, no ambiguity codes, no punctuation, nothing else:

    >>> import polars as pl
    >>> from polars_is_peptide import is_peptide
    >>> df = pl.DataFrame({"seq": ["MKWVTFISLL", "MKW VTF", "MKWVTFISLLX"]})
    >>> df.with_columns(valid=is_peptide("seq"))
    shape: (3, 2)
    ┌─────────────┬───────┐
    │ seq         ┆ valid │
    ╞═════════════╪═══════╡
    │ MKWVTFISLL  ┆ true  │
    │ MKW VTF     ┆ false │
    │ MKWVTFISLLX ┆ false │
    └─────────────┴───────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

if TYPE_CHECKING:
    from polars._typing import IntoExpr

__all__ = [
    "AMBIGUOUS_CODES",
    "AMINO_ACIDS",
    "EXTENDED_RESIDUES",
    "PeptideNamespace",
    "is_peptide",
]

_PLUGIN_PATH = Path(__file__).parent

#: The 20 canonical amino acids, IUPAC single-letter codes.
AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"

#: Ambiguity codes: Asx, Leu/Ile, any, Glx. Accepted only with allow_ambiguous.
AMBIGUOUS_CODES = "BJXZ"

#: Pyrrolysine and selenocysteine. Accepted only with allow_extended.
EXTENDED_RESIDUES = "OU"


def is_peptide(
    expr: IntoExpr,
    *,
    allow_lowercase: bool = False,
    allow_ambiguous: bool = False,
    allow_extended: bool = False,
    min_length: int = 1,
) -> pl.Expr:
    """Return a boolean expression: is each string a valid peptide sequence?

    By default only the 20 canonical amino acids in uppercase are accepted. Every
    option below widens that alphabet, and each must be asked for explicitly, so
    the default can never silently accept something it shouldn't.

    Null values stay null — a missing sequence is unknown, not invalid. Empty
    strings are ``False`` under the default ``min_length=1``.

    Args:
        expr: The string column to validate, as an expression or a column name.
        allow_lowercase: Also accept lowercase residues (``"acdef"``).
        allow_ambiguous: Also accept the ambiguity codes ``BJXZ``.
        allow_extended: Also accept pyrrolysine (``O``) and selenocysteine (``U``).
        min_length: Sequences shorter than this are invalid. ``0`` accepts ``""``.

    Returns:
        A boolean expression, elementwise over the input.

    Raises:
        ValueError: If ``min_length`` is negative.
    """
    if min_length < 0:
        msg = f"min_length must be non-negative, got {min_length}"
        raise ValueError(msg)

    return register_plugin_function(
        plugin_path=_PLUGIN_PATH,
        function_name="is_peptide",
        args=expr,
        kwargs={
            "allow_lowercase": allow_lowercase,
            "allow_ambiguous": allow_ambiguous,
            "allow_extended": allow_extended,
            "min_length": min_length,
        },
        is_elementwise=True,
    )


@pl.api.register_expr_namespace("peptide")
class PeptideNamespace:
    """The ``.peptide`` expression namespace, for method-chaining style.

    ``pl.col("seq").peptide.is_valid()`` is exactly ``is_peptide(pl.col("seq"))``.
    """

    def __init__(self, expr: pl.Expr) -> None:
        self._expr = expr

    def is_valid(
        self,
        *,
        allow_lowercase: bool = False,
        allow_ambiguous: bool = False,
        allow_extended: bool = False,
        min_length: int = 1,
    ) -> pl.Expr:
        """See :func:`is_peptide`."""
        return is_peptide(
            self._expr,
            allow_lowercase=allow_lowercase,
            allow_ambiguous=allow_ambiguous,
            allow_extended=allow_extended,
            min_length=min_length,
        )
