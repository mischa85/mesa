#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate tiny authored shaders and exact-bit input controls; no corpus copy."""
import argparse,json,struct,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
cases=[]
def add(name,a,b=0,c=0):cases.append(dict(name=name,words=[a,b,c,0xa5010000+len(cases)]))
for name,bits in [('pzero',0),('nzero',0x80000000),('pminsub',1),('nminsub',0x80000001),('pmidsub',0x00400000),('nmidsub',0x80400000),('pmaxsub',0x007fffff),('nmaxsub',0x807fffff),('pminnorm',0x00800000),('nminnorm',0x80800000),('one',0x3f800000),('negative_one',0xbf800000),('half',0x3f000000),('one_and_half',0x3fc00000),('two_and_half',0x40200000),('infinity',0x7f800000),('negative_infinity',0xff800000),('qnan',0x7fc12345)]:
 add(name,bits)
 add(name+'_one',bits,0x3f800000)
add('normal_add_to_subnormal',0x00800001,0x80800000)
add('normal_add_to_negative_subnormal',0x80800001,0x00800000)
add('add_input_daz',0x00800000,0x807fffff)
add('add_input_daz_reverse',0x807fffff,0x00800000)
add('subnormal_sum_to_normal',0x007fffff,0x007fffff)
add('mul_input_to_normal',1,0x7e800000)
add('mul_negative_input_to_normal',0x80000001,0x7e800000)
add('mul_normal_to_subnormal',0x00800000,0x3f000000)
add('mul_negative_normal_to_subnormal',0x80800000,0x3f000000)
add('fma_input_to_normal',1,0x7e800000,0x3f800000)
add('fma_addend_daz',0x00800000,0x3f800000,0x807fffff)
add('fma_cancellation_to_subnormal',0x00800001,0x3f800000,0x80800000)
add('fma_underflow_product_normal_result',0x00800000,0x3f000000,0x00800000)
add('p_sub_n_sub',1,0x80000001)
add('n_sub_p_sub',0x80000001,1)
add('unequal_subnormals',0x00400000,1)
add('unequal_subnormals_reverse',1,0x00400000)
add('normal_control',0x3fc00000,0x40200000,0x3f000000)
add('negative_control',0xbfc00000,0x40200000,0x3f000000)
add('reciprocal_to_subnormal',0x7f000000)
add('exp2_to_subnormal',0xc2fe0000) # -127
add('exp2_min_subnormal',0xc3150000) # -149
add('half_min_subnormal_output',0x33800000) # 2^-24
add('half_max_subnormal_output',0x387fc000)
add('half_min_normal_output',0x38800000)
add('half_max_finite_output',0x477fe000)
add('half_min_subnormal_input',1)
add('half_max_subnormal_input',0x03ff)
add('half_min_normal_input',0x0400)
add('half_negative_subnormal_input',0x8001)
(a.output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
(a.output/'inputs.bin').write_bytes(b''.join(struct.pack('<4I',*c['words']) for c in cases))
ops={
 'identity':'u.x','negate':'floatBitsToUint(-x)','abs':'floatBitsToUint(abs(x))',
 'add':'floatBitsToUint(x+y)','multiply':'floatBitsToUint(x*y)',
 'fma':'floatBitsToUint(fma(x,y,z))','add_abs':'floatBitsToUint(abs(x)+y)',
 'multiply_abs':'floatBitsToUint(abs(x)*y)','fma_abs':'floatBitsToUint(fma(abs(x),y,z))',
 'multiply_two':'floatBitsToUint(x*2.0)','add_half':'floatBitsToUint(x+0.5)',
 'min':'floatBitsToUint(min(x,y))','max':'floatBitsToUint(max(x,y))',
 'less':'uint(x<y)','equal':'uint(x==y)','not_equal':'uint(x!=y)',
 'sign':'floatBitsToUint(sign(x))','floor':'floatBitsToUint(floor(x))',
 'ceil':'floatBitsToUint(ceil(x))','trunc':'floatBitsToUint(trunc(x))',
 'round_even':'floatBitsToUint(roundEven(x))','fract':'floatBitsToUint(fract(x))',
 'exp2':'floatBitsToUint(exp2(x))','log2':'floatBitsToUint(log2(x))',
 'sqrt':'floatBitsToUint(sqrt(x))','inverse_sqrt':'floatBitsToUint(inversesqrt(x))',
 'reciprocal':'floatBitsToUint(1.0/x)','sin':'floatBitsToUint(sin(x))','cos':'floatBitsToUint(cos(x))',
 'f32_to_half':'packHalf2x16(vec2(x,0.0))','half_to_f32':'floatBitsToUint(unpackHalf2x16(u.x).x)',
 'f32_to_i32':'uint(int(x))','f32_to_u32':'uint(x)',
 'i32_to_f32':'floatBitsToUint(float(int(u.x)))','u32_to_f32':'floatBitsToUint(float(u.x))',
}
for name,expr in ops.items():
 source='''#version 450
layout(local_size_x=32) in;
layout(set=0,binding=0,std430) readonly buffer Input { uvec4 data[]; } input_data;
layout(set=0,binding=1,std430) writeonly buffer Output { uvec4 data[]; } output_data;
layout(push_constant) uniform Params { uint count; } p;
void main() {
 uint i=gl_GlobalInvocationID.x;if(i>=p.count)return;
 uvec4 u=input_data.data[i];
 precise float x=uintBitsToFloat(u.x),y=uintBitsToFloat(u.y),z=uintBitsToFloat(u.z);
 precise uint result=EXPR;
 output_data.data[i]=uvec4(u.xy,result,u.w^0x6d2b79f5u);
}
'''.replace('EXPR',expr)
 path=a.output/(name+'.comp');path.write_text(source)
 subprocess.run(['glslangValidator','-V','--target-env','vulkan1.2',str(path),'-o',str(a.output/(name+'.spv'))],check=True,stdout=subprocess.DEVNULL)
(a.output/'operations.json').write_text(json.dumps(ops,indent=2)+'\n')
print(f'{len(ops)} operations x {len(cases)} inputs; integer transport/tag controls in each output')
