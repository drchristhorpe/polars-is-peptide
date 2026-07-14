"""Tests for the is_peptide expression.

The semantics under test are the ones set out in PLAN.md §1.
"""

from __future__ import annotations

import random
import string

import polars as pl
import pytest

from polars_is_peptide import (
    AMBIGUOUS_CODES,
    AMINO_ACIDS,
    EXTENDED_RESIDUES,
    is_peptide,
)


def validate(sequences: list[str | None], **kwargs: object) -> list[bool | None]:
    """Run is_peptide over a list of sequences and return the results."""
    df = pl.DataFrame({"seq": sequences}, schema={"seq": pl.String})
    return df.select(is_peptide("seq", **kwargs)).to_series().to_list()


# --------------------------------------------------------------------------
# The core rule: only the 20 canonical amino acids, uppercase, nothing else.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        # Real sequences: serum albumin, insulin A chain, a short tag.
        ("MKWVTFISLLFLFSSAYS", True),
        ("GIVEQCCTSICSLYQLENYCN", True),
        ("YPYDVPDYA", True),
        ("M", True),
        (AMINO_ACIDS, True),
        # Whitespace of every kind.
        ("MKW VTF", False),
        ("MKWVTF ", False),
        (" MKWVTF", False),
        ("MKW\tVTF", False),
        ("MKWVTF\n", False),
        # Not amino acids, however plausible they look.
        ("MKWVTFX", False),  # X: any/unknown
        ("MKWVTFB", False),  # B: Asx
        ("MKWVTFZ", False),  # Z: Glx
        ("MKWVTFJ", False),  # J: Leu/Ile
        ("MKWVTFU", False),  # U: selenocysteine
        ("MKWVTFO", False),  # O: pyrrolysine
        # Punctuation seen in alignment and FASTA formats.
        ("MKWVTF*", False),
        ("MKW-VTF", False),
        ("MKW.VTF", False),
        ("MKWVTF1", False),
        (">sp|P02768", False),
        # Empty is not a peptide (decision D2).
        ("", False),
        # Non-ASCII: the Greek capital psi, and an emoji for good measure.
        ("MKWΨTF", False),
        ("MKW🧬TF", False),
    ],
)
def test_default_semantics(sequence: str, expected: bool) -> None:
    assert validate([sequence]) == [expected]


def test_every_canonical_residue_alone_is_valid() -> None:
    assert validate(list(AMINO_ACIDS)) == [True] * 20


def test_every_non_canonical_ascii_char_is_rejected() -> None:
    """Exhaustive: the only valid ASCII characters are the 20 amino acids."""
    rejected = [chr(i) for i in range(128) if chr(i) not in AMINO_ACIDS]
    assert validate(rejected) == [False] * len(rejected)


# --------------------------------------------------------------------------
# Nulls (decision: propagate, never collapse to false).
# --------------------------------------------------------------------------


def test_null_propagates() -> None:
    assert validate(["MKWVTF", None, "MKW VTF"]) == [True, None, False]


def test_all_null_column() -> None:
    assert validate([None, None]) == [None, None]


def test_empty_column() -> None:
    assert validate([]) == []


# --------------------------------------------------------------------------
# The opt-in flags. Each widens the alphabet and nothing else.
# --------------------------------------------------------------------------


def test_allow_lowercase() -> None:
    sequences = ["mkwvtf", "MkWvTf", "MKWVTF", "mkw vtf", "mkwvtfx"]
    assert validate(sequences, allow_lowercase=True) == [True, True, True, False, False]
    assert validate(sequences) == [False, False, True, False, False]


def test_allow_ambiguous() -> None:
    sequences = ["MKWVTFX", "MKWVTFB", "MKWVTFZ", "MKWVTFJ", "MKWVTFU"]
    # U is extended, not ambiguous, so it stays invalid.
    assert validate(sequences, allow_ambiguous=True) == [True, True, True, True, False]
    assert validate(sequences) == [False] * 5


def test_allow_extended() -> None:
    sequences = ["MKWVTFU", "MKWVTFO", "MKWVTFX"]
    # X is ambiguous, not extended, so it stays invalid.
    assert validate(sequences, allow_extended=True) == [True, True, False]


def test_flags_compose() -> None:
    sequence = "mkwvtf" + AMBIGUOUS_CODES.lower() + EXTENDED_RESIDUES.lower()
    assert validate([sequence]) == [False]
    assert validate(
        [sequence],
        allow_lowercase=True,
        allow_ambiguous=True,
        allow_extended=True,
    ) == [True]


def test_widening_flags_never_admit_whitespace() -> None:
    """No combination of flags should ever accept a space."""
    assert validate(
        ["MKW VTF"],
        allow_lowercase=True,
        allow_ambiguous=True,
        allow_extended=True,
        min_length=0,
    ) == [False]


# --------------------------------------------------------------------------
# min_length
# --------------------------------------------------------------------------


def test_min_length_filters_short_sequences() -> None:
    sequences = ["M", "MK", "MKW", "MKWV"]
    assert validate(sequences, min_length=3) == [False, False, True, True]


def test_min_length_zero_accepts_empty_string() -> None:
    assert validate(["", "MKWVTF"], min_length=0) == [True, True]


def test_min_length_does_not_relax_the_alphabet() -> None:
    assert validate(["MKW VTF"], min_length=0) == [False]


def test_negative_min_length_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_length must be non-negative"):
        is_peptide("seq", min_length=-1)


# --------------------------------------------------------------------------
# The Python surface: expression inputs, the namespace, laziness.
# --------------------------------------------------------------------------


def test_accepts_column_name_or_expression() -> None:
    df = pl.DataFrame({"seq": ["MKWVTF", "MKW VTF"]})
    from_name = df.select(is_peptide("seq")).to_series().to_list()
    from_expr = df.select(is_peptide(pl.col("seq"))).to_series().to_list()
    assert from_name == from_expr == [True, False]


def test_namespace_matches_the_function() -> None:
    df = pl.DataFrame({"seq": ["MKWVTF", "mkwvtf", "MKW VTF"]})
    via_namespace = df.select(
        pl.col("seq").peptide.is_valid(allow_lowercase=True)
    ).to_series()
    via_function = df.select(is_peptide("seq", allow_lowercase=True)).to_series()
    assert via_namespace.to_list() == via_function.to_list() == [True, True, False]


def test_output_dtype_is_boolean() -> None:
    df = pl.DataFrame({"seq": ["MKWVTF"]})
    assert df.select(is_peptide("seq")).dtypes == [pl.Boolean]


def test_works_in_a_lazy_query() -> None:
    lf = pl.LazyFrame({"seq": ["MKWVTF", "MKW VTF", None]})
    result = lf.filter(is_peptide("seq")).collect()
    assert result["seq"].to_list() == ["MKWVTF"]


def test_works_in_a_filter_and_a_with_columns() -> None:
    df = pl.DataFrame({"seq": ["MKWVTF", "MKW VTF"], "id": [1, 2]})
    assert df.filter(is_peptide("seq"))["id"].to_list() == [1]
    assert df.with_columns(ok=is_peptide("seq"))["ok"].to_list() == [True, False]


def test_survives_a_chunked_column() -> None:
    """Two chunks, one with nulls and one without, exercising both fast paths."""
    df = pl.concat(
        [
            pl.DataFrame({"seq": ["MKWVTF", "MKW VTF"]}),
            pl.DataFrame({"seq": [None, "GIVEQ"]}, schema={"seq": pl.String}),
        ],
        rechunk=False,
    )
    assert df.select(is_peptide("seq")).to_series().to_list() == [
        True,
        False,
        None,
        True,
    ]


# --------------------------------------------------------------------------
# Property tests: anything from the alphabet passes; one bad byte fails it.
# --------------------------------------------------------------------------


def test_property_random_canonical_sequences_are_valid() -> None:
    rng = random.Random(20260714)
    sequences = [
        "".join(rng.choices(AMINO_ACIDS, k=rng.randint(1, 200))) for _ in range(2000)
    ]
    assert validate(sequences) == [True] * len(sequences)


def test_property_one_bad_character_invalidates_any_sequence() -> None:
    """Take a valid sequence, splice in one non-amino-acid character anywhere."""
    rng = random.Random(20260714)
    bad_chars = [c for c in string.printable if c not in AMINO_ACIDS]

    sequences = []
    for _ in range(2000):
        valid = "".join(rng.choices(AMINO_ACIDS, k=rng.randint(1, 200)))
        position = rng.randint(0, len(valid))
        intruder = rng.choice(bad_chars)
        sequences.append(valid[:position] + intruder + valid[position:])

    assert validate(sequences) == [False] * len(sequences)
