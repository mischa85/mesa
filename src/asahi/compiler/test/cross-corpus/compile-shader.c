/* SPDX-License-Identifier: MIT
 * CPU-only shader-object compilation. Requires the external host DRM shim.
 * Does not create a queue, command buffer, submission, or draw.
 */
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <vulkan/vulkan.h>
#define CHECK(x) do {VkResult r=(x);if(r){fprintf(stderr,"CORPUS_ERROR %s %d\n",#x,r);return 1;}}while(0)
static VKAPI_ATTR VkBool32 VKAPI_CALL diagnostic(
 VkDebugUtilsMessageSeverityFlagBitsEXT severity,
 VkDebugUtilsMessageTypeFlagsEXT type,
 const VkDebugUtilsMessengerCallbackDataEXT *data, void *user) {
 (void)severity; (void)type; (void)user;
 fprintf(stderr,"CORPUS_VK_DIAGNOSTIC %s\n",data->pMessage);
 return VK_FALSE;
}
static int compile(VkDevice d, PFN_vkCreateShadersEXT create,
                   PFN_vkDestroyShaderEXT destroy, const char *header) {
 FILE *f=stdin;
 char key[256],entry[256];unsigned stage,push,n;size_t size;
 if(sscanf(header,"%255s %u %255s %u %u %zu",key,&stage,entry,&push,&n,&size)!=6)return 2;
 if(size>256*1024*1024 || (size&3))return 2;
 VkDescriptorSetLayoutBinding *bindings[8]={0};unsigned counts[8]={0},sets=0;
 if(n>100000){return 2;}
 for(unsigned j=0;j<n;j++) {
  unsigned s,b,t,c;
  char line[256];
  if(!fgets(line,sizeof(line),f)||sscanf(line,"%u %u %u %u",&s,&b,&t,&c)!=4||s>=8)return 2;
  if(!bindings[s]) bindings[s]=calloc(n,sizeof(*bindings[s]));
  if(!bindings[s]){return 2;}
  bindings[s][counts[s]++]=(VkDescriptorSetLayoutBinding){.binding=b,.descriptorType=t,.descriptorCount=c,.stageFlags=stage};
  if(sets<=s)sets=s+1;
 }
 void *code=malloc(size);
 if(!code||fread(code,1,size,f)!=size)return 2;
 VkDescriptorSetLayout layouts[8]={0};
 for(unsigned i=0;i<sets;i++) CHECK(vkCreateDescriptorSetLayout(d,&(VkDescriptorSetLayoutCreateInfo){.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,.bindingCount=counts[i],.pBindings=bindings[i]},0,&layouts[i]));
 VkPushConstantRange range={.stageFlags=stage,.size=push};VkShaderEXT shader=0;
 VkShaderCreateInfoEXT info={.sType=VK_STRUCTURE_TYPE_SHADER_CREATE_INFO_EXT,.stage=stage,.nextStage=stage==VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT?VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT:((stage&(VK_SHADER_STAGE_VERTEX_BIT|VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT|VK_SHADER_STAGE_GEOMETRY_BIT))?VK_SHADER_STAGE_FRAGMENT_BIT:0),.codeType=VK_SHADER_CODE_TYPE_SPIRV_EXT,.codeSize=size,.pCode=code,.pName=entry,.setLayoutCount=sets,.pSetLayouts=layouts,.pushConstantRangeCount=push?1:0,.pPushConstantRanges=&range};
 struct timespec a,b;clock_gettime(CLOCK_THREAD_CPUTIME_ID,&a);VkResult result=create(d,1,&info,0,&shader);clock_gettime(CLOCK_THREAD_CPUTIME_ID,&b);
 fprintf(stderr,"CORPUS_CREATE result=%d cpu_ns=%llu\n",result,(unsigned long long)((b.tv_sec-a.tv_sec)*1000000000ll+b.tv_nsec-a.tv_nsec));
 if(shader) destroy(d,shader,0);
 free(code);
 for(unsigned i=0;i<sets;i++){vkDestroyDescriptorSetLayout(d,layouts[i],0);free(bindings[i]);}
 return result==VK_SUCCESS?0:1;
}
int main(int argc,char **argv) {
 if(!getenv("LD_PRELOAD")||!getenv("VK_DRIVER_FILES")){fputs("explicit host shim and ICD required\n",stderr);return 2;}
 bool diagnostics=getenv("CORPUS_DIAGNOSTICS")!=NULL;
 const char *debug_ext="VK_EXT_debug_utils";
 VkDebugUtilsMessengerCreateInfoEXT debug={.sType=VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT,.messageSeverity=VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT|VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT,.messageType=VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT|VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT|VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT,.pfnUserCallback=diagnostic};
 VkInstance i;CHECK(vkCreateInstance(&(VkInstanceCreateInfo){.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pNext=diagnostics?&debug:NULL,.enabledExtensionCount=diagnostics?1:0,.ppEnabledExtensionNames=&debug_ext,.pApplicationInfo=&(VkApplicationInfo){.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.apiVersion=VK_API_VERSION_1_3}},0,&i));
 VkDebugUtilsMessengerEXT messenger=VK_NULL_HANDLE;
 if(diagnostics) {
  PFN_vkCreateDebugUtilsMessengerEXT create_debug=(PFN_vkCreateDebugUtilsMessengerEXT)vkGetInstanceProcAddr(i,"vkCreateDebugUtilsMessengerEXT");
  CHECK(create_debug(i,&debug,NULL,&messenger));
 }
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
 char *line=NULL;size_t cap=0;while(getline(&line,&cap,stdin)>0){line[strcspn(line,"\r\n")]=0;char key[256];if(sscanf(line,"%255s",key)!=1)return 2;fprintf(stderr,"CORPUS_BEGIN %s\n",key);fflush(stderr);int r=compile(d,create,destroy,line);fprintf(stderr,"CORPUS_END %d\n",r);fflush(stderr);}
 free(line);vkDestroyDevice(d,0);
 if(messenger) ((PFN_vkDestroyDebugUtilsMessengerEXT)vkGetInstanceProcAddr(i,"vkDestroyDebugUtilsMessengerEXT"))(i,messenger,NULL);
 vkDestroyInstance(i,0);return 0;
}
