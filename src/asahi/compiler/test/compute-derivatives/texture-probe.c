/* SPDX-License-Identifier: MIT
 * Compute texture probe: mip-tagged images, explicit-gradient controls, LOD
 * queries, and exact coordinate/tag echoes. Readback is raw 32-bit words.
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
   if (argc != 11) {
      fprintf(stderr, "usage: %s shader.spv inputs.bin dimension threads bias min max base aniso nearest\n", argv[0]);
      return 2;
   }
   const char *dim = argv[3];
   bool cube = !strncmp(dim, "cube", 4), array = strchr(dim, 'a') != NULL;
   unsigned axes = cube || !strncmp(dim, "3d", 2) ? 3 :
                   !strncmp(dim, "1d", 2) ? 1 : 2;
   unsigned local_threads = strtoul(argv[4], NULL, 0);
   float bias = strtof(argv[5], NULL), min_lod = strtof(argv[6], NULL);
   float max_lod = strtof(argv[7], NULL), aniso = strtof(argv[9], NULL);
   unsigned base_level = strtoul(argv[8], NULL, 0);
   unsigned layers = cube ? (array ? 12 : 6) : (array ? 2 : 1);
   if (!local_threads || base_level >= 6)
      return 2;
   size_t code_size, input_size;
   uint32_t *code = read_file(argv[1], &code_size);
   uint32_t *input = read_file(argv[2], &input_size);
   if (!input_size || input_size % 16 || code_size % 4)
      return 2;
   unsigned count = input_size / 16;
   size_t output_size = input_size * 2;
   VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
                            .pApplicationName = "Apple9 exact-bit compute probe",
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
   VkPhysicalDeviceFloatControlsProperties controls = {
      .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FLOAT_CONTROLS_PROPERTIES,
   };
   driver.pNext = &controls;
   VkPhysicalDeviceProperties2 prop = {
      .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,
      .pNext = &driver};
   vkGetPhysicalDeviceProperties2(pd, &prop);
   fprintf(stderr, "DEVICE %s DRIVER %s %s VERSION %u\n",
           prop.properties.deviceName, driver.driverName, driver.driverInfo,
           prop.properties.driverVersion);
   fprintf(stderr, "FP32_CONTROLS ftz=%u preserve=%u signed_zero_inf_nan=%u\n",
           controls.shaderDenormFlushToZeroFloat32,
           controls.shaderDenormPreserveFloat32,
           controls.shaderSignedZeroInfNanPreserveFloat32);
   const char *expected_device = getenv("PROBE_DEVICE_SUBSTRING");
   if (!strstr(prop.properties.deviceName, expected_device ?: "Apple M4"))
      return 2;
   VkPhysicalDeviceComputeShaderDerivativesFeaturesKHR derivative_features = {
      .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COMPUTE_SHADER_DERIVATIVES_FEATURES_KHR,
      .computeDerivativeGroupLinear = VK_TRUE,
   };
   const char *derivative_ext = VK_KHR_COMPUTE_SHADER_DERIVATIVES_EXTENSION_NAME;
   float priority = 1;
   VkDevice dev;
   CK(vkCreateDevice(
      pd,
      &(VkDeviceCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
         .pNext = &derivative_features,
         .pEnabledFeatures = &(VkPhysicalDeviceFeatures){
            .samplerAnisotropy = aniso > 1, .imageCubeArray = cube && array},
         .enabledExtensionCount = 1,
         .ppEnabledExtensionNames = &derivative_ext,
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
                               .size = i ? output_size : input_size,
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
   memset(map[1], 0xcd, output_size);
   VkImage image;
   VkExtent3D extent = {32, axes == 1 ? 1 : 32, axes == 3 && !cube ? 32 : 1};
   CK(vkCreateImage(dev, &(VkImageCreateInfo){
      .sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
      .flags = cube ? VK_IMAGE_CREATE_CUBE_COMPATIBLE_BIT : 0,
      .imageType = axes == 1 ? VK_IMAGE_TYPE_1D : axes == 3 && !cube ? VK_IMAGE_TYPE_3D : VK_IMAGE_TYPE_2D,
      .format = VK_FORMAT_R32G32B32A32_SFLOAT, .extent = extent,
      .mipLevels = 6, .arrayLayers = layers, .samples = VK_SAMPLE_COUNT_1_BIT,
      .tiling = VK_IMAGE_TILING_OPTIMAL,
      .usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
   }, NULL, &image));
   VkMemoryRequirements image_req;
   vkGetImageMemoryRequirements(dev, image, &image_req);
   unsigned image_type = 0;
   while (!(image_req.memoryTypeBits & (1u << image_type))) ++image_type;
   VkDeviceMemory image_mem;
   CK(vkAllocateMemory(dev, &(VkMemoryAllocateInfo){
      .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize = image_req.size, .memoryTypeIndex = image_type,
   }, NULL, &image_mem));
   CK(vkBindImageMemory(dev, image, image_mem, 0));
   VkImageView view;
   CK(vkCreateImageView(dev, &(VkImageViewCreateInfo){
      .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = image,
      .viewType = cube ? (array ? VK_IMAGE_VIEW_TYPE_CUBE_ARRAY : VK_IMAGE_VIEW_TYPE_CUBE) :
         axes == 1 ? (array ? VK_IMAGE_VIEW_TYPE_1D_ARRAY : VK_IMAGE_VIEW_TYPE_1D) :
         axes == 3 ? VK_IMAGE_VIEW_TYPE_3D :
         array ? VK_IMAGE_VIEW_TYPE_2D_ARRAY : VK_IMAGE_VIEW_TYPE_2D,
      .format = VK_FORMAT_R32G32B32A32_SFLOAT,
      .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, base_level, 6 - base_level, 0, layers},
   }, NULL, &view));
   VkSampler sampler;
   CK(vkCreateSampler(dev, &(VkSamplerCreateInfo){
      .sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO,
      .magFilter = VK_FILTER_LINEAR, .minFilter = VK_FILTER_LINEAR,
      .mipmapMode = atoi(argv[10]) ? VK_SAMPLER_MIPMAP_MODE_NEAREST : VK_SAMPLER_MIPMAP_MODE_LINEAR,
      .addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
      .addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
      .addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
      .mipLodBias = bias, .minLod = min_lod, .maxLod = max_lod,
      .anisotropyEnable = aniso > 1, .maxAnisotropy = aniso,
   }, NULL, &sampler));
   VkDescriptorSetLayoutBinding bindings[3];
   for (unsigned i = 0; i < 2; i++)
      bindings[i] = (VkDescriptorSetLayoutBinding){
         .binding = i,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
         .descriptorCount = 1,
         .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT};
   bindings[2] = (VkDescriptorSetLayoutBinding){
      .binding = 2, .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
      .descriptorCount = 1, .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT};
   VkDescriptorSetLayout layout;
   CK(vkCreateDescriptorSetLayout(
      dev,
      &(VkDescriptorSetLayoutCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
         .bindingCount = 3,
         .pBindings = bindings},
      0, &layout));
   VkDescriptorPool pool;
   CK(vkCreateDescriptorPool(
      dev,
      &(VkDescriptorPoolCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
         .maxSets = 1,
         .poolSizeCount = 2,
         .pPoolSizes = (VkDescriptorPoolSize[]){
            {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 2},
            {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1}}},
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
   VkWriteDescriptorSet writes[3];
   for (unsigned i = 0; i < 2; i++) {
      infos[i] = (VkDescriptorBufferInfo){buf[i], 0, i ? output_size : input_size};
      writes[i] = (VkWriteDescriptorSet){
         .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
         .dstSet = set,
         .dstBinding = i,
         .descriptorCount = 1,
         .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
         .pBufferInfo = &infos[i]};
   }
   VkDescriptorImageInfo image_info = {sampler, view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
   writes[2] = (VkWriteDescriptorSet){
      .sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
      .dstSet = set, .dstBinding = 2, .descriptorCount = 1,
      .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
      .pImageInfo = &image_info};
   vkUpdateDescriptorSets(dev, 3, writes, 0, 0);
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
   VkImageMemoryBarrier image_barrier = {
      .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
      .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
      .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .image = image,
      .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 6, 0, layers}};
   vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
      VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, NULL, 0, NULL, 1, &image_barrier);
   for (unsigned level = 0; level < 6; ++level) {
      VkClearColorValue color = {.float32 = {level + 1, 0, 0, 1}};
      VkImageSubresourceRange sub = {VK_IMAGE_ASPECT_COLOR_BIT, level, 1, 0, layers};
      vkCmdClearColorImage(cb, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &color, 1, &sub);
   }
   image_barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
   image_barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
   image_barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
   image_barrier.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
   vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TRANSFER_BIT,
      VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 0, NULL, 0, NULL, 1, &image_barrier);
   vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pipe);
   vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pl, 0, 1, &set,
                           0, 0);
   vkCmdPushConstants(cb, pl, VK_SHADER_STAGE_COMPUTE_BIT, 0, 4, &count);
   vkCmdDispatch(cb, (count + local_threads - 1) / local_threads, 1, 1);
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
      const uint32_t *v = map[1] + i * 8, *in = input + i * 4;
      if (v[0] != in[0] || v[1] != in[1] || v[3] != (i ^ 0x6d2b79f5u) ||
          v[7] != (i ^ 0xa5120000u)) bad++;
      for (unsigned j = 2; j < 7; ++j) if (v[j] == 0xcdcdcdcdu) bad++;
      printf("%u", i);
      for (unsigned j = 0; j < 8; ++j) printf(" %08x", v[j]);
      printf("\n");
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
   vkDestroySampler(dev, sampler, 0);
   vkDestroyImageView(dev, view, 0);
   vkDestroyImage(dev, image, 0);
   vkFreeMemory(dev, image_mem, 0);
   vkDestroyDevice(dev, 0);
   vkDestroyInstance(inst, 0);
   free(input);
   free(code);
   return bad ? 1 : 0;
}
