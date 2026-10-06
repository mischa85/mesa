/* SPDX-License-Identifier: MIT
 * Exact-bit compute probe. The shader writes {input A, input B, result, tag}.
 * Inputs and outputs are integers so the host transport never interprets FP32.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>
#define CK(x)                                                                  \
   do {                                                                        \
      VkResult r = (x);                                                        \
      if (r) {                                                                 \
         fprintf(stderr, "%s: %d\n", #x, r);                                   \
         exit(2);                                                              \
      }                                                                        \
   } while (0)
static void *
read_file(const char *name, size_t *size)
{
   FILE *f = fopen(name, "rb");
   if (!f) {
      perror(name);
      exit(2);
   }
   fseek(f, 0, SEEK_END);
   *size = ftell(f);
   rewind(f);
   void *p = malloc(*size);
   if (fread(p, 1, *size, f) != *size)
      exit(2);
   fclose(f);
   return p;
}
int
main(int argc, char **argv)
{
   if (argc != 3) {
      fprintf(stderr, "usage: %s shader.spv inputs.bin\n", argv[0]);
      return 2;
   }
   size_t code_size, input_size;
   uint32_t *code = read_file(argv[1], &code_size);
   uint32_t *input = read_file(argv[2], &input_size);
   if (!input_size || input_size % 16 || code_size % 4)
      return 2;
   unsigned count = input_size / 16;
   VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
                            .pApplicationName = "Apple9 exact-bit denorm probe",
                            .apiVersion = VK_API_VERSION_1_2};
   VkInstance inst;
   CK(vkCreateInstance(
      &(VkInstanceCreateInfo){.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
                              .pApplicationInfo = &app},
      0, &inst));
   uint32_t n = 1;
   VkPhysicalDevice pd;
   CK(vkEnumeratePhysicalDevices(inst, &n, &pd));
   VkPhysicalDeviceDriverProperties driver = {
      .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
   VkPhysicalDeviceProperties2 prop = {
      .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,
      .pNext = &driver};
   vkGetPhysicalDeviceProperties2(pd, &prop);
   fprintf(stderr, "DEVICE %s DRIVER %s %s VERSION %u\n",
           prop.properties.deviceName, driver.driverName, driver.driverInfo,
           prop.properties.driverVersion);
   if (!strstr(prop.properties.deviceName, "Apple M4"))
      return 2;
   bool atomic = strstr(argv[1], "atomic_add") != NULL;
   VkPhysicalDeviceShaderAtomicFloatFeaturesEXT atomics = {
      .sType =
         VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_ATOMIC_FLOAT_FEATURES_EXT,
      .shaderBufferFloat32AtomicAdd = VK_TRUE,
   };
   const char *atomic_ext = VK_EXT_SHADER_ATOMIC_FLOAT_EXTENSION_NAME;
   float priority = 1;
   VkDevice dev;
   CK(vkCreateDevice(
      pd,
      &(VkDeviceCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
         .pNext = atomic ? &atomics : NULL,
         .enabledExtensionCount = atomic ? 1 : 0,
         .ppEnabledExtensionNames = atomic ? &atomic_ext : NULL,
         .queueCreateInfoCount = 1,
         .pQueueCreateInfos =
            &(VkDeviceQueueCreateInfo){
               .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
               .queueFamilyIndex = 0,
               .queueCount = 1,
               .pQueuePriorities = &priority}},
      0, &dev));
   VkQueue q;
   vkGetDeviceQueue(dev, 0, 0, &q);
   VkPhysicalDeviceMemoryProperties mp;
   vkGetPhysicalDeviceMemoryProperties(pd, &mp);
   VkBuffer buf[2];
   VkDeviceMemory mem[2];
   uint32_t *map[2];
   for (unsigned i = 0; i < 2; i++) {
      CK(vkCreateBuffer(
         dev,
         &(VkBufferCreateInfo){.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
                               .size = input_size,
                               .usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT},
         0, &buf[i]));
      VkMemoryRequirements req;
      vkGetBufferMemoryRequirements(dev, buf[i], &req);
      unsigned t;
      for (t = 0; t < mp.memoryTypeCount; t++)
         if ((req.memoryTypeBits & (1u << t)) &&
             (mp.memoryTypes[t].propertyFlags &
              (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
               VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) ==
                (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                 VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))
            break;
      if (t == mp.memoryTypeCount)
         return 2;
      CK(vkAllocateMemory(dev,
                          &(VkMemoryAllocateInfo){
                             .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
                             .allocationSize = req.size,
                             .memoryTypeIndex = t},
                          0, &mem[i]));
      CK(vkBindBufferMemory(dev, buf[i], mem[i], 0));
      CK(vkMapMemory(dev, mem[i], 0, VK_WHOLE_SIZE, 0, (void **)&map[i]));
   }
   memcpy(map[0], input, input_size);
   memset(map[1], 0xcd, input_size);
   if (atomic)
      for (unsigned i = 0; i < count; ++i)
         map[1][4 * i + 2] = input[4 * i];
   VkDescriptorSetLayoutBinding bindings[2];
   for (unsigned i = 0; i < 2; i++)
      bindings[i] = (VkDescriptorSetLayoutBinding){
         .binding = i,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
         .descriptorCount = 1,
         .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT};
   VkDescriptorSetLayout layout;
   CK(vkCreateDescriptorSetLayout(
      dev,
      &(VkDescriptorSetLayoutCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
         .bindingCount = 2,
         .pBindings = bindings},
      0, &layout));
   VkDescriptorPool pool;
   CK(vkCreateDescriptorPool(
      dev,
      &(VkDescriptorPoolCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
         .maxSets = 1,
         .poolSizeCount = 1,
         .pPoolSizes =
            &(VkDescriptorPoolSize){VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 2}},
      0, &pool));
   VkDescriptorSet set;
   CK(vkAllocateDescriptorSets(
      dev,
      &(VkDescriptorSetAllocateInfo){
         .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
         .descriptorPool = pool,
         .descriptorSetCount = 1,
         .pSetLayouts = &layout},
      &set));
   VkDescriptorBufferInfo infos[2];
   VkWriteDescriptorSet writes[2];
   for (unsigned i = 0; i < 2; i++) {
      infos[i] = (VkDescriptorBufferInfo){buf[i], 0, input_size};
      writes[i] = (VkWriteDescriptorSet){
         .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
         .dstSet = set,
         .dstBinding = i,
         .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
         .pBufferInfo = &infos[i]};
   }
   vkUpdateDescriptorSets(dev, 2, writes, 0, 0);
   VkPushConstantRange range = {VK_SHADER_STAGE_COMPUTE_BIT, 0, 4};
   VkPipelineLayout pl;
   CK(vkCreatePipelineLayout(
      dev,
      &(VkPipelineLayoutCreateInfo){
         .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
         .setLayoutCount = 1,
         .pSetLayouts = &layout,
         .pushConstantRangeCount = 1,
         .pPushConstantRanges = &range},
      0, &pl));
   VkShaderModule mod;
   CK(vkCreateShaderModule(
      dev,
      &(VkShaderModuleCreateInfo){
         .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
         .codeSize = code_size,
         .pCode = code},
      0, &mod));
   VkPipeline pipe;
   CK(vkCreateComputePipelines(
      dev, 0, 1,
      &(VkComputePipelineCreateInfo){
         .sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
         .stage = {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
                   .stage = VK_SHADER_STAGE_COMPUTE_BIT,
                   .module = mod,
                   .pName = "main"},
         .layout = pl},
      0, &pipe));
   VkCommandPool cp;
   CK(vkCreateCommandPool(
      dev,
      &(VkCommandPoolCreateInfo){
         .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
         .queueFamilyIndex = 0},
      0, &cp));
   VkCommandBuffer cb;
   CK(vkAllocateCommandBuffers(
      dev,
      &(VkCommandBufferAllocateInfo){
         .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
         .commandPool = cp,
         .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
         .commandBufferCount = 1},
      &cb));
   CK(vkBeginCommandBuffer(
      cb, &(VkCommandBufferBeginInfo){
             .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO}));
   VkMemoryBarrier barrier = {.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
                              .srcAccessMask = VK_ACCESS_HOST_WRITE_BIT,
                              .dstAccessMask = VK_ACCESS_SHADER_READ_BIT};
   vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_HOST_BIT,
                        VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 1, &barrier, 0,
                        0, 0, 0);
   vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pipe);
   vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pl, 0, 1, &set,
                           0, 0);
   vkCmdPushConstants(cb, pl, VK_SHADER_STAGE_COMPUTE_BIT, 0, 4, &count);
   vkCmdDispatch(cb, (count + 31) / 32, 1, 1);
   barrier.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
   barrier.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
   vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                        VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &barrier, 0, 0, 0, 0);
   CK(vkEndCommandBuffer(cb));
   VkFence fence;
   CK(vkCreateFence(
      dev, &(VkFenceCreateInfo){.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO},
      0, &fence));
   CK(vkQueueSubmit(q, 1,
                    &(VkSubmitInfo){.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
                                    .commandBufferCount = 1,
                                    .pCommandBuffers = &cb},
                    fence));
   CK(vkWaitForFences(dev, 1, &fence, VK_TRUE, 5000000000ull));
   unsigned bad = 0;
   for (unsigned i = 0; i < count; i++) {
      const uint32_t *v = map[1] + i * 4, *in = input + i * 4;
      if (v[0] != in[0] || v[1] != in[1] || v[3] != (in[3] ^ 0x6d2b79f5u))
         bad++;
      printf("%u %08x %08x %08x %08x\n", i, v[0], v[1], v[2], v[3]);
   }
   fprintf(stderr, "TRANSPORT count=%u bad=%u\n", count, bad);
   vkDestroyFence(dev, fence, 0);
   vkDestroyCommandPool(dev, cp, 0);
   vkDestroyPipeline(dev, pipe, 0);
   vkDestroyShaderModule(dev, mod, 0);
   vkDestroyPipelineLayout(dev, pl, 0);
   vkDestroyDescriptorPool(dev, pool, 0);
   vkDestroyDescriptorSetLayout(dev, layout, 0);
   for (unsigned i = 0; i < 2; i++) {
      vkUnmapMemory(dev, mem[i]);
      vkDestroyBuffer(dev, buf[i], 0);
      vkFreeMemory(dev, mem[i], 0);
   }
   vkDestroyDevice(dev, 0);
   vkDestroyInstance(inst, 0);
   free(input);
   free(code);
   return bad ? 1 : 0;
}
