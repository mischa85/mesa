# T8132 uniform-source probes, October 5

Paired GPR/uniform probes execute in an isolated native Vulkan driver. A setup
program writes known values to u240..u243; the main program injects one tested
operation into a normal SSBO shader. The original varying result supplies the
comparison inputs. Each dispatch checks all 256 outputs exactly. Comparisons
exercise both outcomes; equality has one matching lane. No proprietary binary
was inspected. The public M3 decoder supplies field-layout hypotheses, checked
against independently generated T8132 GPR controls and CPU result oracles.

Local complete cases, output words, diagnostics and control bytes are under
`tmp/uniform-source-probes/`. The diagnostic compiler overlay lives outside the
production source. A compiler assertion in the first harness build was fixed
before GPU submission; it is not a hardware failure. No probes hung the GPU.

## Selects

All four 32-bit source slots pass for integer and floating comparisons. Extended
absolute-value comparisons pass in both comparison slots. A simultaneous
four-uniform case reads distinct values from u240..u243 and passes. Each case
has a matching GPR control. The short and extended select forms now admit
uniform words through u255 and retain a compact list of actual GPR inputs.
Uniform operand 3 is included in expression identity. Boolean NIR selects can
promote their scalar 32-bit selected values; their boolean condition is excluded.

Uniform selectors are bits 55, 57, 37 and 69. The low six word-index bits retain
the GPR field positions; word-index bit 6 uses the source discard field and bit
7 uses the high field. The cache/immediate selector is clear. GPR lifetimes are
unchanged. The four-uniform emitted bytes have a regression test against the
executed probe. Additional tests cover elimination of uniform GPR uses, u255,
out-of-range rejection, and source-3 expression identity.

Host checks: 242 tests outside Apple9Compiler before the byte regression was
added, nine focused compiler tests, and nine select-focused optimization/packer
tests including the emitted-byte regression. The whole-capture comparison will
measure all validated families against `49e1b658f99`.

## Predicate comparisons

Both source slots pass in the six-byte less-than and ten-byte equality
predicate forms. The oracle checks the resulting execution-mask selection,
including one matching equality lane. Short-form uniform selectors are bits
39/41; the extended form uses 55/57. Word-index high bits replace the same
source lifetime fields as in select. Loop-specific and half predicate forms
remain unchanged because they were not part of this validation.

Predicates have no SSA result, so uniform folding explicitly handles them
without treating the instruction as a CSE-able pure ALU. Scalar 32-bit NIR
comparison inputs can be promoted even though the comparison result is boolean.
The boolean result itself never becomes a 32-bit preamble load. Tests check
both executed byte encodings and folding of a destination-less predicate.
Twenty-four existing predicate/shared-RA/control-flow tests and three focused
predicate tests pass.

## Shifts

Arithmetic right, logical right, and logical left pass with a uniform data
operand for both immediate and register shift forms; their register-amount
source also passes. These nine paired cases check negative arithmetic shifts,
distinct full-word data, and varying per-lane data for uniform amounts.
The fixed-source register selector is cleared and its discard field is set
for uniforms; the source cache bit holds uniform word bit 7. The immediate
amount encoding stays immediate. Source compaction cannot change a register
shift into an immediate shift: the encoding now determines that distinction.

The nine executed uniform instruction byte strings have a packer regression.
A folding test checks that a uniform amount preserves the register form.
Eight shift-focused packer, optimization, and compiler tests pass.

## Integer/float conversions

Signed and unsigned 32-bit integer-to-float and float-to-integer sources pass
paired probes. The former checks ±12345; the latter checks truncation of
±123.75. Uniform folding removes the import from the GPR source list. Machine
constraints admit words through u255, and ordinary NIR constant promotion
recognizes all four conversions. The emitted bytes match each executed uniform
probe; out-of-window sources are rejected. Seven conversion-focused tests pass.
