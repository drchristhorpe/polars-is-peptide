# PLAN — `polars-is-peptide`

A Polars expression plugin (Rust core, Python API) that tests whether a string
column contains valid peptide sequences: only standard amino-acid characters,
no spaces, no other characters.

Status: **approved 2026-07-14**. Decisions D1 and D2 are settled (see below); the
stretch expression is dropped.

---

## 1. What "valid peptide" means

The canonical 20 amino acids, single-letter IUPAC codes:

```
A C D E F G H I K L M N P Q R S T V W Y
```

Explicitly **not** valid by default: `B` (Asx), `Z` (Glx), `X` (any), `J` (Leu/Ile),
`U` (selenocysteine), `O` (pyrrolysine), `*`, `-`, `.`, whitespace, digits, and
every other byte.

### Semantics table

| Input | Result | Rationale |
|---|---|---|
| `"MKWVTFISLL"` | `true` | all canonical |
| `"MKWVTFISLLX"` | `false` | `X` is an ambiguity code, not an amino acid |
| `"MKW VTF"` | `false` | space |
| `"MKW\tVTF"`, `"MKW\n"` | `false` | any whitespace, including trailing |
| `""` (empty string) | `false` | a peptide has at least one residue |
| `null` | `null` | Polars convention: nulls propagate, they are not `false` |
| `"mkwvtfisll"` | `false` | lowercase is opt-in — decision **D1** |
| `"MKWΨTF"` (non-ASCII) | `false` | handled safely at the byte level |

### Decisions (settled)

**D1 — case: strict uppercase by default.** `"acdef"` → `false` unless
`allow_lowercase=True` is passed. This matches the spec literally, and means the
plugin can never silently widen what it accepts; the escape hatch is one kwarg.

**D2 — empty string: `""` → `false`.** An empty string is not a peptide. The vacuous-truth
reading is defensible but is the wrong thing in a data-cleaning filter.

---

## 2. API

Primary form — a plain expression function:

```python
import polars as pl
from polars_is_peptide import is_peptide

df.filter(is_peptide(pl.col("sequence")))
df.with_columns(valid=is_peptide("sequence"))          # str is accepted as a column name
```

Plus a registered namespace, for people who prefer method chaining:

```python
df.with_columns(valid=pl.col("sequence").peptide.is_valid())
```

### Options (all keyword-only, all default to strict)

| kwarg | default | effect |
|---|---|---|
| `allow_lowercase` | `False` | accept `a–y` as well as `A–Y` |
| `allow_ambiguous` | `False` | additionally accept `B`, `Z`, `X`, `J` |
| `allow_extended` | `False` | additionally accept `U` (Sec), `O` (Pyl) |
| `min_length` | `1` | shorter sequences → `false` |

Defaults compose to exactly the strict rule in §1. Each flag is additive and opt-in,
so the default behaviour can never silently widen.

### Not included

`invalid_residues()` (returning the offending characters per row) was considered and
**dropped** to keep the surface area minimal. It can be added later without disturbing
`is_peptide()`.

---

## 3. Implementation

Rust core, because a byte scan in Rust over an Arrow string array avoids the
per-row Python overhead entirely.

**Validation kernel:** build a 256-entry `[bool; 256]` lookup table once per call from
the kwargs, then scan each row's bytes with early exit on the first invalid byte.
UTF-8 safety comes for free: every byte of a multi-byte character is `>= 0x80`, so
non-ASCII input can never land on a valid table entry and never needs decoding.
Complexity is O(bytes) with no allocation per row.

Null handling is Polars' default null propagation, not a special case in the kernel.

## 4. Layout

```
polars_is_peptide/
├── Cargo.toml                          # cdylib
├── pyproject.toml                      # maturin backend, requires-python >=3.14
├── .python-version                     # 3.14  (currently 3.8 — a uv init default)
├── src/
│   ├── lib.rs                          # plugin entry
│   ├── alphabet.rs                     # lookup table + kwargs struct
│   └── expressions.rs                  # #[polars_expr] fns
├── python/polars_is_peptide/
│   ├── __init__.py                     # is_peptide(), namespace registration
│   ├── _internal.abi3.so               # built artifact (gitignored)
│   └── py.typed
├── tests/test_is_peptide.py
├── tmp/                                # gitignored demo for you to inspect
├── README.md
├── CHANGELOG.md
└── PLAN.md
```

**Toolchain** (versions verified against crates.io / PyPI today, 2026-07-14):

- Python 3.14 via `uv python pin 3.14` — a uv-managed standalone build, so your
  system Python and its 3.8-era dependants are untouched.
- `pyo3-polars` 0.27 (`derive` feature), `polars` 0.54, `pyo3` 0.29, `serde` 1.0
- Build backend `maturin` 1.14; `abi3` so one wheel covers 3.14+.

## 5. Steps

1. `.gitignore` — **done** (Python + Rust + `tmp/`).
2. Repin to Python 3.14 (`.python-version`, `requires-python`); scaffold Cargo/maturin; drop the `uv init` stub `main.py`.
3. Rust: alphabet table, kwargs, `is_peptide` expression.
4. Python: `is_peptide()`, namespace, type stubs, `py.typed`.
5. `pytest` suite — the §1 semantics table case-by-case, each kwarg on and off,
   nulls, empty strings, non-ASCII, plus a property test (any string drawn from the
   alphabet validates; the same string with one bad byte injected does not).
6. `CHANGELOG.md`, then `README.md`.
7. `tmp/demo.py` + a sample CSV of realistic-and-broken sequences, run end to end,
   output left in `tmp/` for you to inspect. Includes a benchmark against the
   pure-Python/regex equivalent on ~1M rows, since speed is the reason to write
   this in Rust at all.
8. Commit.

## 6. Risks

- **pyo3-polars ↔ polars version pinning.** The classic failure mode for this
  stack: `pyo3-polars` pins its own `polars`, and a mismatch surfaces as an
  inscrutable link error. Mitigation: let Cargo resolve `polars` transitively rather
  than pinning it independently, and build early (step 3) so any mismatch shows up
  before there's much code to unpick.
- **Python 3.14 + abi3.** pyo3 0.29 supports 3.14; if the abi3 feature misbehaves I'll
  fall back to a version-specific wheel. Local-only impact — it doesn't change the API.
