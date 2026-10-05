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
