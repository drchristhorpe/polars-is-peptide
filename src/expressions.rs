//! The Polars expressions exposed to Python.

use polars::prelude::*;
use pyo3_polars::derive::polars_expr;

use crate::alphabet::{build_table, is_valid, IsPeptideKwargs};

/// Elementwise: is each string a valid peptide sequence?
///
/// Nulls propagate as null rather than collapsing to false — a missing sequence
/// is unknown, not invalid.
#[polars_expr(output_type=Boolean)]
fn is_peptide(inputs: &[Series], kwargs: IsPeptideKwargs) -> PolarsResult<Series> {
    let sequences = inputs[0].str()?;

    let table = build_table(&kwargs);
    let min_length = kwargs.min_length;

    // apply_nonnull_values_generic keeps the null mask intact and takes a
    // branch-free fast path over chunks that have no nulls at all.
    let out: BooleanChunked = sequences
        .apply_nonnull_values_generic(DataType::Boolean, |sequence: &str| {
            is_valid(sequence, &table, min_length)
        });

    Ok(out.into_series())
}
