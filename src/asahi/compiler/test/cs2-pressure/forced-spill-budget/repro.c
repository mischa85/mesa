/* SPDX-License-Identifier: MIT
 * CPU-only pipeline creation regression; run with the explicit host shim.
 */
#include <stdio.h>
#include <stdlib.h>
#include <vulkan/vulkan.h>
#define CK(x)                                                                  \
   do {                                                                        \
      VkResult r = (x);                                                        \
      if (r) {                                                                 \
         fprintf(stderr, "%s = %d\n", #x, r);                                  \
         exit(1);                                                              \
      }                                                                        \
   } while (0)
static VkShaderModule
shader(VkDevice d, const char *path)
{
   FILE *f = fopen(path, "rb");
   if (!f)
      abort();
   fseek(f, 0, SEEK_END);
   size_t n = ftell(f);
   rewind(f);
   void *p = malloc(n);
   if (fread(p, 1, n, f) != n)
      abort();
   fclose(f);
   VkShaderModule m;
   CK(vkCreateShaderModule(
      d,
      &(VkShaderModuleCreateInfo){
         .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
         .codeSize = n,
         .pCode = p},
      0, &m));
   free(p);
   return m;
}
int
main(int argc, char **argv)
{
   VkInstance instance;
   CK(vkCreateInstance(
      &(VkInstanceCreateInfo){
         .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
         .pApplicationInfo =
            &(VkApplicationInfo){.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
                                 .apiVersion = VK_API_VERSION_1_2}},
      0, &instance));
   uint32_t n = 1;
   VkPhysicalDevice pd;
   CK(vkEnumeratePhysicalDevices(instance, &n, &pd));
   float priority = 1;
   VkDevice d;
   CK(vkCreateDevice(
      pd,
      &(VkDeviceCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
         .queueCreateInfoCount = 1,
         .pQueueCreateInfos =
            &(VkDeviceQueueCreateInfo){
               .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
               .queueCount = 1,
               .pQueuePriorities = &priority}},
      0, &d));
   VkDescriptorSetLayoutBinding bindings[2];
   for (int i = 0; i < 2; i++)
      bindings[i] = (VkDescriptorSetLayoutBinding){
         .binding = i,
         .descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
         .descriptorCount = 1,
         .stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT};
   VkDescriptorSetLayout set;
   CK(vkCreateDescriptorSetLayout(
      d,
      &(VkDescriptorSetLayoutCreateInfo){
         .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
         .bindingCount = 2,
         .pBindings = bindings},
      0, &set));
   VkPipelineLayout layout;
   CK(vkCreatePipelineLayout(
      d,
      &(VkPipelineLayoutCreateInfo){
         .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
         .setLayoutCount = 1,
         .pSetLayouts = &set},
      0, &layout));
   VkAttachmentDescription color = {
      .format = VK_FORMAT_R8G8B8A8_UNORM,
      .samples = VK_SAMPLE_COUNT_1_BIT,
      .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
      .storeOp = VK_ATTACHMENT_STORE_OP_STORE,
      .finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
   VkAttachmentReference ref = {0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
   VkSubpassDescription sub = {
      .pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS,
      .colorAttachmentCount = 1,
      .pColorAttachments = &ref};
   VkRenderPass pass;
   CK(vkCreateRenderPass(d,
                         &(VkRenderPassCreateInfo){
                            .sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
                            .attachmentCount = 1,
                            .pAttachments = &color,
                            .subpassCount = 1,
                            .pSubpasses = &sub},
                         0, &pass));
   VkPipelineShaderStageCreateInfo stages[2] = {
      {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
       .stage = VK_SHADER_STAGE_VERTEX_BIT,
       .module = shader(d, argv[1]),
       .pName = "main"},
      {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
       .stage = VK_SHADER_STAGE_FRAGMENT_BIT,
       .module = shader(d, argv[2]),
       .pName = "main"}};
   VkViewport viewport = {.width = 16, .height = 16, .maxDepth = 1};
   VkRect2D scissor = {.extent = {16, 16}};
   VkPipelineColorBlendAttachmentState blend = {.colorWriteMask = 15};
   VkPipeline pipeline;
   CK(vkCreateGraphicsPipelines(
      d, VK_NULL_HANDLE, 1,
      &(VkGraphicsPipelineCreateInfo){
         .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
         .stageCount = 2,
         .pStages = stages,
         .layout = layout,
         .renderPass = pass,
         .pVertexInputState =
            &(VkPipelineVertexInputStateCreateInfo){
               .sType =
                  VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO},
         .pInputAssemblyState =
            &(VkPipelineInputAssemblyStateCreateInfo){
               .sType =
                  VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
               .topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST},
         .pViewportState =
            &(VkPipelineViewportStateCreateInfo){
               .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
               .viewportCount = 1,
               .pViewports = &viewport,
               .scissorCount = 1,
               .pScissors = &scissor},
         .pRasterizationState =
            &(VkPipelineRasterizationStateCreateInfo){
               .sType =
                  VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
               .polygonMode = VK_POLYGON_MODE_FILL,
               .lineWidth = 1},
         .pMultisampleState =
            &(VkPipelineMultisampleStateCreateInfo){
               .sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
               .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT},
         .pColorBlendState =
            &(VkPipelineColorBlendStateCreateInfo){
               .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
               .attachmentCount = 1,
               .pAttachments = &blend}},
      0, &pipeline));
   puts("pipeline compiled");
   vkDestroyPipeline(d, pipeline, 0);
   vkDestroyDevice(d, 0);
   vkDestroyInstance(instance, 0);
   return 0;
}
