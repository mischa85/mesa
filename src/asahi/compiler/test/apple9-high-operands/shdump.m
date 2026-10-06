// SPDX-License-Identifier: MIT
// Compile only our authored MSL using public Metal APIs. No dispatch or reset.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdio.h>
#include <stdlib.h>

static void fail(NSString *operation, NSError *error)
{
   fprintf(stderr, "%s: %s\n", operation.UTF8String,
           error ? error.localizedDescription.UTF8String : "failed");
   exit(1);
}

int main(int argc, const char **argv)
{
   if (argc != 4) {
      fprintf(stderr, "usage: shdump source.metal output.bin max-threads (0=default)\n");
      return 1;
   }
   @autoreleasepool {
      char *end = NULL;
      unsigned long limit = strtoul(argv[3], &end, 10);
      if (!*argv[3] || *end || limit > 1024) return 1;
      NSError *error = nil;
      NSString *source = [NSString stringWithContentsOfFile:@(argv[1])
                                 encoding:NSUTF8StringEncoding error:&error];
      if (!source) fail(@"read authored source", error);
      id<MTLDevice> device = MTLCreateSystemDefaultDevice();
      if (!device) fail(@"create Metal device", nil);
      MTLCompileOptions *options = [MTLCompileOptions new];
      options.fastMathEnabled = YES;
      id<MTLLibrary> library = [device newLibraryWithSource:source options:options error:&error];
      if (!library) fail(@"compile authored source", error);
      id<MTLFunction> function = [library newFunctionWithName:@"k"];
      if (!function) fail(@"find k", nil);
      MTLComputePipelineDescriptor *desc = [MTLComputePipelineDescriptor new];
      desc.computeFunction = function;
      if (limit) desc.maxTotalThreadsPerThreadgroup = limit;
      id<MTLComputePipelineState> pipeline =
         [device newComputePipelineStateWithDescriptor:desc options:MTLPipelineOptionNone
                                           reflection:nil error:&error];
      if (!pipeline) fail(@"create compute pipeline", error);
      MTLBinaryArchiveDescriptor *archiveDesc = [MTLBinaryArchiveDescriptor new];
      id<MTLBinaryArchive> archive = [device newBinaryArchiveWithDescriptor:archiveDesc error:&error];
      if (!archive) fail(@"create archive", error);
      if (![archive addComputePipelineFunctionsWithDescriptor:desc error:&error])
         fail(@"add compute pipeline", error);
      if (![archive serializeToURL:[NSURL fileURLWithPath:@(argv[2])] error:&error])
         fail(@"serialize archive", error);
      fprintf(stderr, "device=%s requested_max_threads=%lu width=%lu actual_max_threads=%lu\n",
              device.name.UTF8String, limit, (unsigned long)pipeline.threadExecutionWidth,
              (unsigned long)pipeline.maxTotalThreadsPerThreadgroup);
   }
   return 0;
}
