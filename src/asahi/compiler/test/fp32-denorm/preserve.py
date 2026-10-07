#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""FP32 DenormPreserve probes with an exact oracle.

  preserve.py generate OUT        authored shaders (DenormPreserve +
                                  SignedZeroInfNanPreserve for FP32),
                                  inputs.bin and expected.json
  preserve.py check OUT RESULTS   compare probe outputs (RESULTS/<op>.txt,
                                  the `probe` tool's stdout) with the oracle

Expected values are computed exactly (fractions) and rounded to binary32 with
round-to-nearest-even and gradual underflow. FMA is accepted within one ULP
(the software path is faithfully rounded); everything else must match bit for
bit, except that any NaN matches a NaN.
"""
import json, random, struct, subprocess, sys
from fractions import Fraction
from pathlib import Path

SIGN = 0x80000000


def to_frac(bits):
    e = (bits >> 23) & 0xFF
    m = bits & 0x7FFFFF
    s = -1 if bits & SIGN else 1
    if e == 0:
        return s * Fraction(m, 1 << 149)
    return s * Fraction((1 << 23) | m, 1) * Fraction(2) ** (e - 150)


def is_nan(bits):
    return (bits & 0x7F800000) == 0x7F800000 and bits & 0x7FFFFF


def is_inf(bits):
    return (bits & 0x7FFFFFFF) == 0x7F800000


def round_f32(v, negative_zero=False):
    """Round an exact rational to binary32 bits (RNE, subnormals, overflow)."""
    if v == 0:
        return SIGN if negative_zero else 0
    sign = SIGN if v < 0 else 0
    a = abs(v)
    # Find exponent so that 2^e <= a < 2^(e+1).
    e = a.numerator.bit_length() - a.denominator.bit_length()
    if Fraction(2) ** e > a:
        e -= 1
    if Fraction(2) ** (e + 1) <= a:
        e += 1
    e = max(e, -126)
    # Quantum: 2^(e-23); significand as integer with RNE.
    q = a / Fraction(2) ** (e - 23)
    n = q.numerator // q.denominator
    r = q - n
    if r > Fraction(1, 2) or (r == Fraction(1, 2) and n & 1):
        n += 1
    if n == 1 << 24:
        n >>= 1
        e += 1
    if e > 127:
        return sign | 0x7F800000
    if n < (1 << 23):  # subnormal (e == -126)
        return sign | n
    return sign | ((e + 127) << 23) | (n & 0x7FFFFF)


def f32(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


QNAN = 0x7FC00000


def add_exact(a, b):
    if is_nan(a) or is_nan(b):
        return QNAN
    if is_inf(a) or is_inf(b):
        if is_inf(a) and is_inf(b) and (a ^ b) & SIGN:
            return QNAN
        return a if is_inf(a) else b
    v = to_frac(a) + to_frac(b)
    if v == 0:
        both_neg = (a & SIGN) and (b & SIGN)
        return round_f32(v, negative_zero=bool(both_neg))
    return round_f32(v)


def mul_exact(a, b):
    if is_nan(a) or is_nan(b):
        return QNAN
    sign = (a ^ b) & SIGN
    if is_inf(a) or is_inf(b):
        if to_frac(a) == 0 or to_frac(b) == 0:
            return QNAN
        return sign | 0x7F800000
    v = to_frac(a) * to_frac(b)
    return round_f32(v, negative_zero=bool(sign)) if v == 0 else round_f32(v)


def fma_exact(a, b, c):
    if any(is_nan(x) for x in (a, b, c)):
        return QNAN
    if is_inf(a) or is_inf(b) or is_inf(c):
        p = mul_exact(a, b)
        return add_exact(p, c) if not is_nan(p) else QNAN
    v = to_frac(a) * to_frac(b) + to_frac(c)
    if v == 0:
        psign = (a ^ b) & SIGN
        return round_f32(v, negative_zero=bool(psign and (c & SIGN)))
    return round_f32(v)


def key(bits):
    v = to_frac(bits)
    return v


def minmax(a, b, is_min):
    if is_nan(a):
        return b
    if is_nan(b):
        return a
    va, vb = to_frac(a), to_frac(b)
    if va == vb:
        if va == 0:  # min prefers -0, max +0
            neg = (a & SIGN) != 0
            return a if (neg == is_min) else b
        return a
    return a if ((va < vb) == is_min) else b


def floor_exact(a):
    if is_nan(a) or is_inf(a):
        return a
    v = to_frac(a)
    n = v.numerator // v.denominator
    return round_f32(Fraction(n), negative_zero=bool(a & SIGN) and n == 0)


OPS = {
    # name: (glsl expr, oracle(a, b, c) -> bits or ("bool", value), tolerance ulps)
    "identity": ("u.x", lambda a, b, c: a, 0),
    "negate": ("floatBitsToUint(-x)", lambda a, b, c: a ^ SIGN, 0),
    "abs": ("floatBitsToUint(abs(x))", lambda a, b, c: a & ~SIGN, 0),
    "add": ("floatBitsToUint(x+y)", lambda a, b, c: add_exact(a, b), 0),
    "sub": ("floatBitsToUint(x-y)", lambda a, b, c: add_exact(a, b ^ SIGN), 0),
    "multiply": ("floatBitsToUint(x*y)", lambda a, b, c: mul_exact(a, b), 0),
    "multiply_two": ("floatBitsToUint(x*2.0)", lambda a, b, c: mul_exact(a, 0x40000000), 0),
    "add_half": ("floatBitsToUint(x+0.5)", lambda a, b, c: add_exact(a, 0x3F000000), 0),
    "fma": ("floatBitsToUint(fma(x,y,z))", lambda a, b, c: fma_exact(a, b, c), 1),
    "min": ("floatBitsToUint(min(x,y))", lambda a, b, c: minmax(a, b, True), 0),
    "max": ("floatBitsToUint(max(x,y))", lambda a, b, c: minmax(a, b, False), 0),
    "less": ("uint(x<y)", lambda a, b, c: int(not (is_nan(a) or is_nan(b)) and to_frac(a) < to_frac(b)), 0),
    "equal": ("uint(x==y)", lambda a, b, c: int(not (is_nan(a) or is_nan(b)) and to_frac(a) == to_frac(b)), 0),
    "not_equal": ("uint(x!=y)", lambda a, b, c: int(is_nan(a) or is_nan(b) or to_frac(a) != to_frac(b)), 0),
    "sign": ("floatBitsToUint(sign(x))", lambda a, b, c: a if is_nan(a) else
             (a & SIGN) if to_frac(a) == 0 else (a & SIGN) | 0x3F800000, 0),
    "floor": ("floatBitsToUint(floor(x))", lambda a, b, c: floor_exact(a), 0),
    "ceil": ("floatBitsToUint(ceil(x))", lambda a, b, c: floor_exact(a ^ SIGN) ^ SIGN, 0),
}


def cases():
    random.seed(20261006)
    special = [0, SIGN, 1, SIGN | 1, 0x00400000, 0x807FFFFF, 0x007FFFFF, 0x00800000,
               0x80800000, 0x00800001, 0x3F800000, 0xBF800000, 0x3F000000, 0x7F800000,
               0xFF800000, 0x7FC12345, 0x7E800000, 0x7F7FFFFF, 0x0C000000, 0x34000000]
    out = []
    for a in special:
        for b in special:
            out.append((a, b, special[(a + b) % len(special)]))

    def rnd():
        r = random.random()
        if r < 0.45:
            return random.getrandbits(23) | (random.getrandbits(1) << 31)  # subnormal
        if r < 0.8:  # small normals near the boundary
            return ((random.randint(1, 40) << 23) | random.getrandbits(23) |
                    (random.getrandbits(1) << 31))
        return ((random.randint(100, 140) << 23) | random.getrandbits(23) |
                (random.getrandbits(1) << 31))
    for _ in range(600):
        out.append((rnd(), rnd(), rnd()))
    return out


def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    cs = cases()
    (out / "inputs.bin").write_bytes(b"".join(
        struct.pack("<4I", a, b, c, 0xA5010000 + i) for i, (a, b, c) in enumerate(cs)))
    expected = {}
    for name, (expr, oracle, tol) in OPS.items():
        expected[name] = dict(tol=tol, values=[oracle(a, b, c) for a, b, c in cs])
        src = f"""#version 450
layout(local_size_x=32) in;
layout(set=0,binding=0,std430) readonly buffer Input {{ uvec4 data[]; }} input_data;
layout(set=0,binding=1,std430) writeonly buffer Output {{ uvec4 data[]; }} output_data;
layout(push_constant) uniform Params {{ uint count; }} p;
void main() {{
 uint i=gl_GlobalInvocationID.x;if(i>=p.count)return;
 uvec4 u=input_data.data[i];
 precise float x=uintBitsToFloat(u.x),y=uintBitsToFloat(u.y),z=uintBitsToFloat(u.z);
 precise uint result={expr};
 output_data.data[i]=uvec4(u.xy,result,u.w^0x6d2b79f5u);
}}
"""
        comp = out / f"{name}.comp"
        comp.write_text(src)
        spv = out / f"{name}.spv"
        subprocess.run(["glslangValidator", "-V", "--target-env", "vulkan1.2", str(comp),
                        "-o", str(spv)], check=True, stdout=subprocess.DEVNULL)
        words = list(struct.unpack("<%dI" % (spv.stat().st_size // 4), spv.read_bytes()))
        i, entry, cap_end, mode_end = 5, None, None, None
        while i < len(words):
            count, op = words[i] >> 16, words[i] & 0xFFFF
            if op == 17:
                cap_end = i + count
            if op == 15:
                entry = words[i + 2]
            if op == 16:
                mode_end = i + count
            i += count
        # DenormPreserve (4459) and SignedZeroInfNanPreserve (4461) for 32 bits.
        words[mode_end:mode_end] = [4 << 16 | 16, entry, 4459, 32, 4 << 16 | 16, entry, 4461, 32]
        words[cap_end:cap_end] = [2 << 16 | 17, 4464, 2 << 16 | 17, 4466]
        spv.write_bytes(struct.pack("<%dI" % len(words), *words))
        subprocess.run(["spirv-val", "--target-env", "vulkan1.2", str(spv)], check=True)
    (out / "expected.json").write_text(json.dumps(dict(cases=cs, ops=expected)) + "\n")
    print(f"{len(OPS)} ops x {len(cs)} inputs")


def check(out, results):
    exp = json.loads((out / "expected.json").read_text())
    total_bad = 0
    for name, e in exp["ops"].items():
        path = results / f"{name}.txt"
        if not path.exists():
            print(f"{name:14} MISSING")
            total_bad += 1
            continue
        got = {}
        for line in path.read_text().splitlines():
            f = line.split()
            if len(f) == 5 and f[0].isdigit():
                got[int(f[0])] = int(f[3], 16)
        bad = []
        for i, want in enumerate(e["values"]):
            g = got.get(i)
            if g is None:
                bad.append((i, None, want)); continue
            if name in ("less", "equal", "not_equal"):
                ok = g == want
            elif is_nan(want):
                ok = is_nan(g)
            elif e["tol"]:
                ok = (g & SIGN) == (want & SIGN) and abs((g & ~SIGN) - (want & ~SIGN)) <= e["tol"]
            else:
                ok = g == want
            if not ok:
                bad.append((i, g, want))
        total_bad += len(bad)
        print(f"{name:14} {len(e['values']) - len(bad):5}/{len(e['values'])}" +
              ("" if not bad else "  e.g. " + ", ".join(
                  f"#{i} in={[hex(v) for v in exp['cases'][i]]} got={hex(g) if g is not None else None} want={hex(w)}"
                  for i, g, w in bad[:3])))
    return total_bad


if __name__ == "__main__":
    if sys.argv[1] == "generate":
        generate(Path(sys.argv[2]))
    else:
        sys.exit(1 if check(Path(sys.argv[2]), Path(sys.argv[3])) else 0)
