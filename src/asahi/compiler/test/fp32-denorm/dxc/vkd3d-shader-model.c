#define COBJMACROS
#define INITGUID
#include <stdio.h>
#define COM_NO_WINDOWS_H
#include "vkd3d_windows.h"
#include "vkd3d_d3d12.h"
int main(void)
{
   ID3D12Device *dev;
   HRESULT hr = D3D12CreateDevice(NULL, D3D_FEATURE_LEVEL_11_0, &IID_ID3D12Device, (void **)&dev);
   if (FAILED(hr)) { printf("D3D12CreateDevice failed %#x\n", (unsigned)hr); return 1; }
   D3D12_FEATURE_DATA_SHADER_MODEL sm = { D3D_SHADER_MODEL_6_8 };
   hr = ID3D12Device_CheckFeatureSupport(dev, D3D12_FEATURE_SHADER_MODEL, &sm, sizeof(sm));
   printf("HighestShaderModel %#x (hr %#x)\n", sm.HighestShaderModel, (unsigned)hr);
   D3D12_FEATURE_DATA_D3D12_OPTIONS o = {0};
   ID3D12Device_CheckFeatureSupport(dev, D3D12_FEATURE_D3D12_OPTIONS, &o, sizeof(o));
   printf("MinPrecision %#x\n", o.MinPrecisionSupport);
   ID3D12Device_Release(dev);
   return 0;
}
