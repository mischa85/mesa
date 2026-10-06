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

## Bit operations

Population count, bit reverse, and unsigned find-MSB accept a uniform source.
All three are reachable by normal preamble-import folding and constant
promotion. Their three emitted forms match the executed probes, including the
alternate population-count destination format used in its probe. Existing
GPR forms are preserved. Three focused tests pass, covering folding, packing,
out-of-window rejection, and ordinary integer-unary compilation.

## Float special functions

Floor, ceil, truncation, round-even, reciprocal square root, exp2 and log2 pass
uniform-source probes. A separate machine encoding describes this validated
subset and is selected by normal uniform folding. Dependency finalization and
source modifiers continue to apply. Constant promotion recognizes these seven
32-bit operations. Fourteen focused tests pass, including all seven executed
uniform byte strings and a negative reciprocal folding/packing test.

The reciprocal hypothesis fails: input 4 returns -0.125 instead of 0.25, while
the GPR control passes. It stays GPR-only. Square-root/sine factors and half
forms were not probed and also retain their existing GPR sources. Across this
session, 79 actual GPU dispatches produced 78 exact passes and this one wrong
result, with no hangs or resets. The target was released after the probes.

## Loop-weighted constant promotion

Constant-use priorities now multiply by eight per enclosing NIR loop, capped
at depth six, with saturated accumulation. This is a cost heuristic, not a
measured trip count. A lone static loop use can therefore justify a uniform
word; a lone straight-line use still does not. An end-to-end test verifies the
same literal moves from main to setup only for the loop case. Nine constant
promotion and preamble tests pass. Capture measurements below distinguish this
follow-up from the instruction-family changes.

## Uniform imports across control flow

The optimizer retains uniform-import provenance across block and execution-mask
boundaries when the program never writes the uniform window. Register-expression
CSE still ends at those boundaries. Programs containing uniform writes keep the
old local tracking and write invalidation, including possible backedges. Tests
cover both cases and preserve distinct register results across active-lane
scopes. All 188 non-compiler Apple9 tests and 23 focused compiler control-flow,
loop, preamble and promotion tests pass.
