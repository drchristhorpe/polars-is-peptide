# polars-is-peptide

A [Polars](https://pola.rs) expression plugin that answers one question quickly:
**is this string a valid peptide sequence?**

A string is a peptide when every character is one of the 20 canonical amino acids —
no spaces, no ambiguity codes, no punctuation, nothing else. The check is a byte scan
in Rust, so it runs at about **25M rows/s**: roughly 9× a per-row Python regex loop
and 2× Polars' own regex engine ([benchmark](#performance)).

```python
import polars as pl
from polars_is_peptide import is_peptide

df = pl.DataFrame({"seq": ["MKWVTFISLL", "MKW VTF", "MKWVTFISLLX", "mkwvtfisll", None]})

df.with_columns(valid=is_peptide("seq"))
```

```
┌─────────────┬───────┐
│ seq         ┆ valid │
│ ---         ┆ ---   │
│ str         ┆ bool  │
╞═════════════╪═══════╡
│ MKWVTFISLL  ┆ true  │   all canonical
│ MKW VTF     ┆ false │   space
│ MKWVTFISLLX ┆ false │   X is an ambiguity code, not an amino acid
│ mkwvtfisll  ┆ false │   lowercase is opt-in
│ null        ┆ null  │   missing is unknown, not invalid
└─────────────┴───────┘
```

## Install

Not on PyPI yet — build it from source. You'll need a Rust toolchain, plus
[uv](https://docs.astral.sh/uv/); Python 3.14 and Polars come along for the ride.

```bash
git clone <this repo> && cd polars_is_peptide
uv sync            # fetches Python 3.14, builds the Rust extension, installs it
uv run pytest      # 46 tests
```

`uv sync` installs a uv-managed standalone Python 3.14 (pinned in `.python-version`)
into uv's own cache. Your system Python is not touched.

## Usage

`is_peptide` takes a column name or an expression, and returns a boolean expression.
Use it anywhere an expression goes — `select`, `with_columns`, `filter`, lazy or eager:

```python
df.filter(is_peptide("seq"))                     # keep only the valid rows
df.with_columns(valid=is_peptide(pl.col("seq"))) # flag them instead
lf.filter(is_peptide("seq")).collect()           # works lazily too
```

There is also a `.peptide` namespace, if you prefer method chaining:

```python
df.with_columns(valid=pl.col("seq").peptide.is_valid())
```

### The alphabet

By default, only these are valid — the 20 canonical amino acids, uppercase:

```
A C D E F G H I K L M N P Q R S T V W Y
```

Four keyword arguments widen that. Each is off by default and additive, so the default
behaviour can never silently start accepting something it didn't before:

| Argument | Default | Effect |
|---|---|---|
| `allow_lowercase` | `False` | Accept lowercase residues too (`"acdef"`). Useful for soft-masked FASTA. |
| `allow_ambiguous` | `False` | Additionally accept `B` (Asx), `J` (Leu/Ile), `X` (any), `Z` (Glx). |
| `allow_extended` | `False` | Additionally accept `O` (pyrrolysine) and `U` (selenocysteine). |
| `min_length` | `1` | Sequences shorter than this are invalid. `0` accepts `""`. |

```python
df.with_columns(
    strict=is_peptide("seq"),
    permissive=is_peptide("seq", allow_lowercase=True, allow_ambiguous=True),
    real_peptides=is_peptide("seq", min_length=5),
)
```

The alphabets are exported, so you don't have to retype them:

```python
from polars_is_peptide import AMINO_ACIDS, AMBIGUOUS_CODES, EXTENDED_RESIDUES
```

## Two behaviours worth knowing

**Nulls stay null.** They do not become `false`. A missing sequence is unknown, not
invalid, and the difference matters at the point you filter:

```python
df.filter(is_peptide("seq"))    # drops null rows (null is not true)
df.filter(~is_peptide("seq"))   # ALSO drops them (NOT null is null)
```

A null row falls through *both* filters. That's deliberate — you should decide what a
missing sequence means for your pipeline, rather than have the plugin quietly file it
under "invalid". If you do want nulls treated as invalid, say so explicitly:

```python
df.filter(~is_peptide("seq").fill_null(False))   # rejected, nulls included
```

**The empty string is `false`,** because a peptide has at least one residue. Pass
`min_length=0` for the vacuous-truth reading.

Non-ASCII input is rejected rather than raising: validation is a byte scan against a
256-entry table with no entry set at or above `0x80`, so no byte of a multi-byte
character can be mistaken for a residue.

## Performance

1,000,000 sequences averaging 50 residues (50.4M residues total), on this machine:

| Implementation | Time | Throughput | |
|---|---:|---:|---|
| **polars-is-peptide** | **0.039 s** | **25.6M rows/s** | |
| Polars native `str.contains` regex | 0.091 s | 11.0M rows/s | 2.3× slower |
| Python `re.match` per row | 0.341 s | 2.9M rows/s | 8.7× slower |
| Python set-membership per row | 1.366 s | 0.7M rows/s | 34.9× slower |

All four agree on all million rows. Reproduce with `uv run python tmp/demo.py`.

The speed comes from compiling the options into a `[bool; 256]` lookup table once per
call, which turns per-character validation into a single indexed load, then scanning
each row's bytes with early exit on the first invalid one. No allocation per row, and
no decoding — the table's shape is what makes the byte scan UTF-8 safe.

## Development

```bash
uv sync                      # build the Rust extension + install dev deps
uv run pytest                # test
uv run maturin develop -r    # rebuild in release mode after editing Rust
cargo check --lib            # fast Rust-only feedback loop
```

Layout: the Rust kernel is [src/alphabet.rs](src/alphabet.rs) (the lookup table) and
[src/expressions.rs](src/expressions.rs) (the Polars expression); the Python API is
[python/polars_is_peptide/__init__.py](python/polars_is_peptide/__init__.py).
[tmp/demo.py](tmp/demo.py) is a runnable walkthrough, and [PLAN.md](PLAN.md) records the
design decisions and why they went the way they did.

One pinning note, because it will bite whoever upgrades next: **`pyo3` is held at 0.28
because that's what `pyo3-polars` 0.27 links against.** Bumping `pyo3` on its own fails
the build with a `links = "python"` conflict. Bump the two together, or neither.

## Licence

MIT.
