//! The amino-acid alphabet, compiled into a byte lookup table.

use serde::Deserialize;

/// The 20 canonical amino acids, IUPAC single-letter codes.
pub const CANONICAL: &[u8] = b"ACDEFGHIKLMNPQRSTVWY";

/// Ambiguity codes: Asx, Leu/Ile, any, Glx. Opt-in.
pub const AMBIGUOUS: &[u8] = b"BJXZ";

/// The 21st and 22nd proteinogenic residues: pyrrolysine, selenocysteine. Opt-in.
pub const EXTENDED: &[u8] = b"OU";

/// Options controlling which characters count as valid. Deserialised straight
/// from the kwargs dict handed over by the Python side.
#[derive(Deserialize)]
pub struct IsPeptideKwargs {
    pub allow_lowercase: bool,
    pub allow_ambiguous: bool,
    pub allow_extended: bool,
    pub min_length: usize,
}

/// A 256-entry table mapping every possible byte to valid/invalid.
///
/// Building this once per expression call turns per-character validation into a
/// single indexed load. It is also what makes the scan UTF-8 safe without any
/// decoding: every byte of a multi-byte character is >= 0x80, and no entry that
/// high is ever set, so non-ASCII input can never be mistaken for a residue.
pub fn build_table(kwargs: &IsPeptideKwargs) -> [bool; 256] {
    let mut table = [false; 256];

    let mut groups: Vec<&[u8]> = vec![CANONICAL];
    if kwargs.allow_ambiguous {
        groups.push(AMBIGUOUS);
    }
    if kwargs.allow_extended {
        groups.push(EXTENDED);
    }

    for group in groups {
        for &byte in group {
            table[byte as usize] = true;
            if kwargs.allow_lowercase {
                table[byte.to_ascii_lowercase() as usize] = true;
            }
        }
    }

    table
}

/// Is `sequence` a peptide under this table and minimum length?
///
/// Comparing `len()` in bytes rather than characters is sound here: any sequence
/// containing a multi-byte character is rejected by the table anyway, so the two
/// only ever differ on strings that are already invalid.
#[inline]
pub fn is_valid(sequence: &str, table: &[bool; 256], min_length: usize) -> bool {
    let bytes = sequence.as_bytes();
    bytes.len() >= min_length && bytes.iter().all(|&byte| table[byte as usize])
}
