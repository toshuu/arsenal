<!--
@stageset version: 2
@stageset kind: IMPLEMENTATION
@stageset target: Code/batch/shared_prefix.py
@stageset source_idea: IDEA-0004
@stageset status: SUPERSEDED
@stageset priority: P1
@stageset spec_revision: 1
@stageset implemented_revision: 0
@stageset planned_in: .stageset/sessions/coding-ssld-016-t4.md
@stageset last_updated_in: .stageset/sessions/coding-ssld-016-t4.md
@stageset implemented_in: -
@stageset blocker_ref: -
@stageset resolution_of: -
-->

# Implementation: shared voice-prefix KV

## Purpose

Store one conditioned voice-prefix KV block for the whole batch instead of one
clone per row. Cut state memory and the per-row copy work.

This is SSLD-016 step 3. Build it only if the memory profile shows that the
voice state is one of the largest items.

## Contract

- `share_voice_state(voice_state, batch_size)`:
  - Return a state dict where the prefix slice points at the same storage for
    every row.
  - Do not break the per-row attention offset and pad values.
  - Keep the per-row text suffix separate.
- The stream must read the shared block and never write to it.
- When a row is removed, slice only the per-row part.

## Edge cases

- A write into a shared row would corrupt every row. Test with two rows of
  different lengths.
- The conditioned profile path and the normal path must agree on the layout.
- Do not build this if the profile shows the voice state is small.

## Checks

### CHECK-PREFIX-01 - parity

- Command: `python Code/probes/check_shared_prefix.py`
- Predicted output: `CHECK_SHARED_PREFIX PASS`
- Pass condition: maximum row difference is below 1e-3 against the clone path.
- Fail condition: any row differs or the command exits non-zero.

## References

- `LivingDocs/SSLD-016-single-t4.md`
