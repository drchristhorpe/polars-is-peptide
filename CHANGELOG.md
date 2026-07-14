# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-14

First release. A Polars expression plugin, Rust core, that validates peptide sequences.

### Added

- **`is_peptide(expr)`** — an elementwise boolean expression. A string is a valid
  peptide when every character is one of the 20 canonical amino acids
  (`ACDEFGHIKLMNPQRSTVWY`): no spaces, no ambiguity codes, no punctuation, nothing else.
  Accepts either a column name or an expression.
- **`.peptide.is_valid()`** — the same thing as an expression namespace, for
  method-chaining style.
- **Opt-in alphabet flags**, all defaulting to off, so the default can never silently
  widen what it accepts:
  - `allow_lowercase` — accept lowercase residues as well as uppercase.
  - `allow_ambiguous` — additionally accept `B` (Asx), `J` (Leu/Ile), `X` (any), `Z` (Glx).
  - `allow_extended` — additionally accept `O` (pyrrolysine) and `U` (selenocysteine).
  - `min_length` (default `1`) — sequences shorter than this are invalid.
- **`AMINO_ACIDS`, `AMBIGUOUS_CODES`, `EXTENDED_RESIDUES`** — the alphabets, exported
  so callers can reuse them rather than retyping them.
- Type hints throughout, and a `py.typed` marker.

### Behaviour worth knowing

- **Nulls propagate as null**, and do not collapse to `false`. A missing sequence is
  unknown, not invalid — so `filter(is_peptide(...))` drops null rows, while
  `with_columns(valid=is_peptide(...))` keeps them visible as null.
- **The empty string is `false`** under the default `min_length=1`. Pass `min_length=0`
  if you want the vacuous-truth reading.
- **Non-ASCII input is rejected** rather than raising. Validation is a byte scan against
  a 256-entry table, and no entry at or above `0x80` is ever set, so no byte of a
  multi-byte character can be mistaken for a residue.

### Implementation notes

- The kwargs are compiled into a `[bool; 256]` lookup table once per expression call,
  which turns per-character validation into a single indexed load. Scanning is O(bytes)
  with early exit on the first invalid byte and no per-row allocation.
- Null handling uses Polars' `apply_nonnull_values_generic`, which preserves the null
  mask and takes a branch-free fast path over chunks containing no nulls.

### Toolchain

- Python 3.14 (pinned via `uv python pin`), Polars ≥ 1.42.
- Rust: `pyo3-polars` 0.27, `pyo3` 0.28, `polars` 0.54, built with `maturin` 1.14.
- `pyo3` is held at 0.28 deliberately: it is the version `pyo3-polars` 0.27 links
  against, and bumping it independently fails the build with a `links = "python"`
  conflict. Bump the two together or not at all.
