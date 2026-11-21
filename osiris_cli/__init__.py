"""OSIRIS-CLI QEC v1.1.0 command and provenance-ledger package."""

from .ledger import (
    GENESIS_PREV_SHA256,
    LedgerError,
    append_ledger,
    canonical_json,
    canonicalize,
    compute_wilson_lower_bound,
    create_completed_entry,
    create_pre_submit_entry,
    read_ledger,
    sha256_hex,
    verify_ledger_file,
)
from .qnexus_client import (
    EXPECTED_ISA,
    EXPECTED_PRECOMPILE,
    QNEXUS_VERSION,
    HashMismatchError,
    ManifestError,
    QNexusAPIError,
    with_qnexus_retries,
)

__all__ = [
    "EXPECTED_PRECOMPILE",
    "EXPECTED_ISA",
    "QNEXUS_VERSION",
    "GENESIS_PREV_SHA256",
    "HashMismatchError",
    "ManifestError",
    "LedgerError",
    "QNexusAPIError",
    "canonical_json",
    "canonicalize",
    "sha256_hex",
    "compute_wilson_lower_bound",
    "create_pre_submit_entry",
    "create_completed_entry",
    "append_ledger",
    "read_ledger",
    "verify_ledger_file",
    "with_qnexus_retries",
]
