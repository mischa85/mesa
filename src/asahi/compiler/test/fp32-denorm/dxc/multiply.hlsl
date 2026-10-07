ByteAddressBuffer input_data : register(t0);
RWByteAddressBuffer output_data : register(u1);
[numthreads(32,1,1)]
void main(uint3 id : SV_DispatchThreadID) {
  uint i = id.x; if (i >= 1225) return;
  uint4 u = input_data.Load4(i * 16);
  float x = asfloat(u.x), y = asfloat(u.y), z = asfloat(u.z);
  uint result = asuint(x*y);
  output_data.Store4(i * 16, uint4(u.xy, result, u.w ^ 0x6d2b79f5u));
}
