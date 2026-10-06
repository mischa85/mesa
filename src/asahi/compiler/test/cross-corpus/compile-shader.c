/* SPDX-License-Identifier: MIT
 * CPU-only shader-object compilation. Requires the external host DRM shim.
 * Does not create a queue, command buffer, submission, or draw.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <vulkan/vulkan.h>
#define CHECK(x) do {VkResult r=(x);if(r){fprintf(stderr,"CORPUS_ERROR %s %d\n",#x,r);return 1;}}while(0)
static int compile(VkDevice d, PFN_vkCreateShadersEXT create,
                   PFN_vkDestroyShaderEXT destroy, const char *path) {
 FILE *f=fopen(path,"r");if(!f)return 2;
 char binary[4096],entry[256];unsigned stage,push,n;
 if(fscanf(f,"%4095s %u %255s %u %u",binary,&stage,entry,&push,&n)!=5){fclose(f);return 2;}
 VkDescriptorSetLayoutBinding bindings[16][128]={0};unsigned counts[16]={0},sets=0;
 for(unsigned j=0;j<n;j++) {
  unsigned s,b,t,c;
  if(fscanf(f,"%u %u %u %u",&s,&b,&t,&c)!=4||s>=16||counts[s]>=128){fclose(f);return 2;}
  bindings[s][counts[s]++]=(VkDescriptorSetLayoutBinding){.binding=b,.descriptorType=t,.descriptorCount=c,.stageFlags=stage};
  if(sets<=s)sets=s+1;
 }
 fclose(f);VkDescriptorSetLayout layouts[16]={0};
 for(unsigned i=0;i<sets;i++) CHECK(vkCreateDescriptorSetLayout(d,&(VkDescriptorSetLayoutCreateInfo){.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,.bindingCount=counts[i],.pBindings=bindings[i]},0,&layouts[i]));
 f=fopen(binary,"rb");if(!f)return 2;fseek(f,0,SEEK_END);size_t size=ftell(f);rewind(f);void *code=malloc(size);
 if(!code||fread(code,1,size,f)!=size){fclose(f);return 2;}fclose(f);
 VkPushConstantRange range={.stageFlags=stage,.size=push};VkShaderEXT shader=0;
 VkShaderCreateInfoEXT info={.sType=VK_STRUCTURE_TYPE_SHADER_CREATE_INFO_EXT,.stage=stage,.nextStage=stage==VK_SHADER_STAGE_VERTEX_BIT?VK_SHADER_STAGE_FRAGMENT_BIT:0,.codeType=VK_SHADER_CODE_TYPE_SPIRV_EXT,.codeSize=size,.pCode=code,.pName=entry,.setLayoutCount=sets,.pSetLayouts=layouts,.pushConstantRangeCount=push?1:0,.pPushConstantRanges=&range};
 struct timespec a,b;clock_gettime(CLOCK_THREAD_CPUTIME_ID,&a);VkResult result=create(d,1,&info,0,&shader);clock_gettime(CLOCK_THREAD_CPUTIME_ID,&b);
 fprintf(stderr,"CORPUS_CREATE result=%d cpu_ns=%llu\n",result,(unsigned long long)((b.tv_sec-a.tv_sec)*1000000000ll+b.tv_nsec-a.tv_nsec));
 if(shader) destroy(d,shader,0);
 free(code);
 for(unsigned i=0;i<sets;i++) vkDestroyDescriptorSetLayout(d,layouts[i],0);
 return result==VK_SUCCESS?0:1;
}
int main(int argc,char **argv) {
 if(!getenv("LD_PRELOAD")||!getenv("VK_DRIVER_FILES")){fputs("explicit host shim and ICD required\n",stderr);return 2;}
 VkInstance i;CHECK(vkCreateInstance(&(VkInstanceCreateInfo){.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&(VkApplicationInfo){.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.apiVersion=VK_API_VERSION_1_3}},0,&i));
 uint32_t count=1;VkPhysicalDevice p;CHECK(vkEnumeratePhysicalDevices(i,&count,&p));
 VkPhysicalDeviceProperties props;vkGetPhysicalDeviceProperties(p,&props);fprintf(stderr,"CORPUS_DEVICE %s driver=%u\n",props.deviceName,props.driverVersion);
 if(!strstr(props.deviceName,"Apple M4")){fputs("unexpected device\n",stderr);return 2;}
 VkPhysicalDeviceVulkan13Features f13={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
 VkPhysicalDeviceVulkan12Features f12={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES,.pNext=&f13};
 VkPhysicalDeviceVulkan11Features f11={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES,.pNext=&f12};
 VkPhysicalDeviceFeatures2 f2={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,.pNext=&f11};vkGetPhysicalDeviceFeatures2(p,&f2);
 VkPhysicalDeviceShaderObjectFeaturesEXT so={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_OBJECT_FEATURES_EXT,.shaderObject=VK_TRUE,.pNext=&f2};
 const char *ext="VK_EXT_shader_object";float priority=1;VkDevice d;
 CHECK(vkCreateDevice(p,&(VkDeviceCreateInfo){.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.pNext=&so,.queueCreateInfoCount=1,.pQueueCreateInfos=&(VkDeviceQueueCreateInfo){.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueCount=1,.pQueuePriorities=&priority},.enabledExtensionCount=1,.ppEnabledExtensionNames=&ext},0,&d));
 PFN_vkCreateShadersEXT create=(PFN_vkCreateShadersEXT)vkGetDeviceProcAddr(d,"vkCreateShadersEXT");PFN_vkDestroyShaderEXT destroy=(PFN_vkDestroyShaderEXT)vkGetDeviceProcAddr(d,"vkDestroyShaderEXT");if(!create||!destroy)return 2;
 char *line=NULL;size_t cap=0;while(getline(&line,&cap,stdin)>0){line[strcspn(line,"\r\n")]=0;fprintf(stderr,"CORPUS_BEGIN %s\n",line);fflush(stderr);int r=compile(d,create,destroy,line);fprintf(stderr,"CORPUS_END %d\n",r);fflush(stderr);}
 free(line);vkDestroyDevice(d,0);vkDestroyInstance(i,0);return 0;
}
